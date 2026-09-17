"""The deployable methods and the fixed ablation ladder (task book §17, §21, §22).

Every method here consumes exactly the same observable inputs: the per-action
task-state vector and the replay bank.  Nothing reads a candidate's forecast, a
future label, or another method's decision.

The ablation ladder is implemented as *flags on one selector* wherever the
ablation is "remove a component", so a typo cannot silently turn an ablation
into a different method:

===========================  ==================================================
Full IntroAct                replay + local + intervention + forecast + gate
A1 Global Replay             ``local=False``
A2 w/o Intervention State    ``use_intervention=False``
A3 w/o Forecast State        ``use_forecast=False``
A4 w/o Conservative Gate     ``conservative=False``
A5 Parametric Gain Predictor retrieval replaced by a Ridge / CART regressor
===========================  ==================================================
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from .catalog import EpisodeCatalog
from .matching import ConservativeSelector
from .protocol import ACTIONS, BANK_BLOCK, BETA_GRID, K_GRID, REFERENCE_ACTION
from .replay import ReplayBank

#: The frozen R2 control estimator: the project's existing strong simple
#: control, reused unchanged as an estimator (same depth, same leaf size, same
#: seed).  Only its evidence base moves to the v4.4 state features, which the
#: report states explicitly.
R2_CART_PARAMS = dict(max_depth=3, min_samples_leaf=96, random_state=101)


@dataclass
class MethodRun:
    method: str
    backbone: str
    selected: dict[str, str]
    trace: dict[str, dict]
    notes: dict


def _query_states(catalog: EpisodeCatalog) -> dict[str, np.ndarray]:
    return {action: entry.state_vector
            for action, entry in catalog.actions.items()
            if entry.state_vector is not None}


def full_selector(bank: ReplayBank, *, k: int, beta: float,
                  block_of: dict[str, str] | None = None,
                  block: str = BANK_BLOCK, **flags) -> ConservativeSelector:
    selector = ConservativeSelector(k=k, beta=beta, **flags)
    selector.fit(bank, block_of=block_of, block=block)
    return selector


def select_with(selector: ConservativeSelector, bank: ReplayBank,
                catalogs: list[EpisodeCatalog], *,
                block_of: dict[str, str] | None,
                retrieval_block: str = BANK_BLOCK) -> MethodRun:
    """Apply a fitted selector to a block of requests.

    ``retrieval_block`` is the block the *bank* was built from, not the block
    being evaluated -- see :data:`BANK_BLOCK`.  The evaluated block is carried by
    ``catalogs``.
    """
    selected: dict[str, str] = {}
    trace: dict[str, dict] = {}
    notes = {"abstained": 0, "unavailable": 0}
    for catalog in catalogs:
        legal = catalog.legal()
        if not legal:
            selected[catalog.episode] = REFERENCE_ACTION
            notes["unavailable"] += 1
            continue
        states = _query_states(catalog)
        if not states:
            selected[catalog.episode] = REFERENCE_ACTION
            continue
        decision = selector.select(states, bank, legal=legal, block_of=block_of,
                                   block=retrieval_block)
        selected[catalog.episode] = decision.action
        trace[catalog.episode] = decision.trace()
        if not decision.intervened:
            notes["abstained"] += 1
    return MethodRun("", "", selected, trace, notes)


def native_keep(catalogs: list[EpisodeCatalog]) -> MethodRun:
    return MethodRun("NATIVE_KEEP", "", {c.episode: REFERENCE_ACTION
                                         for c in catalogs}, {},
                     {"abstained": len(catalogs)})


def best_fixed(gate_catalogs: list[EpisodeCatalog]) -> str:
    """The single action with the best mean realised utility on TRAIN-Gate.

    Chosen once, on the gate block, and then applied to every request -- which
    is exactly what makes it a *fixed* control rather than a learned policy.
    """
    totals: dict[str, list[float]] = defaultdict(list)
    for catalog in gate_catalogs:
        for action, entry in catalog.actions.items():
            if entry.utility is not None:
                totals[action].append(entry.utility)
    if not totals:
        return REFERENCE_ACTION
    return max(sorted(totals), key=lambda a: float(np.mean(totals[a])))


def apply_fixed(action: str, catalogs: list[EpisodeCatalog]) -> MethodRun:
    selected = {}
    for catalog in catalogs:
        entry = catalog.actions.get(action)
        if entry is None or not entry.applicable or entry.prediction is None:
            selected[catalog.episode] = REFERENCE_ACTION
        else:
            selected[catalog.episode] = action
    return MethodRun(f"BEST_FIXED[{action}]", "", selected, {},
                     {"fixed_action": action})


def oracle_run(catalogs: list[EpisodeCatalog]) -> MethodRun:
    """Post-hoc best legal action.  Diagnostic only; never a deployable row."""
    selected = {}
    for catalog in catalogs:
        action, _ = catalog.oracle()
        selected[catalog.episode] = action or REFERENCE_ACTION
    return MethodRun("CATALOG_ORACLE", "", selected, {}, {"diagnostic_only": True})


def _episode_labels(bank: ReplayBank, *, block_of: dict[str, str],
                    block: str) -> tuple[np.ndarray, np.ndarray, list[int],
                                         list[str], list[str]]:
    """``(features, utilities, labels, actions, episodes)`` for the controls.

    One row per ``(episode, action)``: the action's state vector as features,
    the realised utility as the regression target, and the episode's best
    action as the classification label.
    """
    grouped: dict[str, dict[str, object]] = defaultdict(dict)
    for record in bank.records:
        if not record.scored or block_of.get(record.parent) != block:
            continue
        grouped[record.episode_uid][record.action] = record
    features, utilities, labels, actions, episodes = [], [], [], [], []
    for episode, bucket in grouped.items():
        scored = {a: r for a, r in bucket.items()
                  if getattr(r, "utility_vs_reference", None) is not None}
        if len(scored) < 2:
            continue
        best = max(sorted(scored), key=lambda a: scored[a].utility_vs_reference)
        for action, record in sorted(scored.items()):
            features.append(record.state_vector)
            utilities.append(record.utility_vs_reference)
            labels.append(ACTIONS.index(best))
            actions.append(action)
            episodes.append(episode)
    return (np.asarray(features, dtype=np.float64),
            np.asarray(utilities, dtype=np.float64),
            labels, actions, episodes)


def r2_cart(bank: ReplayBank, catalogs: list[EpisodeCatalog], *,
            block_of: dict[str, str], block: str = BANK_BLOCK) -> MethodRun:
    """The inherited strong simple control: a depth-3 CART over the same features.

    One classifier per action, each answering "is this action the best one for
    this state?".  The estimator and its hyper-parameters are the project's
    existing R2 control; only the evidence base moves to the v4.4 task-state
    features, and the report says so rather than implying the old numbers carry
    over unchanged.

    ``block`` is the block the evidence is *fitted* on -- the Replay-Fit bank --
    not the block in ``catalogs``, which is what the control is applied to.
    """
    from sklearn.tree import DecisionTreeClassifier

    features, _utilities, labels, actions, _episodes = _episode_labels(
        bank, block_of=block_of, block=block)
    if len(labels) == 0:
        raise RuntimeError("no replay rows to fit the R2 control")
    labels = np.asarray(labels)
    actions = np.asarray(actions)

    models: dict[str, DecisionTreeClassifier] = {}
    for action in ACTIONS:
        mask = actions == action
        if int(mask.sum()) < 8:
            continue
        target = (labels[mask] == ACTIONS.index(action)).astype(int)
        if len(np.unique(target)) < 2:
            continue
        models[action] = DecisionTreeClassifier(**R2_CART_PARAMS).fit(
            features[mask], target)

    selected = {}
    for catalog in catalogs:
        states = _query_states(catalog)
        legal = [a for a in catalog.legal() if a in states and a in models]
        if not legal:
            selected[catalog.episode] = REFERENCE_ACTION
            continue
        best, best_p = REFERENCE_ACTION, -1.0
        for action in legal:
            vector = states[action].reshape(1, -1)
            probability = float(models[action].predict_proba(vector)[0, 1])
            if probability > best_p:
                best, best_p = action, probability
        selected[catalog.episode] = best if best_p > 0.5 else REFERENCE_ACTION
    return MethodRun("R2_CART", "", selected, {},
                     {"estimator": R2_CART_PARAMS,
                      "evidence": "v4.4 task-state features on Replay-Fit",
                      "actions_fitted": sorted(models)})


def parametric(bank: ReplayBank, catalogs: list[EpisodeCatalog], *, k: int,
               beta: float, block_of: dict[str, str],
               block: str = BANK_BLOCK, kind: str = "ridge") -> MethodRun:
    """A5: replace replay retrieval with a lightweight parametric predictor.

    Same observable features, same conservative rule; only the way the local
    utility estimate is produced changes.  Depth-limited CART is available as
    the fixed secondary implementation; no deep network is used.

    As in :func:`r2_cart`, ``block`` names the block the evidence comes from
    (the Replay-Fit bank), not the block in ``catalogs``.
    """
    from sklearn.linear_model import Ridge
    from sklearn.tree import DecisionTreeRegressor

    features, utilities, labels, actions, _episodes = _episode_labels(
        bank, block_of=block_of, block=block)
    if len(labels) == 0:
        raise RuntimeError("no replay rows to fit the parametric predictor")
    actions = np.asarray(actions)

    models: dict[str, object] = {}
    residual: dict[str, float] = {}
    support: dict[str, int] = {}
    for action in ACTIONS:
        mask = actions == action
        if int(mask.sum()) < 8:
            continue
        x, y = features[mask], utilities[mask]
        if kind == "ridge":
            model = Ridge(alpha=1.0).fit(x, y)
        elif kind == "cart":
            model = DecisionTreeRegressor(**R2_CART_PARAMS).fit(x, y)
        else:
            raise ValueError(f"unregistered parametric kind {kind!r}")
        models[action] = model
        residual[action] = float(np.std(y - model.predict(x)))
        support[action] = int(mask.sum())

    selected = {}
    for catalog in catalogs:
        legal = [a for a in catalog.legal() if a in models]
        if not legal:
            selected[catalog.episode] = REFERENCE_ACTION
            continue
        scores = {}
        for action in legal:
            vector = catalog.actions[action].state_vector
            mu = float(models[action].predict(vector.reshape(1, -1))[0])
            scores[action] = mu - beta * residual[action] / np.sqrt(
                max(1.0, float(support[action])))
        best = max(legal, key=lambda a: (scores[a], -ACTIONS.index(a)))
        selected[catalog.episode] = best if scores[best] > 0.0 else REFERENCE_ACTION
    return MethodRun(f"A5_PARAMETRIC_{kind.upper()}", "", selected, {},
                     {"kind": kind, "k_ignored": k, "beta": beta,
                      "actions_fitted": sorted(models)})


def gate_sweep(bank: ReplayBank, gate_catalogs: list[EpisodeCatalog], *,
               block_of: dict[str, str]) -> list[dict]:
    """The nine allowed ``K x beta`` configurations on TRAIN-Gate (§20)."""
    from .metrics import macro_headline

    results = []
    for k in K_GRID:
        for beta in BETA_GRID:
            selector = full_selector(bank, k=k, beta=beta, block_of=block_of)
            run = select_with(selector, bank, gate_catalogs, block_of=block_of)
            records = []
            for catalog in gate_catalogs:
                entry = catalog.actions.get(run.selected[catalog.episode])
                if entry is None or entry.mase is None:
                    continue
                records.append({
                    "method": "FULL", "backbone": bank.backbone,
                    "source": catalog.source, "parent": catalog.parent,
                    "variant": catalog.episode, "horizon": catalog.horizon,
                    "pattern": catalog.pattern, "severity": catalog.severity,
                    "mase": entry.mase,
                })
            results.append({
                "k": k, "beta": beta,
                "source_macro_mase": macro_headline(records, "mase"),
                "abstained": run.notes["abstained"],
                "records": len(records),
            })
    return results
