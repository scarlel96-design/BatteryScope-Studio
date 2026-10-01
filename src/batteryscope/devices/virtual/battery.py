"""Small energy model for pipeline tests, not a physical battery predictor."""

from dataclasses import dataclass


@dataclass
class VirtualBattery:
    nominal_voltage_v: float = 20.0
    maximum_energy_wh: float = 72.0
    remaining_energy_wh: float = 72.0
    effective_resistance_ohm: float = 0.02
    cutoff_voltage_v: float = 14.0

    def draw(self, current_a: float, duration_s: float) -> tuple[float, float]:
        if current_a < 0 or duration_s < 0:
            raise ValueError("negative draw")
        voltage_v = max(0.0, self.nominal_voltage_v - current_a * self.effective_resistance_ohm)
        if self.remaining_energy_wh <= 0 or voltage_v <= self.cutoff_voltage_v:
            return 0.0, 0.0
        consumed_wh = voltage_v * current_a * duration_s / 3600
        self.remaining_energy_wh = max(0.0, self.remaining_energy_wh - consumed_wh)
        return voltage_v, current_a
