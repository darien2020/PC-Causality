"""Synthetic NDR dataset with a known causal DAG for testing the PC pipeline.

Ground-truth structure:
    contract_value -> csm_engagement
    csm_engagement -> expansion_revenue
    csm_engagement -> churn_risk        (negative effect)
    onboarding_score -> product_usage
    product_usage -> feature_adoption
    feature_adoption -> expansion_revenue
    support_tickets -> churn_risk
    expansion_revenue -> ndr
    churn_risk -> ndr                   (negative effect)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


GROUND_TRUTH_EDGES: list[tuple[str, str]] = [
    ("contract_value", "csm_engagement"),
    ("csm_engagement", "expansion_revenue"),
    ("csm_engagement", "churn_risk"),
    ("onboarding_score", "product_usage"),
    ("product_usage", "feature_adoption"),
    ("feature_adoption", "expansion_revenue"),
    ("support_tickets", "churn_risk"),
    ("expansion_revenue", "ndr"),
    ("churn_risk", "ndr"),
]


def generate(n: int = 2000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    contract_value = rng.lognormal(mean=10.5, sigma=0.8, size=n)
    onboarding_score = rng.normal(70, 15, size=n).clip(0, 100)
    support_tickets = rng.poisson(lam=3, size=n).astype(float)

    csm_engagement = (
        0.4 * _z(contract_value) + rng.normal(0, 0.6, n)
    )
    product_usage = (
        0.6 * _z(onboarding_score) + rng.normal(0, 0.5, n)
    )
    feature_adoption = (
        0.7 * product_usage + rng.normal(0, 0.4, n)
    )
    expansion_revenue = (
        0.5 * csm_engagement + 0.4 * feature_adoption + rng.normal(0, 0.5, n)
    )
    churn_risk = (
        0.6 * _z(support_tickets) - 0.4 * csm_engagement + rng.normal(0, 0.5, n)
    )
    ndr = (
        0.7 * expansion_revenue - 0.6 * churn_risk + rng.normal(0, 0.3, n)
    )

    return pd.DataFrame({
        "contract_value": contract_value,
        "onboarding_score": onboarding_score,
        "support_tickets": support_tickets,
        "csm_engagement": csm_engagement,
        "product_usage": product_usage,
        "feature_adoption": feature_adoption,
        "expansion_revenue": expansion_revenue,
        "churn_risk": churn_risk,
        "ndr": ndr,
    })


def _z(x: np.ndarray) -> np.ndarray:
    return (x - x.mean()) / x.std()
