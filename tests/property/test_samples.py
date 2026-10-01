from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from batteryscope.core.config import AppConfig
from batteryscope.core.models import MeasurementSample, QualityFlag, SourceKind


@given(st.floats(allow_nan=True, allow_infinity=True, width=64))
def test_arbitrary_voltage_is_either_valid_or_rejected(value: float) -> None:
    data = {"timestamp_monotonic_ns": 1, "timestamp_utc": datetime.now(UTC), "sequence": 1,
            "source_device_id": "virtual:c2", "source_kind": SourceKind.SIMULATED,
            "voltage_v": value, "current_a": 1, "power_w": 1,
            "quality_flags": {QualityFlag.SIMULATED}}
    if value < 0 or not (-float("inf") < value < float("inf")):
        with pytest.raises(ValidationError):
            MeasurementSample(**data)
    else:
        assert MeasurementSample(**data).voltage_v == value


@given(st.integers(max_value=15))
def test_corrupt_queue_limit_is_rejected(value: int) -> None:
    with pytest.raises(ValidationError):
        AppConfig(acquisition_queue_limit=value)
