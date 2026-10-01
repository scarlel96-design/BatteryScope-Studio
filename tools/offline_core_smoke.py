"""Dependency-light core smoke for environments without the full lock install.

Run with a Python 3.12 interpreter that has Pydantic 2 installed.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from batteryscope.core.errors import StorageError
from batteryscope.core.events import EventBus
from batteryscope.core.models import DeviceCapabilities, SourceKind
from batteryscope.devices.base.contracts import NotVerifiedProtocolError
from batteryscope.devices.c2.driver import C2ProDriver
from batteryscope.devices.virtual.devices import VirtualC2, VirtualEBD
from batteryscope.safety.engine import LoadRequest, SafetyDenied, SafetyEngine
from batteryscope.safety.stop import StopPhase
from batteryscope.storage.session import SessionState, SessionStore


def main() -> None:
    safety = SafetyEngine(EventBus())
    try:
        safety.validate_requested_load(
            LoadRequest(mode="CP", power_w=1),
            DeviceCapabilities(features=frozenset({"load.constant_power"})), SourceKind.REAL,
        )
    except SafetyDenied:
        pass
    else:
        raise AssertionError("unknown physical limit accepted")

    c2 = C2ProDriver()
    try:
        c2.request_pdo(1)
    except NotVerifiedProtocolError:
        pass
    else:
        raise AssertionError("physical C2 write accepted")

    ebd = VirtualEBD()
    ebd.connect()
    ebd.set_constant_current(2)
    assert next(iter(ebd.samples(1))).current_a == 0
    ebd.load_on()
    assert next(iter(ebd.samples(1))).current_a > 0
    bus = EventBus()
    bus.subscribe("*", lambda _: (_ for _ in ()).throw(StorageError("disk full")))
    engine = SafetyEngine(bus)
    assert engine.emergency_stop(ebd, "virtual:ebd").phase == StopPhase.VERIFIED_OFF
    assert engine.emergency_stop(ebd, "virtual:ebd").already_safe
    assert not ebd.load_enabled and ebd.state.value == "SAFE"

    first = VirtualC2(scenario="voltage_sag", seed=381992)
    second = VirtualC2(scenario="voltage_sag", seed=381992)
    first.connect()
    second.connect()
    assert [x.voltage_v for x in first.samples(4)] == [x.voltage_v for x in second.samples(4)]

    root = Path("runtime") / f"offline-smoke-{uuid4().hex}"
    store = SessionStore(root)
    for _ in range(2):
        sid, path = store.create_session()
        store.transition(sid, path, SessionState.RUNNING)
        store.add_chunk(sid, "virtual:c2", "raw/same.parquet", 1, "0" * 64, 1, 1, 1, 1, 1)
    store.close()
    recovered = SessionStore(root)
    issues = recovered.recover_incomplete()
    assert [issue["kind"] for issue in issues] == ["INTERRUPTED", "INTERRUPTED"]
    assert recovered.connection.execute("SELECT count(*) FROM raw_chunks").fetchone()[0] == 2
    assert [row[0] for row in recovered.connection.execute("SELECT status FROM sessions")] == [
        "INCOMPLETE", "INCOMPLETE"
    ]
    recovered.close()
    print("offline core smoke PASS: unknown limit, physical guard, stop priority/idempotency, simulation, recovery")


if __name__ == "__main__":
    main()
