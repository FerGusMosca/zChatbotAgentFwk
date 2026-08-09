# crowd_transition_dto.py
"""
DTO for crowding tier transitions between two quarters
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class CrowdTransitionDTO:
    """DTO for one asset moving between crowding tiers across two periods"""
    rank: int
    cusip: str
    asset: str
    size_bucket: str

    from_tier: int
    to_tier: int
    tier_delta: int          # from_tier - to_tier  (positive = got more crowded)
    direction: str           # LOADING / UNLOADING

    from_owners: int
    to_owners: int
    owners_delta: int

    from_weight: float
    to_weight: float
    weight_delta_pct: Optional[float]

    from_crowd_score: float
    to_crowd_score: float
