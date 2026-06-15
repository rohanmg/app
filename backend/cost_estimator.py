"""Approximate monthly AWS cost estimator based on detected services."""
from typing import Dict, List
from drawio_parser import AWS_SERVICE_MAP


def estimate_costs(service_counts: Dict[str, int]) -> List[Dict]:
    """Returns list of dicts: {name, category, count, monthly_cost_usd}."""
    out = []
    # invert AWS_SERVICE_MAP to get canonical -> (category, cost)
    canonical_meta = {}
    for _key, (canonical, category, cost) in AWS_SERVICE_MAP.items():
        if canonical not in canonical_meta:
            canonical_meta[canonical] = (category, cost)

    for name, count in service_counts.items():
        category, unit_cost = canonical_meta.get(name, ("other", 10.0))
        out.append({
            "name": name,
            "category": category,
            "count": count,
            "monthly_cost_usd": round(unit_cost * count, 2),
        })
    return sorted(out, key=lambda x: -x["monthly_cost_usd"])


def total_cost(items: List[Dict]) -> float:
    return round(sum(i["monthly_cost_usd"] for i in items), 2)
