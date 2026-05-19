"""
CameraFootprintManager — Real-time camera footprint calculation and map update.

Calculates the ground area visible in a drone's camera feed based on:
- GPS position (lat, lon, alt)
- Vehicle attitude (roll, pitch, yaw)
- Gimbal/pod tilt angle (pitch)
- Camera field of view (HFOV, VFOV)

Projects a "viewing trapezoid" polygon onto the map showing exactly
which parts of the ground are currently visible in the camera feed.

Usage:
    manager = CameraFootprintManager(map_widget)
    # Connect telemetry signals to the manager's update methods
    position_signal.connect(manager.update_position)
    attitude_signal.connect(manager.update_attitude)
    mount_signal.connect(manager.update_mount_angles)
"""

import math
from PySide6.QtCore import QObject, Signal


class CameraFootprintConfig:
    """Configuration for camera footprint calculation."""

    def __init__(
        self,
        hfov_deg=82.1,   # DJI Mini 3 spec — override per-drone if using a different sensor
        vfov_deg=63.1,   # DJI Mini 3 spec — 4:3 sensor at 2.7K
        earth_radius_m=6378137.0,
        min_area_m2=1.0,
    ):
        """
        Parameters:
            hfov_deg: Horizontal field of view in degrees (default 60°)
            vfov_deg: Vertical field of view in degrees (default 45°)
            earth_radius_m: Earth radius for geodesic calculations
            min_area_m2: Minimum footprint area to display (filters noise)
        """
        self.hfov_deg = hfov_deg
        self.vfov_deg = vfov_deg
        self.earth_radius_m = earth_radius_m
        self.min_area_m2 = min_area_m2


class CameraFootprintManager(QObject):
    """Manages real-time camera footprint calculation and map rendering.

    Signals:
        footprint_updated: Emitted when a drone's footprint polygon is calculated
            Args: (node_id, sysid, corners: list[[lat, lon]], area_m2: float)
        footprint_cleared: Emitted when a drone's footprint should be removed
            Args: (node_id, sysid)
    """

    footprint_updated = Signal(int, int, list, float, float)  # node_id, sysid, corners, area_m2, heading
    footprint_cleared = Signal(int, int)  # node_id, sysid
    enabled_changed = Signal(bool)  # enabled
    footprint_state_changed = Signal(int, int, bool)  # node_id, sysid, is_active

    def __init__(self, map_widget, config=None):
        """
        Parameters:
            map_widget: SatelliteMapWidget instance for rendering footprints
            config: CameraFootprintConfig instance (uses defaults if None)
        """
        super().__init__()
        self._map_widget = map_widget
        self._config = config or CameraFootprintConfig()

        # Cached telemetry state per drone
        # Keys: (node_id, sysid)
        self._position = {}   # { (nid, sid): (lat, lon, alt) }
        self._attitude = {}   # { (nid, sid): (roll, pitch, yaw) }
        self._mount = {}      # { (nid, sid): (gimbal_pitch_deg, gimbal_yaw_deg) }

        # Visibility control
        self._enabled = False
        
        # Per-drone footprint enable flags
        self._drone_footprints = {}  # {(nid, sid): True/False}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_enabled(self, enabled):
        """Enable or disable footprint calculation and display."""
        if self._enabled == bool(enabled):
            return  # No change
        self._enabled = enabled
        self.enabled_changed.emit(enabled)
        if not enabled:
            # Clear all footprints when disabled
            self.clear_all()

    def is_enabled(self):
        return self._enabled
    
    def enable_drone_footprint(self, node_id, sysid):
        """Enable footprint display for a specific drone."""
        self._drone_footprints[(node_id, sysid)] = True
        # Ensure global enabled state is on
        if not self._enabled:
            self._enabled = True
            self.enabled_changed.emit(True)
        # Emit per-drone state change signal
        self.footprint_state_changed.emit(node_id, sysid, True)
        # Trigger calculation
        self._calculate_and_emit(node_id, sysid)

    def disable_drone_footprint(self, node_id, sysid):
        """Disable footprint display for a specific drone."""
        was_active = self._drone_footprints.pop((node_id, sysid), None)
        if was_active:
            self.footprint_state_changed.emit(node_id, sysid, False)
        self._map_widget.clear_footprint(node_id, sysid)
        self.footprint_cleared.emit(node_id, sysid)
        
        # Check if any drones still have footprints enabled
        if not self._drone_footprints and self._enabled:
            # Optional: disable global if no drones have footprints
            pass  # Keep global enabled in case new drones are added

    def is_drone_footprint_active(self, node_id, sysid):
        """Check if footprint is enabled for a specific drone."""
        return self._drone_footprints.get((node_id, sysid), False)
    
    def set_manual_position(self, node_id, sysid, lat, lon, alt):
        """Set a manual position for footprint calculation (e.g., USB webcam).
        
        This allows creating footprints without drone telemetry by accepting
        manually entered coordinates.
        
        Parameters:
            node_id: Identifier for the camera/source
            sysid: System ID
            lat: Latitude in degrees
            lon: Longitude in degrees
            alt: Altitude above ground in meters
        """
        if not self._is_valid_position(lat, lon):
            return False
        self._position[(node_id, sysid)] = (lat, lon, alt)
        if self._enabled and self.is_drone_footprint_active(node_id, sysid):
            self._calculate_and_emit(node_id, sysid)
        return True
    
    def clear_manual_position(self, node_id, sysid):
        """Clear manually set position for a camera/source."""
        self._position.pop((node_id, sysid), None)

    def update_position(self, node_id, sysid, lat, lon, alt):
        """Update cached position for a drone."""
        if not self._is_valid_position(lat, lon):
            return
        self._position[(node_id, sysid)] = (lat, lon, alt)
        if self._enabled:
            self._calculate_and_emit(node_id, sysid)

    def update_attitude(self, node_id, sysid, roll, pitch, yaw):
        """Update cached vehicle attitude for a drone."""
        self._attitude[(node_id, sysid)] = (roll, pitch, yaw)
        if self._enabled:
            self._calculate_and_emit(node_id, sysid)

    def update_mount_angles(self, node_id, sysid, gimbal_pitch, gimbal_yaw=None):
        """Update cached gimbal/mount angles for a drone.

        Parameters:
            node_id: Drone node ID
            sysid: Drone system ID
            gimbal_pitch: Gimbal pitch angle in degrees (negative = down)
            gimbal_yaw: Gimbal yaw angle in degrees (optional)
        """
        self._mount[(node_id, sysid)] = (gimbal_pitch, gimbal_yaw if gimbal_yaw is not None else 0.0)
        if self._enabled:
            self._calculate_and_emit(node_id, sysid)

    def clear_drone(self, node_id, sysid):
        """Clear footprint for a specific drone."""
        self._position.pop((node_id, sysid), None)
        self._attitude.pop((node_id, sysid), None)
        self._mount.pop((node_id, sysid), None)
        self._map_widget.clear_footprint(node_id, sysid)
        self.footprint_cleared.emit(node_id, sysid)

    def clear_all(self):
        """Clear all footprints."""
        self._position.clear()
        self._attitude.clear()
        self._mount.clear()
        self._map_widget.clear_all_footprints()

    # ------------------------------------------------------------------
    # Core calculation
    # ------------------------------------------------------------------

    def _calculate_and_emit(self, node_id, sysid):
        """Calculate footprint from cached telemetry and emit signal."""
        if not self._enabled:
            return
        if not self.is_drone_footprint_active(node_id, sysid):
            return
            
        pos = self._position.get((node_id, sysid))
        if pos is None:
            print(f"[FOOTPRINT DEBUG] No position for drone {node_id}:{sysid}, cannot calculate")
            return
            
        corners = self.calculate_footprint(node_id, sysid)
        if corners is None:
            print(f"[FOOTPRINT DEBUG] calculate_footprint returned None for {node_id}:{sysid}")
            return
            
        area = self.calculate_footprint_area(corners)
        if area < self._config.min_area_m2:
            print(f"[FOOTPRINT DEBUG] Area {area:.1f} < min_area_m2, skipping")
            return
        
        _, _, yaw = self._attitude.get((node_id, sysid), (0.0, 0.0, 0.0))
        print(f"[FOOTPRINT DEBUG] Emitting footprint for {node_id}:{sysid}: corners={len(corners)}, area={area:.1f}m²")
        self.footprint_updated.emit(node_id, sysid, corners, area, yaw)

    def calculate_footprint(self, node_id, sysid):
        """Calculate the camera footprint polygon corners for a drone.

        Works with partial telemetry:
        - Position only (lat, lon, alt): Uses default attitude (0, 0, 0) and straight-down gimbal
        - Position + attitude: Uses full calculation
        - Position + attitude + mount: Full calculation with gimbal data

        Returns:
            List of [lat, lon] pairs forming the viewing trapezoid polygon,
            or None if position data is unavailable.
        """
        pos = self._position.get((node_id, sysid))

        if pos is None:
            return None

        lat, lon, alt = pos
        
        # Default attitude if not available (for USB webcam or missing telemetry)
        att = self._attitude.get((node_id, sysid))
        if att is not None:
            roll, pitch, yaw = att
        else:
            # Default: level vehicle, heading north
            roll, pitch, yaw = 0.0, 0.0, 0.0

        # Get gimbal pitch; default to straight-down if not available
        mount = self._mount.get((node_id, sysid))
        if mount and mount[0] is not None:
            gimbal_pitch = mount[0]
        else:
            # Assume straight-down gimbal when no mount data available
            gimbal_pitch = -90.0  # degrees (straight down)

        return self._compute_footprint_corners(
            lat, lon, alt, roll, pitch, yaw, gimbal_pitch
        )

    def calculate_target_coordinate(self, node_id, sysid, x_pct, y_pct):
        """Calculate the real-world GPS coordinate of a target detected at (x_pct, y_pct)
        in the video frame, using the drone's current telemetry and raycasting.

        Parameters:
            node_id: Drone node ID
            sysid: Drone system ID
            x_pct: Horizontal position in frame as fraction 0.0 (left) to 1.0 (right)
            y_pct: Vertical position in frame as fraction 0.0 (top) to 1.0 (bottom)

        Returns:
            (lat, lon) tuple of the target's real-world position, or None if unavailable.
        """
        pos = self._position.get((node_id, sysid))
        if pos is None:
            return None

        lat, lon, alt = pos

        att = self._attitude.get((node_id, sysid))
        roll, pitch, yaw = att if att is not None else (0.0, 0.0, 0.0)

        mount = self._mount.get((node_id, sysid))
        gimbal_pitch = mount[0] if (mount and mount[0] is not None) else -90.0

        R = self._config.earth_radius_m
        hfov = math.radians(self._config.hfov_deg)
        vfov = math.radians(self._config.vfov_deg)

        # Convert pixel percentages to signed angular offsets from center
        # x_pct=0.5, y_pct=0.5 → 0,0 (dead centre)
        h_offset_sign = (x_pct - 0.5) * 2.0   # -1=far left, +1=far right
        v_offset_sign = (y_pct - 0.5) * 2.0   # -1=top, +1=bottom

        # For near-nadir cameras use a direct, geometrically clean calculation.
        # _pixel_direction has body-frame sign issues at -90° that cause the
        # ground-intersection test to fail (ray appears to point upward in ENU).
        if abs(gimbal_pitch + 90.0) < 10.0:
            return self._calculate_nadir_target(lat, lon, alt, yaw, x_pct, y_pct)

        # Calculate the exact ray direction through this specific pixel
        target_ray = self._pixel_direction(
            roll, pitch, yaw, gimbal_pitch,
            h_offset_sign, v_offset_sign
        )

        if target_ray[2] >= 0:
            # Ray points upward — target is above horizon (invalid)
            # Fall back to nadir calculation rather than failing silently
            return self._calculate_nadir_target(lat, lon, alt, yaw, x_pct, y_pct)

        # Intersect the ray with the ground plane (z=0 in ENU, origin=drone)
        # Drone is at altitude `alt` above ground, so cam_pos z = alt
        t = alt / (-target_ray[2])
        east  = t * target_ray[0]
        north = t * target_ray[1]

        # Convert ENU offsets (metres) to lat/lon
        lat_rad = math.radians(lat)
        target_lat = lat + (north / R) * (180.0 / math.pi)
        target_lon = lon + (east / (R * math.cos(lat_rad))) * (180.0 / math.pi)

        return target_lat, target_lon

    def _calculate_nadir_target(self, lat, lon, alt, yaw_deg, x_pct, y_pct):
        """Direct pixel→GPS calculation for nadir (straight-down) cameras.

        Avoids the body-frame sign convention issues in _pixel_direction.
        Uses a simple geometric projection from altitude and FOV.

        Parameters:
            lat, lon: Drone position in degrees
            alt: Altitude above ground in metres
            yaw_deg: Drone heading in degrees (0=north)
            x_pct: Horizontal fraction 0.0 (left) to 1.0 (right)
            y_pct: Vertical fraction 0.0 (top) to 1.0 (bottom)

        Returns:
            (lat, lon) of the target, or None if altitude is unavailable.
        """
        if alt is None or alt <= 0:
            return None

        R = self._config.earth_radius_m
        hfov_half = math.radians(self._config.hfov_deg) / 2.0
        vfov_half = math.radians(self._config.vfov_deg) / 2.0

        # cx/cy: signed [-1, +1] offsets from frame centre
        cx = (x_pct - 0.5) * 2.0   # -1=left edge, +1=right edge
        cy = (y_pct - 0.5) * 2.0   # -1=top edge,  +1=bottom edge

        # Ground offsets in camera-frame (camera right = +cx, camera forward = -cy)
        # Image y=0 is the top of frame = "forward" for a nadir camera pointing north
        cam_right_m  =  cx * alt * math.tan(hfov_half)
        cam_fwd_m    = -cy * alt * math.tan(vfov_half)   # -cy: top of frame = forward

        # Rotate camera offsets by drone heading into geographic ENU
        yaw_rad = math.radians(yaw_deg)
        east  = cam_right_m * math.cos(yaw_rad) + cam_fwd_m * (-math.sin(yaw_rad))
        north = cam_right_m * math.sin(yaw_rad) + cam_fwd_m *   math.cos(yaw_rad)

        lat_rad = math.radians(lat)
        target_lat = lat + (north / R) * (180.0 / math.pi)
        target_lon = lon + (east / (R * math.cos(lat_rad))) * (180.0 / math.pi)

        return target_lat, target_lon

    def _pixel_direction(self, roll, pitch, yaw, gimbal_pitch_deg, sign_h, sign_v):
        """Like _corner_direction but uses fractional signed offsets instead of ±1.

        sign_h/sign_v are fractions in [-1, 1]:
          (0, 0) = dead centre of frame
          (-1,-1) = top-left corner
          (+1,+1) = bottom-right corner
        """
        hfov = math.radians(self._config.hfov_deg) / 2.0
        vfov = math.radians(self._config.vfov_deg) / 2.0

        gp_rad   = math.radians(gimbal_pitch_deg)
        cos_gp   = math.cos(gp_rad)
        sin_gp   = math.sin(gp_rad)

        center_body   = [cos_gp, 0.0, -sin_gp]
        cam_up_body   = [sin_gp, 0.0,  cos_gp]

        cam_right_body = [
            center_body[1] * cam_up_body[2] - center_body[2] * cam_up_body[1],
            center_body[2] * cam_up_body[0] - center_body[0] * cam_up_body[2],
            center_body[0] * cam_up_body[1] - center_body[1] * cam_up_body[0]
        ]
        norm_right = math.sqrt(sum(c**2 for c in cam_right_body))
        if norm_right > 0:
            cam_right_body = [c / norm_right for c in cam_right_body]

        tan_h = math.tan(sign_h * hfov)
        tan_v = math.tan(sign_v * vfov)

        ray_body = [
            center_body[0] + tan_h * cam_right_body[0] + tan_v * cam_up_body[0],
            center_body[1] + tan_h * cam_right_body[1] + tan_v * cam_up_body[1],
            center_body[2] + tan_h * cam_right_body[2] + tan_v * cam_up_body[2],
        ]

        norm = math.sqrt(sum(c**2 for c in ray_body))
        if norm == 0:
            return [0.0, 0.0, -1.0]
        ray_body = [c / norm for c in ray_body]

        # Rotate body → ENU (roll → pitch → yaw)
        cos_r, sin_r = math.cos(math.radians(roll)),  math.sin(math.radians(roll))
        cos_p, sin_p = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
        cos_y, sin_y = math.cos(math.radians(yaw)),   math.sin(math.radians(yaw))

        x1 = ray_body[0]
        y1 = cos_r * ray_body[1] - sin_r * ray_body[2]
        z1 = sin_r * ray_body[1] + cos_r * ray_body[2]

        x2 =  cos_p * x1 + sin_p * z1
        y2 = y1
        z2 = -sin_p * x1 + cos_p * z1

        enu_x = cos_y * x2 - sin_y * y2
        enu_y = sin_y * x2 + cos_y * y2
        enu_z = z2

        return [enu_x, enu_y, enu_z]

    def _compute_footprint_corners(self, lat, lon, alt, roll, pitch, yaw, gimbal_pitch_deg):
        """Compute the four corners using the centralized geo_math engine."""
        from core.geo_math import calculate_footprint
        
        # Use the hardened projection engine that handles absolute gimbals
        corners = calculate_footprint(
            drone_lat=lat,
            drone_lon=lon,
            drone_alt=alt,
            roll=roll,
            pitch=pitch,
            yaw=yaw,
            gimbal_pitch=gimbal_pitch_deg,
            fov_h=self._config.hfov_deg,
            fov_v=self._config.vfov_deg
        )
        
        if not corners:
            return None
            
        # Convert tuples to lists for JSON compatibility
        return [[c[0], c[1]] for c in corners]

    def calculate_footprint_area(self, corners):
        """Calculate area using the centralized geo_math engine."""
        from core.geo_math import footprint_area
        return footprint_area(corners)

    @staticmethod
    def _is_valid_position(lat, lon):
        """Check if lat/lon values are valid."""
        if lat is None or lon is None:
            return False
        if not math.isfinite(lat) or not math.isfinite(lon):
            return False
        if abs(lat) > 90.0 or abs(lon) > 180.0:
            return False
        return True
