import numpy as np
import pytest

from introact_ts.v431.acquisition import (
    AcquiredBranch, Charge, CostInvoice, ParentRegressionTree, ValueLabelRow,
    execute_one_step, fit_acquirer, make_value_labels,
)


HASH = "terminal-frozen-sha256"
NAMES = ("missing_fraction", "horizon_ratio")


def invoice(**costs):
    return CostInvoice(tuple(Charge(key, value) for key, value in costs.items()))


def label(parent, *, tool="history", gain=1., variant=0, x=0., stop=None, acquire=None):
    tool_bill = invoice(tool=2.)
    return ValueLabelRow(
        uid=f"p{parent}-v{variant}", parent=f"p{parent}", tool=tool,
        terminal_hash=HASH, features=(x, 0.5), stop_loss=2., acquire_loss=2. - gain,
        stop_invoice=stop or invoice(shared=1., final_stop=4.),
        acquire_invoice=acquire or invoice(shared=1., tool=2., final_acquire=1.),
        weight=1./6, tool_invoice=tool_bill,
    )


def fit_constant(gain=1.):
    return fit_acquirer([label(parent, gain=gain) for parent in range(18)], HASH, NAMES)


def test_shared_invoice_deduplicates_without_erasing_actual_cost():
    shared = invoice(load=2., input=1.)
    complete = shared.merge(shared, invoice(tool=3., final=4.))
    assert complete.total_seconds == 10.
    assert len(complete.charges) == 4
    with pytest.raises(ValueError, match="conflicting"):
        shared.merge(invoice(load=4.))


def test_value_label_uses_complete_branch_difference_keeps_negative_and_zero():
    rows = [label(0, gain=-2.), label(1, gain=0.), label(2, gain=1.)]
    labels = make_value_labels(rows, HASH, 0.)
    assert [r["value"] for r in labels] == [-2., 0., 1.]
    priced = make_value_labels(rows, HASH, 0.5)
    # Acquiring costs 4 versus STOP 5, so delta is -1, despite a +2 tool cost.
    assert priced[0]["delta_cost"] == -1.
    assert priced[0]["value"] == -1.5
    assert priced[0]["acquire_cost"] == 4.
    assert priced[0]["tool_invoice"]["total_seconds"] == 2.


def test_label_policy_hash_and_parent_isolation_are_enforced():
    row = label(0)
    with pytest.raises(ValueError, match="hash"):
        make_value_labels([row], "new-terminal", 0.)
    with pytest.raises(ValueError, match="hash"):
        fit_acquirer([row], "new-terminal", NAMES)
    with pytest.raises(ValueError, match="overlap"):
        fit_acquirer([row], HASH, NAMES, forbidden_parents=["p0"])
    with pytest.raises(ValueError, match="T_acq"):
        ValueLabelRow(**{**row.__dict__, "role": "dev"})


def test_parent_support_cannot_be_inflated_with_corruption_variants():
    # There are 108 rows but just 18 parents: no split can make two 16-parent leaves.
    X = np.array([[float(parent >= 9)] for parent in range(18) for _ in range(6)])
    y = X[:, 0].copy()
    parents = [f"p{parent}" for parent in range(18) for _ in range(6)]
    tree = ParentRegressionTree().fit(X, y, parents)
    assert tree.root_.feature is None
    assert tree.root_.parent_count == 18
    with pytest.raises(ValueError, match="below 16"):
        ParentRegressionTree(min_parents=15)
    with pytest.raises(ValueError, match="insufficient"):
        ParentRegressionTree().fit(X[:90], y[:90], parents[:90])


def test_supported_tree_split_has_distinct_parent_counts_and_depth_bound():
    X = np.array([[float(parent)] for parent in range(40)])
    y = (X[:, 0] >= 20).astype(float)
    model = ParentRegressionTree().fit(X, y, [f"p{p}" for p in range(40)])
    assert model.root_.feature == 0
    assert model.root_.left.parent_count >= 16
    assert model.root_.right.parent_count >= 16
    # Sixteen quantile cutpoints need not include the exact class boundary.
    # The supported split must improve squared loss without relaxing support.
    assert np.sum((model.predict(X) - y) ** 2) < 1.


def test_lambda_is_group_cross_fitted_using_tool_cost_not_delta_cost():
    rows = [label(parent) for parent in range(18)]
    model = fit_acquirer(rows, HASH, NAMES)
    assert model.report["lambda_candidates"] == [0., 0.05]
    assert model.report["positive_tool_cost_scale"] == 2.
    for record in model.report["cv_records"]:
        assert record["held_parent"] not in record["train_parents"]
        assert len(record["train_parents"]) == 17
    assert model.models["history"].root_.feature is None
    zero = fit_acquirer([label(parent, gain=0.) for parent in range(18)], HASH, NAMES)
    assert zero.report["lambda_candidates"] == [0.]
    assert zero.report["scale_status"] == "degenerate_only_lambda_zero"


def test_hidden_evidence_cannot_be_fetched_on_stop_and_schema_rejects_unavailable_values():
    model = fit_constant(gain=-1.)
    called = []

    def forbidden_fetch(tool):
        called.append(tool)
        raise AssertionError("hidden evidence accessed")

    result = execute_one_step(
        terminal_hash=HASH, visible_features=(0., 0.5), stop_arm="A2_SINGLE",
        stop_invoice=invoice(stop=1.), branch_estimates={"history": invoice(branch=2.)},
        budget=3., applicable={"history": True}, model=model, fetch=forbidden_fetch,
    )
    assert result["status"] == "STOP" and not called
    with pytest.raises(ValueError, match="unavailable"):
        fit_acquirer([label(parent) for parent in range(18)], HASH,
                     ("candidate_roughness", "history_evidence"))
    with pytest.raises(ValueError, match="snapshot"):
        fit_acquirer([label(0), label(0, tool="mask", x=99.)], HASH, NAMES)


def test_admission_uses_complete_branch_not_favorable_negative_delta():
    model = fit_constant()
    called = []
    result = execute_one_step(
        terminal_hash=HASH, visible_features=(0., 0.5), stop_arm="A2_SINGLE",
        stop_invoice=invoice(stop=20.), branch_estimates={"history": invoice(branch=10.)},
        budget=5., applicable={"history": True}, model=model,
        fetch=lambda tool: called.append(tool),
    )
    assert not called and result["tool"] is None
    assert result["excluded"]["history"] == "estimated_complete_branch_exceeds_budget"
    assert result["budget_overrun"]  # Even STOP was infeasible; never hide that fact.
    assert result["total_seconds"] == 20.


def test_actual_overrun_is_retained_with_one_fetch_and_no_free_rollback():
    model = fit_constant()
    called = []

    def fetch(tool):
        called.append(tool)
        return AcquiredBranch("A3_COV", invoice(tool=4., final=2.), "evidence-sha", HASH)

    result = execute_one_step(
        terminal_hash=HASH, visible_features=(0., 0.5), stop_arm="A2_SINGLE",
        stop_invoice=invoice(stop=1.), branch_estimates={"history": invoice(branch=2.)},
        budget=3., applicable={"history": True}, model=model, fetch=fetch,
    )
    assert called == ["history"]
    assert result["status"] == "budget_overrun"
    assert result["total_seconds"] == 6. and result["arm"] == "A3_COV"
    assert result["history"] == ["history"]
    with pytest.raises(ValueError, match="hash"):
        execute_one_step(
            terminal_hash="updated-terminal", visible_features=(0., 0.5), stop_arm="A2_SINGLE",
            stop_invoice=invoice(stop=1.), branch_estimates={}, budget=0.,
            applicable={}, model=model, fetch=fetch,
        )


def test_random_and_fixed_controls_share_complete_budget_and_fetch_contract():
    calls = []

    def fetch(tool):
        calls.append(tool)
        return AcquiredBranch("A0_NATIVE", invoice(branch=2.), "evidence", HASH)

    kwargs = dict(terminal_hash=HASH, visible_features=(0., 0.5), stop_arm="A2_SINGLE",
                  stop_invoice=invoice(stop=1.), branch_estimates={"history": invoice(branch=2.)},
                  budget=2., applicable={"history": True}, model=None, fetch=fetch)
    fixed = execute_one_step(**kwargs, mode="fixed")
    assert fixed["tool"] == "history" and calls == ["history"]
    first = execute_one_step(**kwargs, mode="random", random_key="case-unique")
    second = execute_one_step(**kwargs, mode="random", random_key="case-unique")
    assert first["tool"] == second["tool"]
    stopped = execute_one_step(**kwargs, mode="simple", condition=False)
    assert stopped["tool"] is None


def test_unsupported_training_tool_is_explicit_not_zero_filled():
    model = fit_acquirer([label(parent) for parent in range(15)], HASH, NAMES)
    assert model.predict((0., 0.5), "history", HASH) is None
    assert model.report["tool_support"]["history"]["status"] == "unsupported_parent_count"
