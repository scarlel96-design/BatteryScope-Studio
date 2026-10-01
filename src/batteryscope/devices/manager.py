"""Capability-first device discovery and connection management."""

from batteryscope.core.events import Event, EventBus
from batteryscope.core.models import DeviceIdentity
from batteryscope.plugins.registry import PluginRegistry


class DeviceManager:
    def __init__(self, registry: PluginRegistry, bus: EventBus) -> None:
        self.registry = registry
        self.bus = bus
        self.devices: dict[str, object] = {}

    def discover(self) -> list[DeviceIdentity]:
        identities = []
        for manifest in self.registry.manifests():
            device = self.registry.create(manifest.plugin_id)
            identity = device.get_identity()
            self.devices[identity.device_id] = device
            identities.append(identity)
        return identities

    def connect(self, device_id: str) -> object:
        device = self.devices[device_id]
        device.connect()
        self.bus.publish(Event("DeviceConnected", device_id))
        return device

    def disconnect_all(self) -> None:
        first_error: Exception | None = None
        for device_id, device in self.devices.items():
            try:
                device.disconnect()
                self.bus.publish(Event("DeviceDisconnected", device_id))
            except Exception as error:  # noqa: BLE001 - disconnect remaining devices
                first_error = first_error or error
        if first_error is not None:
            raise first_error
