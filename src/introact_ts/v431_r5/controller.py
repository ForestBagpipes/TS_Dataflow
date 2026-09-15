"""Current-task version trials. Runtime has no loss, label or unqueried cache API."""
from dataclasses import dataclass
import time
import numpy as np
from .scoring import response_features, reference_features
from .geometry import project_scores


@dataclass(frozen=True)
class TrialResult:
    action: int
    prediction: np.ndarray
    input_hash: str
    identity: dict
    governance_seconds: float
    forecast_seconds: float
    status: str = 'completed'
    actual_action: int | None = None
    alias_reason: str | None = None

    @property
    def seconds(self):
        return self.governance_seconds+self.forecast_seconds

    def summary(self):
        return dict(action=self.action, input_hash=self.input_hash, identity=self.identity,
                    governance_seconds=self.governance_seconds, forecast_seconds=self.forecast_seconds,
                    status=self.status, actual_action=self.actual_action, alias_reason=self.alias_reason)


def run(visible, scale, fully_observed, budget, reference_policy, critic, prior, estimate,
        execute_trial, *, mode='full', schedule='selective', lambda_value=0.,
        max_versions=3, initial_seconds=0., simulate_costs=True, score_mode='current',
        history_responses=None, output_reserve=.001):
    """Only execute_trial(action) can reveal an action's actual current prediction.

    simulate_costs adds audited historic component fees to CPU wall, whereas
    live runtime uses actual elapsed wall only. No final prediction is repeated.
    Historical evidence is an explicitly prepaid optional mechanism baseline.
    """
    if schedule not in ('selective','fixed','all','reference'):
        raise ValueError('Unregistered schedule')
    if lambda_value not in (0.,.01,.1) or max_versions not in (1,2,3,5):
        raise ValueError('Unregistered budget/search')
    if score_mode not in ('current','free','history'):
        raise ValueError('Unregistered visible score mode')
    x=np.asarray(visible,float)
    if x.ndim!=1 or np.isinf(x).any() or not np.isfinite(scale) or scale<=0:
        raise ValueError('Invalid visible state')
    started=time.perf_counter(); paid=0.; queried=[]; trace=[]; chosen=0; failure=None
    def total():return initial_seconds+(time.perf_counter()-started)+paid
    def validate_cost(trial):
        if not all(np.isfinite(v) and v>=0 for v in (trial.governance_seconds,trial.forecast_seconds)):
            raise ValueError('Trial costs must be nonnegative and finite')
    reference=0 if fully_observed else reference_policy.predict(x,False)
    # A positive-cost final forecast is still required when no branch fits.
    first=execute_trial(reference)
    validate_cost(first)
    if first.status=='failed' or first.action!=reference or first.prediction.ndim!=1 or not np.isfinite(first.prediction).all():
        raise ValueError('Reference trial failed; no fabricated final prediction is available')
    queried.append(first)
    if simulate_costs:paid+=first.seconds
    gains=np.zeros(1); raw=np.zeros(1);reason='reference_only'
    while not fully_observed and schedule!='reference' and len(queried)<max_versions:
        remaining=budget-total()-output_reserve
        available=[a for a in range(5) if a not in [q.action for q in queried]]
        estimates={a:float(estimate(a)) for a in available}
        if any(not np.isfinite(v) or v<0 for v in estimates.values()):
            raise ValueError('Invalid frozen cost estimate')
        feasible=[a for a in available if estimates[a]<=remaining]
        if not feasible:
            reason='budget_STOP';break
        if schedule=='selective':
            f=np.r_[x,reference_features(first.prediction,scale)]
            mus=prior.predict(np.tile(f,(len(feasible),1)),feasible)
            utility={a:float(mu-max(0.,float(gains.max()))-lambda_value*estimates[a]) for a,mu in zip(feasible,mus)}
            action=min(feasible,key=lambda a:(-utility[a],estimates[a],a))
            if utility[action]<=0:
                reason='nonpositive_prior_STOP';break
        else:
            action=min(feasible);utility={}
        row=dict(action=action,available=available,feasible=feasible,remaining_budget=remaining,
                 estimates=estimates,prior_utility=utility)
        previous=chosen
        try:
            trial=execute_trial(action)
            validate_cost(trial)
            if simulate_costs:paid+=trial.seconds
            row['trial']=trial.summary()
            if trial.action!=action or trial.prediction.shape!=first.prediction.shape or not np.isfinite(trial.prediction).all():
                raise ValueError('Candidate identity/horizon/nonfinite prediction failure')
            queried.append(trial)
            if trial.status=='failed':
                failure='trial_failed';reason='failure_STOP';trace.append(row);break
            features=[]
            for q in queried[1:]:
                if score_mode=='current': extra=response_features(first.prediction,q.prediction,scale)
                elif score_mode=='free':extra=np.zeros(7)
                else:
                    if history_responses is None:raise ValueError('Historical evidence was not acquired')
                    extra=history_responses[q.action]
                features.append(np.r_[x,extra])
            raw=np.r_[0.,critic.predict(features,[q.action for q in queried[1:]])]
            if not np.isfinite(raw).all():raise ValueError('Nonfinite critic')
            result=project_scores(np.stack([q.prediction for q in queried]),raw,scale,weights=None,
                mode=mode,max_iter=2048,tolerance=1e-8,
                time_limit_seconds=max(0.,min(.05,budget-total()-output_reserve)))
            row['projection']=result.to_dict();row['raw']=raw.tolist()
            if result.status in ('timeout','failed'):
                chosen=previous;failure=result.reason;reason='solver_'+result.status+'_STOP';trace.append(row);break
            gains=result.scores
            chosen=0 if gains.max()<=0 else min(range(len(gains)),key=lambda j:(-gains[j],j!=0,queried[j].action))
            row['chosen_action']=queried[chosen].action;trace.append(row);reason='version_limit_STOP'
        except Exception as exc:
            # Live elapsed includes failures; synthetic/evaluator callbacks must
            # attach their actual cost when they fail before producing a trial.
            if simulate_costs:paid+=float(getattr(exc,'incurred_seconds',0.))
            chosen=previous;failure=type(exc).__name__+': '+str(exc);reason='failure_STOP'
            row['failure']=failure;trace.append(row);break
    seconds=total()+output_reserve
    return dict(action=queried[chosen].action,reference_action=reference,reason='complete_KEEP' if fully_observed else reason,
                queried=[q.summary() for q in queried],queried_actions=[q.action for q in queried],
                final_prediction=queried[chosen].prediction.copy(),raw=raw.tolist(),gains=gains.tolist(),trace=trace,
                total_seconds=seconds,budget_overrun=seconds>budget,versions=len(queried),
                failure=failure,final_input_hash=queried[chosen].input_hash,
                final_identity=queried[chosen].identity,output_reserve=output_reserve,
                cost_scope='historical components plus current CPU wall' if simulate_costs else 'actual request wall including output reserve')
