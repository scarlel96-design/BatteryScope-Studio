"""Read-only C2 Pro discovery skeleton. No product VID/PID or protocol is assumed."""

from __future__ import annotations

from batteryscope.core.models import (
    DeviceCapabilities,
    DeviceIdentity,
    SourceKind,
    SupportStatus,
)
from batteryscope.devices.base.contracts import NotVerifiedProtocolError


class C2ProDriver:
    @classmethod
    def discover(cls) -> list[DeviceIdentity]:
        # Generic USB inventory cannot identify a C2 Pro without verified identifiers.
        return []

    @staticmethod
    def usb_candidates() -> list[dict[str, str]]:
        import usb.core

        return [{"vendor_id": f"{device.idVendor:04x}", "product_id": f"{device.idProduct:04x}"}
                for device in usb.core.find(find_all=True)]

    def connect(self) -> None:
        raise NotVerifiedProtocolError("C2 Pro transport and protocol are UNVERIFIED")

    def disconnect(self) -> None:
        return None

    def get_identity(self) -> DeviceIdentity:
        return DeviceIdentity(device_id="physical:c2-pro-unverified", display_name="ALIENTEK C2 Pro",
                              kind=SourceKind.REAL, discovery_status=SupportStatus.PARTIAL,
                              telemetry_status=SupportStatus.UNVERIFIED, control_status=SupportStatus.NOT_IMPLEMENTED,
                              evidence=("generic OS USB enumeration only",))

    def get_capabilities(self) -> DeviceCapabilities:
        return DeviceCapabilities()

    def get_status(self) -> str:
        return "UNVERIFIED"

    def self_test(self) -> bool:
        return False

    def request_pdo(self, *args: object, **kwargs: object) -> None:
        raise NotVerifiedProtocolError("C2 Pro PD write protocol is UNVERIFIED")

    def request_pps(self, *args: object, **kwargs: object) -> None:
        raise NotVerifiedProtocolError("C2 Pro PPS write protocol is UNVERIFIED")

    def firmware_command(self, *args: object, **kwargs: object) -> None:
        raise NotVerifiedProtocolError("C2 Pro firmware command protocol is UNVERIFIED")
