"""Manifest-based device plugin registry with factories behind a narrow API."""

from __future__ import annotations

from collections.abc import Callable

from batteryscope.core.models import PluginManifest
from batteryscope.devices.virtual.devices import VirtualC2, VirtualEBD


DeviceFactory = Callable[[], object]


class PluginRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[PluginManifest, DeviceFactory]] = {}

    def register(self, manifest: PluginManifest, factory: DeviceFactory) -> None:
        if manifest.plugin_id in self._entries:
            raise ValueError(f"duplicate plugin: {manifest.plugin_id}")
        probe = factory()
        capabilities = probe.get_capabilities()
        if set(manifest.capabilities) != set(capabilities.features):
            raise ValueError("plugin manifest capabilities disagree with driver")
        if "emergency_stop" in capabilities.features and not callable(getattr(probe, "emergency_stop", None)):
            raise ValueError("emergency_stop capability requires an implementation")
        self._entries[manifest.plugin_id] = manifest, factory

    def create(self, plugin_id: str) -> object:
        return self._entries[plugin_id][1]()

    def manifests(self) -> tuple[PluginManifest, ...]:
        return tuple(entry[0] for entry in self._entries.values())


def built_in_registry() -> PluginRegistry:
    registry = PluginRegistry()
    registry.register(PluginManifest(plugin_id="virtual.c2", name="Virtual C2", vendor="BatteryScope",
                                     version="0.1.0", supported_devices=("virtual:c2",),
                                     capabilities=("measurement.voltage", "measurement.current", "measurement.power"),
                                     minimum_app_version="0.1.0"), VirtualC2)
    registry.register(PluginManifest(plugin_id="virtual.ebd", name="Virtual EBD", vendor="BatteryScope",
                                     version="0.1.0", supported_devices=("virtual:ebd",),
                                     capabilities=("measurement.voltage", "measurement.current", "measurement.power",
                                                   "load.constant_current", "load.constant_power", "emergency_stop"),
                                     minimum_app_version="0.1.0"), VirtualEBD)
    return registry
