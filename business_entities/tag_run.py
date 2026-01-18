import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class TagRun:
    id: int
    report: str
    portfolio: str
    source: str
    rank_folder: str
    year: str
    quarter: str
    sec_processed:int
    tag_model: str
    doc_type: str
    tag_json: Optional[str] = None
    tag_file: Optional[str] = None
    status: str = "completed"
    creation_time: Optional[datetime] = None
    last_update_time: Optional[datetime] = None
    last_error: Optional[str] = None

    @property
    def run_date(self) -> str:
        """Formato legible para el frontend: 'YYYY-MM-DD HH:MM'"""
        if self.creation_time:
            return self.creation_time.strftime("%Y-%m-%d %H:%M")
        return "N/A"

    @property
    def tag_name(self)-> str:
        tag_name = "-"
        if self.tag_json is not None:
            try:
                tag_dict = json.loads(self.tag_json)
                if tag_dict is not None:
                    tag_name = "|".join(tag_dict.keys())
                    return tag_name
            except Exception as e:
                return "-"