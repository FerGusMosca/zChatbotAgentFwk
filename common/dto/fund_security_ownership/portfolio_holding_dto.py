from dataclasses import dataclass
from typing import Optional


@dataclass
class PortfolioHoldingDTO:
    """DTO for portfolio holdings display"""
    cusip: str
    name: str
    ticker: Optional[str]
    weight: float
    shares: Optional[int]
    value: Optional[float]