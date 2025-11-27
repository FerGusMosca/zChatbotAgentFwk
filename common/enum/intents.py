
# StrEnum backport para Python 3.10

from enum import Enum
from typing import List

class StrEnum(str, Enum):
    """StrEnum backport – funciona en Python 3.10"""
    def __str__(self) -> str:
        return str(self.value)

class Intent(StrEnum):
    BROAD = "broad_query"
    ENUMERATION = "enumeration_query"
    ANALYTICAL = "analytical_query"
    TEMPORAL = "temporal_query"
    SPECIFIC = "specific_query"
    FUZZY = "fuzzy_query"

    @classmethod
    def list_values(cls) -> List[str]:
        return [item.value for item in cls]