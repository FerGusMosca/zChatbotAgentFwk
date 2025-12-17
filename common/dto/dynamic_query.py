import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class DynamicQueryDTO:
    is_dynamic: bool
    query: str
    chunks_folder: Optional[str] = None
