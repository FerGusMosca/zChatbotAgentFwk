# manager_holding_dto.py
"""
DTO for Manager Holdings - Anemic class for display purposes
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class CrowdedTradeDTO:
    """DTO for crowded/capitulation trade display"""
    rank: int
    asset: str
    owners: int
    total_weight: float
    crowd_score: float