"""Cost estimator that uses aws_pricing (curated + live bulk JSON cache)."""
from typing import Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from aws_pricing import get_price, category_for


async def estimate_costs(
    service_counts: Dict[str, int],
    region: str = "us-east-1",
    cache_col: Optional[AsyncIOMotorCollection] = None,
) -> List[Dict]:
    """Returns list of dicts: {name, category, count, unit_cost_usd, monthly_cost_usd, assumption, source}."""
    out: List[Dict] = []
    for name, count in service_counts.items():
        unit, assumption, source = await get_price(name, region, cache_col)
        out.append({
            "name": name,
            "category": category_for(name),
            "count": count,
            "unit_cost_usd": unit,
            "monthly_cost_usd": round(unit * count, 2),
            "assumption": assumption,
            "source": source,
        })
    return sorted(out, key=lambda x: -x["monthly_cost_usd"])


def total_cost(items: List[Dict]) -> float:
    return round(sum(i["monthly_cost_usd"] for i in items), 2)
