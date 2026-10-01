"""Validated operational settings. Chunk values are provisional and benchmarkable."""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class BackpressurePolicy(StrEnum):
    BLOCK = "BLOCK"
    SPILL = "SPILL"
    FAIL_SAFE = "FAIL_SAFE"


class AppConfig(BaseModel):
    environment: Environment = Environment.DEVELOPMENT
    runtime_dir: Path = Path("runtime")
    acquisition_queue_limit: int = Field(default=8192, ge=16)
    queue_warning_fraction: float = Field(default=0.75, gt=0, lt=1)
    chunk_max_rows: int = Field(default=10000, ge=1)
    chunk_max_seconds: float = Field(default=60.0, gt=0)
    sample_interval_seconds: float = Field(default=0.02, gt=0)
    queue_full_timeout_seconds: float = Field(default=1.0, gt=0)
    backpressure_policy: BackpressurePolicy = BackpressurePolicy.FAIL_SAFE
    timestamp_gap_factor: float = Field(default=3.0, gt=1)
