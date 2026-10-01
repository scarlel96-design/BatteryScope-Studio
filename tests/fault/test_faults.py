from datetime import UTC

import pytest

from batteryscope.core.events import EventBus
from batteryscope.core.models import QualityFlag
from batteryscope.devices.virtual.devices import LoadState, VirtualC2, VirtualEBD
from batteryscope.devices.virtual.scenarios import SCENARIOS
from batteryscope.safety.engine import SafetyEngine


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_scenario_is_registered(scenario: str) -> None:
    assert SCENARIOS[scenario](1) is not None


def test_disconnect_and_gap() -> None:
    c2 = VirtualC2(scenario="unexpected_disconnect")
    c2.connect()
    assert len(list(c2.samples(2))) == 2
    with pytest.raises(ConnectionError):
        list(c2.samples(1))
    assert c2.get_status() == "DISCONNECTED"
    gap = VirtualC2(scenario="data_gap")
    gap.connect()
    samples = list(gap.samples(3))
    assert QualityFlag.DATA_GAP in samples[-1].quality_flags
    assert samples[-1].sequence == 4


def test_load_failure_and_emergency_stop() -> None:
    ebd = VirtualEBD(scenario="load_failure")
    ebd.connect()
    ebd.set_constant_current(2)
    ebd.load_on()
    list(ebd.samples(3))
    assert ebd.state == LoadState.SAFE
    SafetyEngine(EventBus()).emergency_stop(ebd, "virtual-ebd")
    assert ebd.state == LoadState.SAFE


def test_faults_change_measurement_and_load_state() -> None:
    sag = VirtualC2(scenario="voltage_sag")
    sag.connect()
    voltages = [sample.voltage_v for sample in sag.samples(3)]
    assert voltages == [20.0, 20.0, 17.6]
    disagreement = VirtualC2(scenario="sensor_disagreement")
    disagreement.connect()
    assert QualityFlag.SENSOR_WARNING in list(disagreement.samples(3))[-1].quality_flags
    cutoff = VirtualEBD(scenario="unexpected_cutoff")
    cutoff.connect()
    cutoff.set_constant_current(2)
    cutoff.load_on()
    list(cutoff.samples(3))
    assert cutoff.state == LoadState.SAFE and not cutoff.load_enabled


def test_virtual_battery_stream_is_reproducible_for_same_seed() -> None:
    from datetime import datetime

    def stream() -> list[tuple[int, float, float, float, float, float]]:
        device = VirtualEBD(scenario="voltage_sag", seed=381992,
                            clock=lambda: (99, datetime(2026, 1, 1, tzinfo=UTC)))
        device.connect()
        device.set_constant_current(2)
        device.load_on()
        return [(item.sequence, item.voltage_v, item.current_a, item.power_w,
                 item.accumulated_ah, item.accumulated_wh) for item in device.samples(5)]

    assert stream() == stream()
