# period_stats_dto.py
"""
DTO for the pre-computed aggregate status of a period
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PeriodStatsDTO:
    """One row of the aggregates panel"""
    year: str
    quarter: str
    assets: int
    built: bool
    built_at: Optional[str] = None


@dataclass
class SizeBucketStatsDTO:
    """Crowding aggregated by size bucket for one period"""
    size_bucket: str
    assets: int
    avg_owners: float
    total_weight: float
    avg_crowd_score: float
    max_crowd_score: float
