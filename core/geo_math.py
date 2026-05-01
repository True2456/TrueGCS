"""
core/geo_math.py — Georeferenced Camera Footprint Calculations

Provides mathematical utilities for projecting a drone's camera view frustum
onto the Earth's surface (WGS84 ellipsoid approximation) to compute the
georeferenced "footprint" polygon visible in the camera feed.

Key Concepts:
- Drone position: (lat, lon, alt_AGL) in WGS84
- Drone attitude: roll, pitch, yaw (degrees, NED convention)
- Gimbal angles: pitch (negative = down), yaw offset (degrees)
- Camera FOV: horizontal and vertical field of view in degrees

The footprint is a trapezoid on the ground defined by 4 corners:
  FL (front-left), FR (front-right), RL (rear-left), RR (rear-right)
These are returned as (lat, lon) pairs suitable for mapping.
"""

import math


# ---------------------------------------------------------------------------
# WGS84 Constants
# ---------------------------------------------------------------------------
WGS84_A = 6378137.0          # Semi-major axis (m)
WGS84_F = 1 / 298.257223563  # Flattening
WGS84_B = WGS84_A * (1 - WGS84_F)  # Semi-minor axis

# Average Earth radius for local NED calculations
WGS84_R_MEAN = 6371000.0


# ---------------------------------------------------------------------------
# Coordinate Conversion Helpers
# ---------------------------------------------------------------------------

def latlon_to_ned(lat_ref, lon_ref, alt_ref, lat, lon, alt):
    """Convert a global (lat, lon, alt) to local NED coordinates relative to a reference point.

    Returns (north, east, down) in metres.
    Uses simple equirectangular approximation which is accurate for distances < ~50 km.
    """
    lat_r = math.radians(lat_ref)
    lon_r = math.radians(lon_ref)
    dlat = math.radians(lat - lat_ref)
    dlon = math.radians(lon - lon_ref)

    north = WGS84_R_MEAN * dlat
    east = WGS84_R_MEAN * math.cos(lat_r) * dlon
    down = -(alt - alt_ref)  # Down is positive in NED

    return north, east, down


def ned_to_latlon(lat_ref, lon_ref, alt_ref, north, east, down):
    """Convert local NED offsets back to global (lat, lon, alt).

    Parameters:
        lat_ref, lon_ref, alt_ref: Reference point in WGS84 (degrees)
        north, east, down: Offsets in metres (NED convention)

    Returns:
        (lat, lon, alt) in WGS84 (degrees)
    """
    # north / R gives radians; convert to degrees
    lat = lat_ref + math.degrees(north / WGS84_R_MEAN)
    lon = lon_ref + math.degrees(east / (WGS84_R_MEAN * math.cos(math.radians(lat_ref))))
    alt = alt_ref - down

    return lat, lon, alt


# ---------------------------------------------------------------------------
# Rotation Helpers (NED convention)
# ---------------------------------------------------------------------------

def _rot_x(angle_deg):
    """Rotation matrix about X axis (roll) in NED."""
    c = math.cos(math.radians(angle_deg))
    s = math.sin(math.radians(angle_deg))
    return [
        [1, 0, 0],
        [0, c, -s],
        [0, s,  c],
    ]


def _rot_y(angle_deg):
    """Rotation matrix about Y axis (pitch) in NED."""
    c = math.cos(math.radians(angle_deg))
    s = math.sin(math.radians(angle_deg))
    return [
        [ c, 0, s],
        [ 0, 1, 0],
        [-s, 0, c],
    ]


def _rot_z(angle_deg):
    """Rotation matrix about Z axis (yaw) in NED."""
    c = math.cos(math.radians(angle_deg))
    s = math.sin(math.radians(angle_deg))
    return [
        [c, -s, 0],
        [s,  c, 0],
        [0,  0, 1],
    ]


def _mat_mul(A, B):
    """Multiply two 3×3 matrices."""
    return [
        [A[0][0]*B[0][0] + A[0][1]*B[1][0] + A[0][2]*B[2][0],
         A[0][0]*B[0][1] + A[0][1]*B[1][1] + A[0][2]*B[2][1],
         A[0][0]*B[0][2] + A[0][1]*B[1][2] + A[0][2]*B[2][2]],
        [A[1][0]*B[0][0] + A[1][1]*B[1][0] + A[1][2]*B[2][0],
         A[1][0]*B[0][1] + A[1][1]*B[1][1] + A[1][2]*B[2][1],
         A[1][0]*B[0][2] + A[1][1]*B[1][2] + A[1][2]*B[2][2]],
        [A[2][0]*B[0][0] + A[2][1]*B[1][0] + A[2][2]*B[2][0],
         A[2][0]*B[0][1] + A[2][1]*B[1][1] + A[2][2]*B[2][1],
         A[2][0]*B[0][2] + A[2][1]*B[1][2] + A[2][2]*B[2][2]],
    ]


def _mat_vec_mul(R, v):
    """Apply 3×3 rotation matrix R to a 3D vector."""
    return [
        R[0][0]*v[0] + R[0][1]*v[1] + R[0][2]*v[2],
        R[1][0]*v[0] + R[1][1]*v[1] + R[1][2]*v[2],
        R[2][0]*v[0] + R[2][1]*v[1] + R[2][2]*v[2],
    ]


def _normalize(v):
    """Normalize a 3D vector."""
    l = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
    if l == 0:
        return [0, 0, 0]
    return [v[0]/l, v[1]/l, v[2]/l]


# ---------------------------------------------------------------------------
# Camera Footprint Calculation
# ---------------------------------------------------------------------------

def calculate_footprint(
    drone_lat,
    drone_lon,
    drone_alt,          # Altitude above ground level (AGL) in metres
    roll,               # Drone roll angle (degrees)
    pitch,              # Drone pitch angle (degrees, positive = nose up in body frame)
    yaw,                # Drone yaw / heading (degrees, NED, 0 = North)
    gimbal_pitch,       # Gimbal pitch relative to body (degrees, negative = down)
    gimbal_yaw=0.0,     # Gimbal yaw offset relative to drone heading (degrees)
    fov_h=60.0,         # Camera horizontal FOV (degrees)
    fov_v=45.0,         # Camera vertical FOV (degrees)
):
    """Calculate the georeferenced camera footprint polygon.

    Given the drone's position, attitude, gimbal orientation, and camera FOV,
    computes the four corners of the ground area visible in the camera feed.

    Coordinate Convention (NED — North-East-Down):
      - Drone body frame: +X = forward, +Y = right, +Z = down
      - Earth NED frame:   +X (North), +Y (East), +Z (Down)
      - Camera points along body +X when gimbal is at 0° pitch
      - Gimbal pitch: negative = pointing down (e.g., -90° = straight down)

    Parameters:
        drone_lat: Drone latitude (WGS84, degrees)
        drone_lon: Drone longitude (WGS84, degrees)
        drone_alt: Drone altitude above ground level (AGL, metres)
        roll: Drone roll angle (degrees)
        pitch: Drone pitch angle (degrees, positive = nose up)
        yaw: Drone heading (degrees, NED, 0 = North, clockwise positive)
        gimbal_pitch: Gimbal pitch relative to drone body (degrees, negative = down)
        gimbal_yaw: Gimbal yaw offset relative to drone heading (degrees)
        fov_h: Camera horizontal field of view (degrees)
        fov_v: Camera vertical field of view (degrees)

    Returns:
        A list of 4 tuples [(lat, lon), ...] representing the footprint corners:
            [front-left, front-right, rear-right, rear-left]
        Or None if the calculation fails (e.g., camera pointing above ground).
    """
    # Build rotation matrix from body frame to NED earth frame.
    # Order: yaw (about Z), pitch (about Y), roll (about X)
    R_body_to_earth = _mat_mul(_rot_z(yaw), _mat_mul(_rot_y(pitch), _rot_x(roll)))

    # Camera optical axis in body frame: +X direction = [1, 0, 0]
    # Apply gimbal pitch (rotation about body Y axis)
    R_gimbal_pitch = _rot_y(gimbal_pitch)

    # Combined rotation: body to earth, then gimbal
    # Camera direction in body frame after gimbal:
    cam_body = _mat_vec_mul(R_gimbal_pitch, [1.0, 0.0, 0.0])
    # Then transform to earth NED frame:
    cam_earth = _mat_vec_mul(R_body_to_earth, cam_body)

    # Normalize
    cam_earth = _normalize(cam_earth)

    # In NED: cam_earth[2] > 0 means pointing downward
    if cam_earth[2] <= 1e-6:
        # Camera pointing above or at horizon — no ground footprint
        return None

    # Distance from drone to ground along camera axis:
    # Ground is at down-distance = drone_alt below the drone
    t = drone_alt / cam_earth[2]

    if t <= 0 or math.isinf(t):
        return None

    # Ground intersection point (center of footprint) in NED from drone position
    center_ned = [t * cam_earth[0], t * cam_earth[1], t * cam_earth[2]]

    # We need the drone's MSL altitude to convert back.
    # For simplicity, we use the drone position as reference and compute relative offsets.
    center_lat, center_lon, _ = ned_to_latlon(
        drone_lat, drone_lon, 0.0,
        center_ned[0], center_ned[1], center_ned[2]
    )

    # --- Calculate footprint corners ---
    half_hov = math.tan(math.radians(fov_h / 2))   # Half horizontal angle tangent
    half_vov = math.tan(math.radians(fov_v / 2))     # Half vertical angle tangent

    # Corner directions in camera frame.
    # The optical axis is [1, 0, 0] in the camera frame (after gimbal rotation).
    # Corners are offset from this axis by ±half_hov in Y and ±half_vov in Z.
    corner_dirs_cam = [
        [1.0,  half_hov,  half_vov],   # Front-left (from drone perspective)
        [1.0, -half_hov,  half_vov],   # Front-right
        [1.0, -half_hov, -half_vov],   # Rear-right
        [1.0,  half_hov, -half_vov],   # Rear-left
    ]

    corners = []
    for d_cam in corner_dirs_cam:
        # Normalize in camera frame
        d_cam = _normalize(d_cam)

        # Apply gimbal pitch rotation about Y
        d_after_gimbal = _mat_vec_mul(R_gimbal_pitch, d_cam)

        # Transform to earth NED frame
        d_earth = _mat_vec_mul(R_body_to_earth, d_after_gimbal)

        # Normalize
        d_earth = _normalize(d_earth)

        # Intersection with ground plane (down direction is d_earth[2])
        if d_earth[2] <= 1e-6:
            continue  # This corner is above horizon

        t_corner = drone_alt / d_earth[2]
        corner_ned = [t_corner * d_earth[0], t_corner * d_earth[1], t_corner * d_earth[2]]

        corner_lat, corner_lon, _ = ned_to_latlon(
            drone_lat, drone_lon, 0.0,
            corner_ned[0], corner_ned[1], corner_ned[2]
        )
        corners.append((corner_lat, corner_lon))

    if len(corners) < 4:
        return None

    # Return corners in order: front-left, front-right, rear-right, rear-left
    return [corners[0], corners[1], corners[2], corners[3]]


# ---------------------------------------------------------------------------
# Simplified Footprint (for quick estimates)
# ---------------------------------------------------------------------------

def calculate_simple_footprint(
    drone_lat,
    drone_lon,
    drone_alt_agl,
    gimbal_pitch_deg,
    fov_h_deg=60.0,
    fov_v_deg=45.0,
):
    """Quick footprint calculation assuming level drone and gimbal-only tilt.

    This is a simplified model useful when full attitude data is unavailable.
    Assumes: roll=0, pitch=0, yaw=0, gimbal_yaw=0.

    Parameters:
        drone_lat, drone_lon: Drone position (degrees)
        drone_alt_agl: Altitude above ground (metres)
        gimbal_pitch_deg: Gimbal pitch (negative = down, e.g., -45 for 45° down)
        fov_h_deg: Horizontal FOV (degrees)
        fov_v_deg: Vertical FOV (degrees)

    Returns:
        List of 4 (lat, lon) tuples or None.
    """
    return calculate_footprint(
        drone_lat=drone_lat,
        drone_lon=drone_lon,
        drone_alt=drone_alt_agl,
        roll=0.0,
        pitch=0.0,
        yaw=0.0,
        gimbal_pitch=gimbal_pitch_deg,
        gimbal_yaw=0.0,
        fov_h=fov_h_deg,
        fov_v=fov_v_deg,
    )


# ---------------------------------------------------------------------------
# Footprint Area Calculation
# ---------------------------------------------------------------------------

def footprint_area(corners):
    """Calculate the approximate area (m²) of a footprint polygon.

    Uses the equirectangular approximation with the shoelace formula.
    """
    if not corners or len(corners) < 3:
        return 0.0

    # Convert to local NED from first corner
    ref_lat, ref_lon = corners[0]
    points_ned = []
    for lat, lon in corners:
        n, e, _ = latlon_to_ned(ref_lat, ref_lon, 0, lat, lon, 0)
        points_ned.append((e, n))  # (east, north)

    # Shoelace formula for area
    area = 0.0
    n_pts = len(points_ned)
    for i in range(n_pts):
        j = (i + 1) % n_pts
        area += points_ned[i][0] * points_ned[j][1]
        area -= points_ned[j][0] * points_ned[i][1]

    return abs(area) / 2.0


# ---------------------------------------------------------------------------
# Unit Tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Test 1: Direct NED conversion round-trip
    lat0, lon0, alt0 = -33.8688, 151.2093, 100.0
    n, e, d = latlon_to_ned(lat0, lon0, alt0, lat0 + 0.001, lon0, alt0)
    rlat, rlon, ralt = ned_to_latlon(lat0, lon0, alt0, n, e, d)
    print(f"Test 1 - NED round-trip:")
    print(f"  Original: ({lat0}, {lon0}, {alt0})")
    print(f"  Offset:   ({n:.2f}m N, {e:.2f}m E, {d:.2f}m D)")
    print(f"  Recovered: ({rlat:.6f}, {rlon:.6f}, {ralt:.2f})")
    print()

    # Test 2: Simple footprint with gimbal pointing straight down
    fp = calculate_simple_footprint(
        drone_lat=-29.983,
        drone_lon=153.233,
        drone_alt_agl=100.0,
        gimbal_pitch_deg=-90.0,  # Straight down
        fov_h_deg=60.0,
        fov_v_deg=45.0,
    )
    if fp:
        area = footprint_area(fp)
        print(f"Test 2 - Straight-down gimbal at 100m AGL:")
        for i, (lat, lon) in enumerate(fp):
            print(f"  Corner {i}: ({lat:.8f}, {lon:.8f})")
        print(f"  Approximate area: {area:.1f} m² ({area/1e4:.2f} ha)")
    else:
        print("Test 2 - No footprint (camera above horizon?)")
    print()

    # Test 3: Gimbal at -45 degrees
    fp = calculate_simple_footprint(
        drone_lat=-29.983,
        drone_lon=153.233,
        drone_alt_agl=100.0,
        gimbal_pitch_deg=-45.0,
        fov_h_deg=60.0,
        fov_v_deg=45.0,
    )
    if fp:
        area = footprint_area(fp)
        print(f"Test 3 - Gimbal at -45° at 100m AGL:")
        for i, (lat, lon) in enumerate(fp):
            print(f"  Corner {i}: ({lat:.8f}, {lon:.8f})")
        print(f"  Approximate area: {area:.1f} m² ({area/1e4:.2f} ha)")
    else:
        print("Test 3 - No footprint")
