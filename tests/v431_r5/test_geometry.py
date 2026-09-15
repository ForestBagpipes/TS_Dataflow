import itertools
import numpy as np
from scipy.optimize import minimize
from introact_ts.v431_r5.geometry import project_scores, breakpoint_vectors, distance_bounds


def qp_projection(p, r, scale, weights):
    v = breakpoint_vectors(p, scale)
    if weights is None:
        points = v.reshape(-1,len(p))
    else:
        points = np.array([sum(weights[h]*v[h,j] for h,j in enumerate(indices))
                           for indices in itertools.product(range(len(p)), repeat=p.shape[1])])
    # Independent dense convex-combination QP for tiny test problems only.
    out = minimize(lambda q: .5*np.sum((q@points-r)**2),
                   np.ones(len(points))/len(points),
                   jac=lambda q: points@(q@points-r),
                   bounds=[(0,None)]*len(points),
                   constraints={'type':'eq','fun':lambda q:q.sum()-1,
                                'jac':lambda q:np.ones(len(q))}, method='SLSQP',
                   options={'ftol':1e-13,'maxiter':3000})
    assert out.success
    return out.x@points


def solve(p,r,weights=None,**kwargs):
    return project_scores(p,r,1.,weights,time_limit_seconds=10,max_iter=20000,**kwargs)


def test_analytic_zero_one_two():
    p=np.array([[0.],[1.],[2.]])
    v=breakpoint_vectors(p,1.)[0]
    np.testing.assert_allclose(v,[[0,-1,-2],[0,1,0],[0,1,2]])
    out=solve(p,np.array([0.,-1.,2.]))
    np.testing.assert_allclose(out.scores,[0,.6,1.2],atol=1e-7)
    assert out.converged and out.gap<=1e-8


def test_duplicate_predictions():
    p=np.array([[0.,1.],[2.,3.],[2.,3.]])
    out=solve(p,np.array([0.,2.,-2.]))
    assert out.scores[1]==out.scores[2]


def test_independent_qp_known_and_unknown():
    p=np.array([[0.,2.],[1.,-1.],[3.,.5]])
    r=np.array([0.,-2.,3.])
    for w in (None,np.array([.2,.8])):
        out=solve(p,r,w)
        expected=qp_projection(p,r,1.,w)
        np.testing.assert_allclose(out.scores,expected,atol=4e-4)
        assert np.sum((out.scores-expected)**2) <= 2*out.gap+1e-8
        assert out.gap < 1e-3


def test_true_gain_membership_and_gap_bound():
    p=np.array([[0.,2.],[1.,-1.],[3.,.5]])
    r=np.array([0.,-2.,3.])
    for w in (np.array([.2,.8]),np.array([0.,1.])):
        for y in (np.array([-8.,7.]),np.array([.4,-.2]),np.array([9.,-9.])):
            losses=np.abs(p-y)@w
            gain=losses[0]-losses
            for geometry_w in (None,w):
                np.testing.assert_allclose(qp_projection(p,gain,1.,geometry_w),gain,atol=1e-5)
                out=solve(p,r,geometry_w)
                assert np.sum((out.scores-gain)**2) <= np.sum((r-gain)**2)-np.sum((r-out.scores)**2)+2*out.gap+1e-8


def test_two_actions_reduce_to_interval():
    p=np.array([[0.,2.],[2.,1.]])
    for w in (None,np.array([.25,.75])):
        full=solve(p,np.array([0.,9.]),w)
        single=solve(p,np.array([0.,9.]),w,mode='single')
        np.testing.assert_allclose(full.scores,single.scores)


def test_pair_projection_and_simple_clip():
    p=np.array([[0.],[1.],[2.]])
    r=np.array([0.,-1.,2.])
    single=solve(p,r,mode='single')
    pair=solve(p,r,mode='pair')
    assert pair.converged
    assert np.max(np.abs(pair.scores[:,None]-pair.scores[None,:])-distance_bounds(p,1.))<1e-8
    np.testing.assert_allclose(pair.scores,[0.,0.,1.],atol=1e-7)
    np.testing.assert_array_equal(single.scores,r)


def test_unknown_mask_does_not_accept_label_mask():
    p=np.array([[0.,0.],[1.,10.]])
    unknown=solve(p,np.array([0.,8.]))
    known=solve(p,np.array([0.,8.]),np.array([1.,0.]))
    assert unknown.scores[1]==8 and known.scores[1]==1


def test_nonfinite_and_invalid_reference_rejected():
    for p,r,s in (([[0.],[np.nan]],[0,1],1),([[0.],[1.]],[1,1],1),([[0.],[1.]],[0,1],0),([[-1e308],[1e308]],[0,1],1)):
        out=project_scores(p,r,s)
        assert out.status=='failed' and not out.converged


def test_timeout_restores_previous_scores():
    previous=np.array([0.,.2,.3])
    out=project_scores([[0.],[1.],[2.]],[0.,-1.,2.],1.,time_limit_seconds=0,previous_scores=previous)
    assert out.timed_out and not out.converged
    np.testing.assert_array_equal(out.scores,previous)


def test_iteration_limit_gap_is_for_final_iterate():
    from introact_ts.v431_r5.geometry import _lmo
    p=np.array([[0.,2.],[1.,-1.],[3.,.5]])
    r=np.array([0.,-2.,3.])
    out=project_scores(p,r,1.,max_iter=1,time_limit_seconds=10,tolerance=0)
    gradient=out.scores-r
    expected=gradient@(out.scores-_lmo(breakpoint_vectors(p,1.),gradient,None))
    np.testing.assert_allclose(out.gap,expected)
    assert out.status=='iteration_limit' and not out.converged
