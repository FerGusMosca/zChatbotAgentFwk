
# manager_holding_dto.py
"""
DTO for Manager Holdings - Anemic class for display purposes
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AssetDTO:
    """DTO for asset info"""
    cusip: str
    name: str
    ticker: Optional[str]
