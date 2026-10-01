"""Extensible deterministic fault scenarios."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioEffect:
    voltage_multiplier: float = 1.0
    disconnect: bool = False
    data_gap: bool = False
    sensor_warning: bool = False
    load_failure: bool = False
    cutoff: bool = False
    pd_renegotiation: bool = False


ScenarioFactory = Callable[[int], ScenarioEffect]


def _active_at(sequence: int, start: int = 3) -> bool:
    return sequence >= start


SCENARIOS: dict[str, ScenarioFactory] = {
    "normal": lambda _: ScenarioEffect(),
    "voltage_sag": lambda n: ScenarioEffect(voltage_multiplier=0.88 if _active_at(n) else 1.0),
    "pd_renegotiation": lambda n: ScenarioEffect(pd_renegotiation=n == 3),
    "unexpected_disconnect": lambda n: ScenarioEffect(disconnect=n == 3),
    "sensor_disagreement": lambda n: ScenarioEffect(sensor_warning=_active_at(n)),
    "load_failure": lambda n: ScenarioEffect(load_failure=n == 3),
    "data_gap": lambda n: ScenarioEffect(data_gap=n == 3),
    "unexpected_cutoff": lambda n: ScenarioEffect(cutoff=n == 3),
}


class FaultScenarioRegistry:
    def __init__(self, initial: dict[str, ScenarioFactory] | None = None) -> None:
        self._factories = dict(initial or {})

    def register(self, name: str, factory: ScenarioFactory) -> None:
        if name in self._factories:
            raise ValueError(f"scenario already registered: {name}")
        self._factories[name] = factory

    def get(self, name: str) -> ScenarioFactory:
        return self._factories[name]

    def list(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


DEFAULT_SCENARIOS = FaultScenarioRegistry(SCENARIOS)


def register_scenario(name: str, factory: ScenarioFactory) -> None:
    DEFAULT_SCENARIOS.register(name, factory)
    SCENARIOS[name] = factory
