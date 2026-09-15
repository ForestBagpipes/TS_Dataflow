"""Exact finite-grammar cost-sensitive policy search (generic method, not new theory).

Only fit labels enter search. Deployment accepts typed visible/evidence states.
Gate chooses predeclared split enablement/lambda outside this module.
"""
from dataclasses import dataclass
import hashlib,json,copy
import numpy as np
from .branch_cost import BranchCost

TOOLS=('H32','H','control')
ARMS=('A0_NATIVE','A0_FFILL','A2_SINGLE','A3_COV','A4_RIDGE_CONTEXT')
FORBIDDEN=('source','parent','uid','path','future','oracle','true_class','kappa','z_response')

@dataclass(frozen=True)
class VisibleState:
    features: dict
    fully_observed: bool
    applicable: dict

@dataclass(frozen=True)
class AcquiredEvidence:
    tool: str
    features: dict
    status: str='completed'


def _thresholds(x):
    x=np.asarray(x,float);x=x[np.isfinite(x)]
    return [] if not len(x) else sorted(set(np.quantile(x,[.25,.5,.75]).tolist()))

def _names(names):
    if any(any(word in str(n).lower() for word in FORBIDDEN) for n in names):
        raise ValueError('Forbidden feature identity/label/response in whitelist')

def _arm(node, values):
    if node['kind']=='leaf':return node['arm']
    value=values[node['feature']]
    if not np.isfinite(value):return node['missing_arm']
    return _arm(node['left'] if value<=node['threshold'] else node['right'],values)

class JointPolicy:
    def fit(self,batch,*,reference_arm=2,budget=3.5,lambda_value=0.,
            allow_free_split=True,objective='task',tools=TOOLS,forced_tool=None,
            minimum_parents=16,staged=False):
        if minimum_parents!=16:raise ValueError('Registered support is 16 parents')
        if objective not in ('task','classification'):raise ValueError('Unknown objective')
        if not set(tools)<=set(TOOLS):raise ValueError('Unknown tool')
        if forced_tool is not None and forced_tool not in tools:raise ValueError('Forced tool absent')
        if any(str(r) not in ('T_fit','fit') for r in batch.roles):raise ValueError('Only T_fit may optimize policy')
        self.free_names=tuple(batch.free_names);self.evidence_names={k:tuple(v) for k,v in batch.evidence_names.items()}
        _names(self.free_names)
        for names in self.evidence_names.values():_names(names)
        self.reference_arm=int(reference_arm);self.budget=float(budget);self.lambda_value=float(lambda_value)
        if self.budget<0 or self.lambda_value<0:raise ValueError('Negative budget/lambda')
        self.cost=BranchCost.fit(batch);self.minimum_parents=16
        self.training_parents=tuple(sorted(set(batch.parents)));self.objective=objective
        X=np.asarray(batch.visible,float);L=np.asarray(batch.losses,float);W=np.asarray(batch.weights,float)
        P=np.asarray(batch.parents);N=len(P);full=np.asarray(batch.fully_observed,bool)
        if L.shape!=(N,5) or not np.isfinite(L).all() or not np.isfinite(W).all() or (W<0).any():raise ValueError('Invalid real task losses/weights')
        C=np.asarray(batch.action_costs,float)
        best=np.argmin(L+np.arange(5)[None,:]*0.,axis=1)
        # True ties in the class target also prefer the fixed reference.
        best[np.isclose(L[:,reference_arm],np.min(L,axis=1),rtol=0,atol=1e-12)]=reference_arm
        target=L if objective=='task' else (np.arange(5)[None,:]!=best[:,None]).astype(float)
        loss=target+lambda_value*C
        action_admissible=np.array([[self.cost.action_estimate(a,dict(zip(self.free_names,row)))<=budget for a in range(5)] for row in X])
        feasible=[a for a in range(5) if np.any(action_admissible[:,a])]
        # No feasible final forecast is an explicit unmet-budget outcome, not free STOP.
        fallback_pool=feasible or list(range(5))
        self.fallback_order=tuple(sorted(range(5),key=lambda a:(float(np.sum(W*loss[:,a])),self.cost.action_seconds[a],a!=reference_arm,a)))
        self.fallback_arm=self.fallback_order[0]
        fallback_actions=np.array([self._fallback(dict(zip(self.free_names,row)),budget) for row in X],int)
        self.counts={'leaf_actions_scored':0,'evidence_splits_scored':0,'branches_scored':0,'free_splits_scored':0,'unsupported_terminal_leaves':0}
        self.free_thresholds={n:_thresholds(X[:,j]) for j,n in enumerate(self.free_names)}
        self.evidence_thresholds={}
        for t in tools:
            e=np.asarray(batch.evidence[t],float);valid=np.asarray(batch.supported[t],bool)
            self.evidence_thresholds[t]={n:_thresholds(e[valid,j]) for j,n in enumerate(self.evidence_names[t])}
        def support(mask):return len(set(P[mask]))
        def leaf(mask):
            count=support(mask)
            if count<16:
                self.counts['unsupported_terminal_leaves']+=1
                return None
            self.counts['leaf_actions_scored']+=len(fallback_pool)
            a=min(fallback_pool,key=lambda a:(float(np.sum(W[mask]*loss[mask,a])),float(np.sum(W[mask]*C[mask,a])),a!=reference_arm,a))
            return {'kind':'leaf','arm':int(a),'fit_parents':count}
        def route_term(term,e,mask):
            actions=fallback_actions.copy()
            if term['kind']=='leaf':actions[mask]=term['arm']
            else:
                j=self.evidence_names[current_tool].index(term['feature']);v=e[:,j]
                actions[mask&np.isfinite(v)&(v<=term['threshold'])]=term['left']['arm']
                actions[mask&np.isfinite(v)&(v>term['threshold'])]=term['right']['arm']
            return actions
        def rank(actions,costs,mask,nodes):
            actions=actions.copy();actions[full]=0
            effective=costs.copy();effective[full]=C[full,0]
            return (float(np.sum(W[mask]*(target[np.arange(N),actions]+lambda_value*effective)[mask])),
                    float(np.sum(W[mask]*effective[mask])),nodes,
                    int(np.sum(actions[mask]!=reference_arm)))
        staged_options={};staged_direct=None;stage_capture=bool(staged)
        def branch(mask):
            nonlocal current_tool,staged_direct
            active=mask&~full
            winner=None
            direct_pool=([staged_direct] if staged and not stage_capture else fallback_pool) if support(active)>=16 else [self.fallback_arm]
            for action in direct_pool:
                executed=active&action_admissible[:,action]
                if action!=self.fallback_arm and support(executed)<16:continue
                term={'kind':'leaf','arm':action,'fit_parents':support(executed)}
                if support(active)<16:term['registered_fallback']=True
                actions=fallback_actions.copy();actions[executed]=action
                costs=C[np.arange(N),actions]
                candidate=(rank(actions,costs,mask,1),{'kind':'submit','terminal':term})
                self.counts['leaf_actions_scored']+=1
                if winner is None or candidate[0]<winner[0]:winner=candidate
            if winner is None:
                actions=fallback_actions.copy()
                winner=(rank(actions,C[np.arange(N),actions],mask,1),{'kind':'submit','terminal':{'kind':'leaf','arm':self.fallback_arm,'registered_fallback':True,'fit_parents':0}})
            if stage_capture:staged_direct=winner[1]['terminal']['arm']
            if forced_tool is not None:winner=None
            for t in tools:
                if forced_tool is not None and t!=forced_tool:continue
                current_tool=t
                e=np.asarray(batch.evidence[t],float)
                possible=active&np.asarray(batch.supported[t],bool)&np.isfinite(e).all(axis=1)
                if support(possible)<16:continue
                # Enumerate terminal actions before reserving: unused expensive arms
                # must not exclude an otherwise feasible complete path.
                if staged and not stage_capture:
                    options=copy.deepcopy(staged_options.get(t,[]))
                else:
                    options=[dict(kind='leaf',arm=a,fit_parents=support(possible)) for a in fallback_pool]
                    for j,n in enumerate(self.evidence_names[t]):
                        for threshold in self.evidence_thresholds[t][n]:
                            lm=possible&(e[:,j]<=threshold);rm=possible&(e[:,j]>threshold)
                            if support(lm)<16 or support(rm)<16:continue
                            for a in fallback_pool:
                                for b in fallback_pool:
                                    options.append(dict(kind='split',feature=n,threshold=threshold,
                                        left=dict(kind='leaf',arm=a,fit_parents=support(lm)),
                                        right=dict(kind='leaf',arm=b,fit_parents=support(rm)),missing_arm=self.fallback_arm))
                            self.counts['evidence_splits_scored']+=1
                tc=np.asarray(batch.tool_costs[t],float)
                tool_best=None
                reservation_cache={}
                for candidate in options:
                    reachable=tuple(sorted({candidate['arm']} if candidate['kind']=='leaf' else
                                          {candidate['left']['arm'],candidate['right']['arm']}))
                    if reachable not in reservation_cache:
                        reservation_cache[reachable]=np.array([self.cost.reservation(t,dict(zip(self.free_names,row)),reachable)<=budget for row in X])
                    valid=possible&reservation_cache[reachable]
                    if candidate['kind']=='leaf':
                        if support(valid)<16:continue
                        candidate['fit_parents']=support(valid)
                    else:
                        j=self.evidence_names[t].index(candidate['feature'])
                        lm=valid&(e[:,j]<=candidate['threshold']);rm=valid&(e[:,j]>candidate['threshold'])
                        if support(lm)<16 or support(rm)<16:continue
                        candidate['left']['fit_parents']=support(lm);candidate['right']['fit_parents']=support(rm)
                    actions=route_term(candidate,e,valid)
                    costs=C[np.arange(N),actions].copy();costs[valid]+=tc[valid]
                    candidate_node={'kind':'acquire','tool':t,'terminal':candidate,
                                    'reachable_arms':list(reachable),'fit_supported_parents':support(valid)}
                    key=rank(actions,costs,mask,2 if candidate['kind']=='leaf' else 4)
                    self.counts['branches_scored']+=1
                    if tool_best is None or key<tool_best[0]:tool_best=(key,candidate)
                    if winner is None or key<winner[0]:winner=(key,candidate_node)
                if stage_capture:staged_options[t]=[] if tool_best is None else [copy.deepcopy(tool_best[1])]
            if winner is None:
                node={'kind':'submit','terminal':{'kind':'leaf','arm':self.fallback_arm,'registered_fallback':True,'fit_parents':support(active)},'forced_tool_unavailable':True}
                actions=fallback_actions.copy();winner=(rank(actions,C[np.arange(N),actions],mask,1),node)
            return winner
        current_tool=None
        whole=np.ones(N,bool);score,node=branch(whole)
        stage_capture=False
        if allow_free_split:
            for j,n in enumerate(self.free_names):
                for threshold in self.free_thresholds[n]:
                    left=whole&np.isfinite(X[:,j])&(X[:,j]<=threshold);right=whole&np.isfinite(X[:,j])&(X[:,j]>threshold)
                    # Typed missing free inputs go to registered fallback, never fabricated zero.
                    if support(left&~full)<16 or support(right&~full)<16:continue
                    ls,ln=branch(left);rs,rn=branch(right)
                    missing=~(left|right);ma=fallback_actions.copy()
                    ms=rank(ma,C[np.arange(N),ma],missing,0)
                    key=(ls[0]+rs[0]+ms[0],ls[1]+rs[1]+ms[1],ls[2]+rs[2]+1,ls[3]+rs[3]+ms[3])
                    self.counts['free_splits_scored']+=1
                    if key<score:score,node=key,dict(kind='free_split',feature=n,threshold=threshold,left=ln,right=rn)
        self.tree=node;self.fit_objective=score[0];self.fit_cost=score[1]
        self.allow_free_split=allow_free_split;self.forced_tool=forced_tool;self.tools=tuple(tools)
        self.staged=bool(staged);self.staged_terminals=staged_options if staged else {}
        return self

    def _fallback(self, features, budget):
        for arm in self.fallback_order:
            if self.cost.action_estimate(arm,features)<=budget:return arm
        return min(range(5),key=lambda arm:(self.cost.action_estimate(arm,features),arm!=self.reference_arm,arm))

    def decide(self,visible_state,acquired_evidence=None,remaining_budget=None):
        if not isinstance(visible_state,VisibleState):raise TypeError('Typed VisibleState required; no offline supervision row')
        if set(visible_state.features)!=set(self.free_names):raise ValueError('Exact visible feature whitelist required')
        budget=self.budget if remaining_budget is None else float(remaining_budget)
        if not np.isfinite(budget) or budget<0:raise ValueError('Invalid remaining budget')
        def submit(a,reason):
            required=self.cost.action_estimate(a,visible_state.features)
            return dict(kind='submit',arm=ARMS[a],action=a,reason=reason,tool=None,
                        estimated_final_seconds=required,total_budget_unmet=required>budget,
                        stopped_acquisition=True,policy_hash=self.frozen_hash)
        fallback=self._fallback(visible_state.features,budget)
        if visible_state.fully_observed:return submit(0,'complete_target_KEEP')
        node=self.tree
        if node['kind']=='free_split':
            value=visible_state.features[node['feature']]
            if value is None or not np.isfinite(value):return submit(fallback,'missing_free_feature_fallback')
            node=node['left'] if value<=node['threshold'] else node['right']
        if node['kind']=='submit':
            if acquired_evidence is not None:raise ValueError('Unexpected unpurchased evidence')
            if node['terminal'].get('registered_fallback'):return submit(fallback,'registered_support_fallback')
            a=node['terminal']['arm']
            return submit(a if self.cost.action_estimate(a,visible_state.features)<=budget else fallback,'policy_STOP' if self.cost.action_estimate(a,visible_state.features)<=budget else 'budget_fallback')
        tool=node['tool']
        if acquired_evidence is None:
            if not visible_state.applicable.get(tool,False):return submit(fallback,'unsupported_tool_fallback')
            estimate=self.cost.reservation(tool,visible_state.features,node['reachable_arms'])
            if estimate>budget:return submit(fallback,'budget_fallback')
            return dict(kind='acquire',tool=tool,reason='frozen_joint_path',estimated_branch_seconds=estimate,
                        stopped_acquisition=False,policy_hash=self.frozen_hash)
        if not isinstance(acquired_evidence,AcquiredEvidence) or acquired_evidence.tool!=tool:raise ValueError('Evidence tool identity mismatch')
        if acquired_evidence.status!='completed':return submit(fallback,'tool_failure_fallback')
        if set(acquired_evidence.features)!=set(self.evidence_names[tool]):raise ValueError('Exact purchased evidence whitelist required')
        values=acquired_evidence.features
        if any(v is None or not np.isfinite(v) for v in values.values()):return submit(fallback,'missing_evidence_fallback')
        a=_arm(node['terminal'],values)
        return submit(a if self.cost.action_estimate(a,visible_state.features)<=budget else fallback,'evidence_commit' if self.cost.action_estimate(a,visible_state.features)<=budget else 'post_tool_budget_fallback')

    def to_dict(self):
        return dict(version='v4.3.1-r4-JOINT',method_identity='generic cost-sensitive finite-grammar joint policy',
                    tree=self.tree,reference_arm=self.reference_arm,fallback_arm=self.fallback_arm,fallback_order=list(self.fallback_order),
                    free_names=list(self.free_names),evidence_names=self.evidence_names,
                    cost=self.cost.to_dict(),budget=self.budget,lambda_value=self.lambda_value,
                    objective=self.objective,training_parents=list(self.training_parents),
                    minimum_parents=16,counts=self.counts,fit_objective=self.fit_objective,fit_cost=self.fit_cost,
                    free_thresholds=self.free_thresholds,evidence_thresholds=self.evidence_thresholds,
                    allow_free_split=self.allow_free_split,forced_tool=self.forced_tool,tools=list(self.tools),
                    staged=self.staged,staged_terminals=self.staged_terminals)

    @property
    def frozen_hash(self):
        return hashlib.sha256(json.dumps(self.to_dict(),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
