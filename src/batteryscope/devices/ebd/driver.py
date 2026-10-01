"""EBD-A20H serial candidate skeleton; physical load commands are blocked."""

from __future__ import annotations

from serial.tools import list_ports

from batteryscope.core.models import DeviceCapabilities, DeviceIdentity, SourceKind, SupportStatus
from batteryscope.devices.base.contracts import NotVerifiedProtocolError


class EBDA20HDriver:
    @classmethod
    def discover(cls) -> list[DeviceIdentity]:
        return []  # A COM port alone does not identify this device.

    @staticmethod
    def serial_candidates() -> list[dict[str, str | None]]:
        return [{"port": port.device, "description": port.description,
                 "vendor_id": f"{port.vid:04x}" if port.vid is not None else None,
                 "product_id": f"{port.pid:04x}" if port.pid is not None else None}
                for port in list_ports.comports()]

    def connect(self) -> None:
        raise NotVerifiedProtocolError("EBD-A20H serial protocol is UNVERIFIED")

    def disconnect(self) -> None:
        return None

    def get_identity(self) -> DeviceIdentity:
        return DeviceIdentity(device_id="physical:ebd-a20h-unverified", display_name="ZKETECH EBD-A20H",
                              kind=SourceKind.REAL, discovery_status=SupportStatus.PARTIAL,
                              telemetry_status=SupportStatus.UNVERIFIED, control_status=SupportStatus.NOT_IMPLEMENTED,
                              evidence=("generic OS serial enumeration only",))

    def get_capabilities(self) -> DeviceCapabilities:
        return DeviceCapabilities()

    def get_status(self) -> str:
        return "UNVERIFIED"

    def self_test(self) -> bool:
        return False

    def send_load_command(self, payload: bytes) -> None:
        raise NotVerifiedProtocolError("EBD-A20H command frame is UNVERIFIED")

    def set_constant_current(self, current_a: float) -> None:
        raise NotVerifiedProtocolError("EBD-A20H CC frame is UNVERIFIED")

    def set_constant_power(self, power_w: float) -> None:
        raise NotVerifiedProtocolError("EBD-A20H CP frame is UNVERIFIED")

    def set_current(self, current_a: float) -> None:
        raise NotVerifiedProtocolError("EBD-A20H current frame is UNVERIFIED")

    def set_power(self, power_w: float) -> None:
        raise NotVerifiedProtocolError("EBD-A20H power frame is UNVERIFIED")

    def load_on(self) -> None:
        raise NotVerifiedProtocolError("EBD-A20H load-on frame is UNVERIFIED")

    def load_off(self) -> None:
        raise NotVerifiedProtocolError("EBD-A20H load-off frame is UNVERIFIED")

    def emergency_stop(self) -> None:
        raise NotVerifiedProtocolError("EBD-A20H stop frame is UNVERIFIED")
