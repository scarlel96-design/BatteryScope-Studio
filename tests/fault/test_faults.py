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
