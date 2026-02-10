
# manager_holding_dto.py
"""
DTO for Manager Holdings - Anemic class for display purposes
"""

from dataclasses import dataclass
from typing import Optional

@dataclass
class AssetStatsDTO:
    """DTO for asset aggregated stats"""
    total_owners: int
    total_weight: float
    crowd_score: float