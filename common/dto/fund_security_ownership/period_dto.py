
# manager_holding_dto.py
"""
DTO for Manager Holdings - Anemic class for display purposes
"""

from dataclasses import dataclass
from typing import Optional

@dataclass
class PeriodDTO:
    """DTO for available period"""
    year: str
    quarter: str