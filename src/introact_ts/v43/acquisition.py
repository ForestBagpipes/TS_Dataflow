"""Visible-state tool choice contract; fitting the value model remains pending."""
import math
from .features import TOOLS, extract_available_features
from .schemas import require


def select_tool(state, value_model, estimated_costs, remaining_budget, max_rounds=2):
    require(math.isfinite(remaining_budget) and remaining_budget >= 0, "invalid tool budget")
    if len(state.history) >= max_rounds:
        return None
    features = extract_available_features(state)
    best, best_value = None, 0.
    for tool in TOOLS:
        if tool in state.history:
            continue
        cost = estimated_costs[tool]
        require(math.isfinite(cost) and cost >= 0, "invalid cost estimate")
        if cost > remaining_budget:
            continue
        value = value_model(features, tool)
        require(math.isfinite(value), "invalid predicted tool value")
        if value > best_value:
            best, best_value = tool, value
    return best
