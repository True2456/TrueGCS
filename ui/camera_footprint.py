"""
ui/camera_footprint.py — Georeferenced Camera Footprint Manager

Manages real-time calculation of the camera footprint polygon from drone telemetry
(position, attitude, gimbal angles) and emits footprint data for map rendering.

This module is designed to work alongside existing video code without modification.
It receives telemetry updates via signals and calculates the ground projection of
the camera's field of view.

Usage:
    footprint_mgr = CameraFootprintManager()
    footprint_mgr.footprint_updated.connect(map_widget.update_footprint)

    # Connect telemetry signals
    telemetry.position_updated.connect(footprint_mgr.on_position_update)
    telemetry.attitude_updated.connect(footprint_mgr.on_attitude_update)
    # ... etc.

    # Toggle footprint display
    footprint_mgr.set_enabled(True)
"""

from PySide6.QtCore import QObject, Signal, QTimer
from core.geo_math import calculate_footprint, footprint_area


class DroneTelemetryState:
    """Holds the latest known state of a drone for footprint calculation."""

    def __init__(self, node_id, sysid):
        self.node_id = node_id
        self.sysid = sysid
        # Position (WGS84)
        self.lat = 0.0
        self.lon = 0.0
        self.alt_agl = 0.0  # Altitude above ground level (metres)
        # Attitude (NED convention, degrees)
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0
        # Gimbal angles (degrees)
        self.gimbal_pitch = -90.0  # Default: pointing straight down
        self.gimbal_yaw = 0.0
        # Camera specs (degrees)
        self.fov_h = 60.0
        self.fov_v = 45.0
        # Timestamp of last update
        self.last_update = 0.0

    def is_valid(self, stale_timeout=5.0):
        """Check if telemetry data is fresh enough for footprint calculation."""
        import time
        return self.last_update > 0 and (time.time() - self.last_update) < stale_timeout


class CameraFootprintManager(QObject):
    """Manages real-time camera footprint calculation for one or more drones.

    Signals:
        footprint_updated: Emitted when a new footprint polygon is calculated.
            Args: (node_id, sysid, corners, area_m2)
                - node_id, sysid: Drone identifiers
                - corners: List of (lat, lon) tuples or None
                - area_m2: Approximate ground area in m²
        enabled_changed: Emitted when footprint calculation is toggled.
            Args: (enabled: bool)
    """

    footprint_updated = Signal(int, int, object, float)  # node_id, sysid, corners, area_m2
    enabled_changed = Signal(bool)  # enabled

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = False
        self._drones = {}  # (node_id, sysid) -> DroneTelemetryState
        self._default_fov_h = 60.0
        self._default_fov_v = 45.0
        self._stale_timeout = 5.0

        # Timer for periodic footprint recalculation (when drone moves)
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(200)  # 5 Hz update rate
        self._update_timer.timeout.connect(self._on_timer_tick)
        self._last_calc_time = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_enabled(self):
        """Return whether footprint calculation is enabled."""
        return self._enabled

    def set_enabled(self, enabled):
        """Enable or disable footprint calculation."""
        if self._enabled != bool(enabled):
            self._enabled = bool(enabled)
            self.enabled_changed.emit(self._enabled)
            if self._enabled:
                self._update_timer.start()
            else:
                self._update_timer.stop()

    def set_default_fov(self, fov_h, fov_v):
        """Set default camera FOV values (degrees)."""
        self._default_fov_h = float(fov_h)
        self._default_fov_v = float(fov_v)

    def add_drone(self, node_id, sysid):
        """Register a drone for footprint tracking."""
        key = (node_id, sysid)
        if key not in self._drones:
            state = DroneTelemetryState(node_id, sysid)
            state.fov_h = self._default_fov_h
            state.fov_v = self._default_fov_v
            self._drones[key] = state

    def remove_drone(self, node_id, sysid):
        """Remove a drone from footprint tracking."""
        key = (node_id, sysid)
        if key in self._drones:
            del self._drones[key]

    def get_drone_state(self, node_id, sysid):
        """Get the telemetry state for a drone."""
        return self._drones.get((node_id, sysid))

    # ------------------------------------------------------------------
    # Telemetry Signal Handlers
    # ------------------------------------------------------------------

    def on_position_update(self, node_id, sysid, lat, lon, alt):
        """Handle position update signal from telemetry."""
        key = (node_id, sysid)
        if key not in self._drones:
            self.add_drone(node_id, sysid)

        state = self._drones[key]
        state.lat = float(lat)
        state.lon = float(lon)
        # Assume alt is AGL for footprint purposes; if MSL needed, override via separate signal
        state.alt_agl = float(alt)
        import time
        state.last_update = time.time()

    def on_attitude_update(self, node_id, sysid, roll, pitch, yaw):
        """Handle attitude update signal from telemetry."""
        key = (node_id, sysid)
        if key not in self._drones:
            return

        state = self._drones[key]
        state.roll = float(roll)
        state.pitch = float(pitch)
        state.yaw = float(yaw)
        import time
        state.last_update = time.time()

    def on_gimbal_update(self, node_id, sysid, gimbal_pitch, gimbal_yaw=None):
        """Handle gimbal angle update signal from telemetry.

        Parameters:
            node_id, sysid: Drone identifiers
            gimbal_pitch: Gimbal pitch in degrees (negative = down)
            gimbal_yaw: Gimbal yaw offset in degrees (optional, defaults to 0)
        """
        key = (node_id, sysid)
        if key not in self._drones:
            return

        state = self._drones[key]
        state.gimbal_pitch = float(gimbal_pitch)
        if gimbal_yaw is not None:
            state.gimbal_yaw = float(gimbal_yaw)
        import time
        state.last_update = time.time()

    def on_camera_fov_update(self, node_id, sysid, fov_h, fov_v):
        """Update camera FOV parameters for a drone."""
        key = (node_id, sysid)
        if key not in self._drones:
            return

        state = self._drones[key]
        state.fov_h = float(fov_h)
        state.fov_v = float(fov_v)

    # ------------------------------------------------------------------
    # Internal Timer Handler
    # ------------------------------------------------------------------

    def _on_timer_tick(self):
        """Periodically recalculate footprints for all active drones."""
        import time
        now = time.time()

        # Throttle: only recalculate every 100ms
        if now - self._last_calc_time < 0.1:
            return
        self._last_calc_time = now

        if not self._enabled:
            return

        for key, state in self._drones.items():
            if not state.is_valid(self._stale_timeout):
                continue

            self._calculate_footprint(state)

    # ------------------------------------------------------------------
    # Footprint Calculation
    # ------------------------------------------------------------------

    def _calculate_footprint(self, state):
        """Calculate the footprint polygon for a drone's telemetry state."""
        corners = calculate_footprint(
            drone_lat=state.lat,
            drone_lon=state.lon,
            drone_alt=max(state.alt_agl, 1.0),  # Minimum 1m to avoid division by zero
            roll=state.roll,
            pitch=state.pitch,
            yaw=state.yaw,
            gimbal_pitch=state.gimbal_pitch,
            gimbal_yaw=state.gimbal_yaw,
            fov_h=state.fov_h,
            fov_v=state.fov_v,
        )

        if corners is not None:
            area = footprint_area(corners)
        else:
            area = 0.0

        self.footprint_updated.emit(
            state.node_id,
            state.sysid,
            corners,
            area
        )

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clear_all(self):
        """Remove all tracked drones."""
        self._drones.clear()

    def cleanup(self):
        """Stop timer and clean up."""
        self._update_timer.stop()
        self.clear_all()
