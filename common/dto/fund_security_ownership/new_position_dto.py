# new_position_dto.py
"""
DTO for assets that show up between two quarters (new institutional positions)
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class NewPositionDTO:
    """DTO for a brand-new (or re-entered) asset in the destination quarter"""
    rank: int
    cusip: str
    asset: str
    size_bucket: str

    to_owners: int
    to_weight: float
    to_crowd_score: float
    to_tier: int

    from_owners: int          # 0 when the asset did not exist in the base quarter
    is_brand_new: bool        # True  -> no node at all in the base quarter
