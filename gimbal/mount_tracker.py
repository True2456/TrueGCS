from dataclasses import dataclass
import time


@dataclass
class MountTrackerConfig:
    kp_yaw: float = 0.03
    kp_pitch: float = 0.03
    deadband_px: int = 12
    max_step_deg: float = 2.0
    min_pitch_deg: float = -45.0
    max_pitch_deg: float = 45.0
    min_yaw_deg: float = -90.0
    max_yaw_deg: float = 90.0
    invert_pitch: bool = True
    invert_yaw: bool = False
    update_hz: float = 15.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class MountTrackerController:
    """Reusable pixel-error to mount-angle controller for MAVLink mount control."""

    def __init__(self, cfg: MountTrackerConfig | None = None):
        self.cfg = cfg or MountTrackerConfig()
        self.pitch_deg = 0.0
        self.yaw_deg = 0.0
        self.enabled = False
        self._last_update = 0.0

    def reset(self) -> None:
        self.pitch_deg = 0.0
        self.yaw_deg = 0.0
        self._last_update = 0.0

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if not self.enabled:
            self.reset()

    def update(self, err_x: int, err_y: int) -> tuple[float, float] | None:
        if not self.enabled:
            return None

        now = time.time()
        min_interval = 1.0 / max(1.0, self.cfg.update_hz)
        if now - self._last_update < min_interval:
            return None
        self._last_update = now

        if abs(err_x) <= self.cfg.deadband_px and abs(err_y) <= self.cfg.deadband_px:
            return self.pitch_deg, self.yaw_deg

        sign_yaw = -1.0 if self.cfg.invert_yaw else 1.0
        sign_pitch = -1.0 if self.cfg.invert_pitch else 1.0

        yaw_step = sign_yaw * _clamp(err_x * self.cfg.kp_yaw, -self.cfg.max_step_deg, self.cfg.max_step_deg)
        pitch_step = sign_pitch * _clamp(err_y * self.cfg.kp_pitch, -self.cfg.max_step_deg, self.cfg.max_step_deg)

        self.yaw_deg = _clamp(self.yaw_deg + yaw_step, self.cfg.min_yaw_deg, self.cfg.max_yaw_deg)
        self.pitch_deg = _clamp(self.pitch_deg + pitch_step, self.cfg.min_pitch_deg, self.cfg.max_pitch_deg)
        return self.pitch_deg, self.yaw_deg
