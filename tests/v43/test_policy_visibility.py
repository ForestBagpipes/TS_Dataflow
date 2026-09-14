from introact_ts.v43.features import VisibleState, extract_available_features
from introact_ts.v43.acquisition import select_tool


def test_hidden_cache_is_not_a_policy_input():
    cache = {"residual": 100., "tsicl_cov": 2.}
    state = VisibleState()
    before = extract_available_features(state)
    costs = {"residual": 1., "tsicl_cov": 1., "history_probe": 1.}
    def value_model(features, tool):
        return (2. if tool == "residual" else 1.) + sum(v for v, missing in features if not missing)
    first = select_tool(state, value_model, costs, 2.)
    cache["residual"] = -1e9
    assert before == extract_available_features(state)
    assert first == select_tool(state, value_model, costs, 2.) == "residual"
    assert all(missing for _, missing in before)
    acquired = state.acquire("tsicl_cov", cache["tsicl_cov"])
    cache["tsicl_cov"] = 9999.
    assert extract_available_features(acquired)[1] == (2., False)
    assert extract_available_features(acquired)[0] == (None, True)
