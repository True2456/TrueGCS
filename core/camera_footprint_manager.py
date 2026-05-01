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
        hfov_deg=60.0,
        vfov_deg=45.0,
        earth_radius_m=6378137.0,
        min_area_m2=10.0,
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

    footprint_updated = Signal(int, int, list, float)  # node_id, sysid, corners, area_m2
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
            
        print(f"[FOOTPRINT DEBUG] Emitting footprint for {node_id}:{sysid}: corners={len(corners)}, area={area:.1f}m²")
        self.footprint_updated.emit(node_id, sysid, corners, area)

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

    def _compute_footprint_corners(self, lat, lon, alt, roll, pitch, yaw, gimbal_pitch_deg):
        """Compute the four corners of the camera footprint polygon.

        Uses a geometric ray-tracing model:
        1. Build the camera's center pointing vector in ENU frame from
           vehicle attitude and gimbal tilt
        2. Build the four corner vectors by adding FOV offsets
        3. Intersect each ray with the ground plane (z=0 in ENU)
        4. Convert intersection points to lat/lon

        For straight-down gimbal (-90°), uses a simplified rectangular model.

        Parameters:
            lat, lon, alt: Drone position (degrees, meters above ellipsoid)
            roll, pitch, yaw: Vehicle attitude in degrees (ENU frame)
            gimbal_pitch_deg: Gimbal pitch angle in degrees

        Returns:
            List of [lat, lon] pairs (corners in clockwise order) or None
        """
        R = self._config.earth_radius_m

        # Handle straight-down gimbal case specially
        if abs(gimbal_pitch_deg + 90.0) < 5.0:
            return self._compute_downward_footprint(lat, lon, alt)

        # Convert to radians
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)

        # Camera FOV half-angles
        hfov = math.radians(self._config.hfov_deg)
        vfov = math.radians(self._config.vfov_deg)

        # Ground plane is approximately horizontal at altitude alt
        # Camera position in local ENU frame (ENU origin = drone ground position)
        cam_pos = [0.0, 0.0, -alt]  # alt meters above ground (z is up)

        # Calculate corner rays and find ground intersections
        corners = []
        for sign_v in [-1, 1]:  # -1 = top, +1 = bottom
            for sign_h in [-1, 1]:  # -1 = left, +1 = right
                # Corner ray in ENU (relative to camera center)
                corner_ray = self._corner_direction(
                    roll, pitch, yaw, gimbal_pitch_deg, sign_h, sign_v
                )

                if corner_ray[2] >= 0:
                    # This corner doesn't hit the ground (pointing above horizon)
                    continue

                t_corner = -cam_pos[2] / corner_ray[2]
                c_east = t_corner * corner_ray[0]
                c_north = t_corner * corner_ray[1]

                # Convert to lat/lon
                c_lat = math.degrees(lat_rad) + (c_north / R) * (180.0 / math.pi)
                c_lon = math.degrees(lon_rad) + (c_east / (R * math.cos(math.radians(lat)))) * (180.0 / math.pi)

                corners.append([c_lat, c_lon])

        if len(corners) < 3:
            return None

        # Sort corners to form a proper polygon (counter-clockwise around center)
        center_lon = math.radians(lon)
        center_lat = math.radians(lat)
        corners.sort(key=lambda c: math.atan2(
            math.radians(c[1]) - center_lon,
            math.radians(c[0]) - center_lat
        ))

        return corners

    def _compute_downward_footprint(self, lat, lon, alt):
        """Compute footprint for straight-down camera view.

        Creates a rectangular footprint centered on the drone position,
        sized based on altitude and camera FOV.

        Parameters:
            lat, lon, alt: Drone position
            
        Returns:
            List of [lat, lon] pairs forming a rectangle
        """
        R = self._config.earth_radius_m
        
        # Calculate ground distance from altitude and FOV
        # For straight-down: half-width = alt * tan(hfov/2)
        hfov_half = math.radians(self._config.hfov_deg) / 2.0
        vfov_half = math.radians(self._config.vfov_deg) / 2.0
        
        # Ground distances in metres
        half_width_m = alt * math.tan(hfov_half) if alt > 0 else 50.0
        half_height_m = alt * math.tan(vfov_half) if alt > 0 else 50.0
        
        # Convert to lat/lon offsets
        d_lat = (half_height_m / R) * (180.0 / math.pi)
        d_lon = (half_width_m / (R * math.cos(math.radians(lat)))) * (180.0 / math.pi)
        
        # Create rectangle corners (clockwise from top-left)
        corners = [
            [lat + d_lat, lon - d_lon],  # Top-left (north-west)
            [lat + d_lat, lon + d_lon],  # Top-right (north-east)
            [lat - d_lat, lon + d_lon],  # Bottom-right (south-east)
            [lat - d_lat, lon - d_lon],  # Bottom-left (south-west)
        ]
        
        return corners

    def _corner_direction(self, roll, pitch, yaw, gimbal_pitch, sign_h, sign_v):
        """Calculate the direction vector for a camera FOV corner in ENU frame.

        Parameters:
            roll, pitch, yaw: Vehicle attitude in degrees
            gimbal_pitch: Gimbal pitch in degrees (negative = down)
            sign_h: -1 for left, +1 for right
            sign_v: -1 for top, +1 for bottom

        Returns:
            Normalized direction vector [east, north, up] in ENU frame
        """
        hfov = math.radians(self._config.hfov_deg) / 2.0
        vfov = math.radians(self._config.vfov_deg) / 2.0

        # Camera center direction in body frame (forward along +X)
        # Apply gimbal pitch first
        gp_rad = math.radians(gimbal_pitch)
        cos_gp = math.cos(gp_rad)
        sin_gp = math.sin(gp_rad)

        # Center direction after gimbal (body frame):
        # Gimbal pitch rotates around body Y axis
        # 0° = forward, -90° = straight down
        center_body = [cos_gp, 0.0, -sin_gp]

        # Camera up vector in body frame (after gimbal)
        # For a forward-looking camera, up is approximately +Z in body frame
        cam_up_body = [sin_gp, 0.0, cos_gp]

        # Camera right vector (cross product of direction and up)
        cam_right_body = [
            center_body[1] * cam_up_body[2] - center_body[2] * cam_up_body[1],
            center_body[2] * cam_up_body[0] - center_body[0] * cam_up_body[2],
            center_body[0] * cam_up_body[1] - center_body[1] * cam_up_body[0]
        ]

        # Normalize right vector
        norm_right = math.sqrt(sum(c ** 2 for c in cam_right_body))
        if norm_right > 0:
            cam_right_body = [c / norm_right for c in cam_right_body]

        # Corner direction in body frame
        # Combine center direction with horizontal and vertical offsets
        tan_h = math.tan(sign_h * hfov)
        tan_v = math.tan(sign_v * vfov)

        corner_body = [
            center_body[0] + tan_h * cam_right_body[0] + tan_v * cam_up_body[0],
            center_body[1] + tan_h * cam_right_body[1] + tan_v * cam_up_body[1],
            center_body[2] + tan_h * cam_right_body[2] + tan_v * cam_up_body[2]
        ]

        # Normalize
        norm = math.sqrt(sum(c ** 2 for c in corner_body))
        if norm == 0:
            return [0.0, 0.0, -1.0]
        corner_body = [c / norm for c in corner_body]

        # Rotate from body frame to ENU frame
        # Roll rotation (around X axis)
        cos_r = math.cos(roll)
        sin_r = math.sin(roll)

        x1 = corner_body[0]
        y1 = cos_r * corner_body[1] - sin_r * corner_body[2]
        z1 = sin_r * corner_body[1] + cos_r * corner_body[2]

        # Pitch rotation (around Y axis)
        cos_p = math.cos(pitch)
        sin_p = math.sin(pitch)

        x2 = cos_p * x1 + sin_p * z1
        y2 = y1
        z2 = -sin_p * x1 + cos_p * z1

        # Yaw rotation (around Z axis)
        cos_y = math.cos(yaw)
        sin_y = math.sin(yaw)

        # Result in ENU: x=east, y=north, z=up
        enu_x = cos_y * x2 - sin_y * y2
        enu_y = sin_y * x2 + cos_y * y2
        enu_z = z2

        return [enu_x, enu_y, enu_z]

    def calculate_footprint_area(self, corners):
        """Calculate the approximate ground area of a footprint polygon.

        Uses the planar shoelace formula with lat/lon-to-metres conversion.

        Parameters:
            corners: List of [lat, lon] pairs forming the polygon

        Returns:
            Approximate area in square metres
        """
        if corners is None or len(corners) < 3:
            return 0.0

        R = self._config.earth_radius_m

        # Convert to radians
        lat_rad = [math.radians(c[0]) for c in corners]
        lon_rad = [math.radians(c[1]) for c in corners]

        # Average latitude for scale factor
        avg_lat = sum(lat_rad) / len(lat_rad)
        cos_avg_lat = math.cos(avg_lat)

        # Convert to local ENU coordinates (metres) relative to first corner
        # Note: lat_rad and lon_rad are already in radians, so no need for π/180 conversion
        enu = []
        for lr, lor in zip(lat_rad, lon_rad):
            e = R * (lor - lon_rad[0]) * cos_avg_lat  # east in metres
            n = R * (lr - lat_rad[0])  # north in metres
            enu.append((e, n))

        # Shoelace formula for area
        n_pts = len(enu)
        area = 0.0
        for i in range(n_pts):
            j = (i + 1) % n_pts
            area += enu[i][0] * enu[j][1]
            area -= enu[j][0] * enu[i][1]

        return abs(area) / 2.0

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
