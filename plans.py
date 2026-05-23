"""Definición de planes SaaS — features, límites y precios.

Cambios en estos valores requieren además:
- Actualizar el frontend de pricing (static/pricing.html).
- Si cambia el precio, crear preapproval plans nuevos en Mercado Pago.
"""
from typing import Any, Dict


# Status considerados "el plan está vigente y se puede usar".
ACTIVE_STATUSES = {"active", "trialing"}

PLANS: Dict[str, Dict[str, Any]] = {
    "free": {
        "label": "Free",
        "price_clp": 0,
        "max_opps_per_day": 20,
        "max_contacts": 50,
        "ai_matching": False,
        "exports": False,
    },
    "pro": {
        "label": "Pro",
        "price_clp": 29000,
        "max_opps_per_day": 500,
        "max_contacts": 2000,
        "ai_matching": True,
        "exports": True,
    },
    "team": {
        "label": "Team",
        "price_clp": 89000,
        "max_opps_per_day": 9999,
        "max_contacts": 99999,
        "ai_matching": True,
        "exports": True,
    },
}


def features_for(plan_name: str) -> Dict[str, Any]:
    """Devuelve el dict de features para un plan; defaultea a free si no existe."""
    return PLANS.get(plan_name, PLANS["free"])


def plan_is_active(status: str) -> bool:
    return status in ACTIVE_STATUSES
