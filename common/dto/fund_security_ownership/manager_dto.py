
# manager_holding_dto.py
"""
DTO for Manager Holdings - Anemic class for display purposes
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ManagerDTO:
    """DTO for manager info"""
    name: str