from dataclasses import dataclass
from typing import Optional


@dataclass
class AssetOwnerDTO:
    """DTO for asset ownership display"""
    cik: str
    name: str
    weight: float
    shares: Optional[int]
    value: Optional[float]
