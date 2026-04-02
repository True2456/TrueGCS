import time
import math
import json
import threading
import socket
import os
os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil

class TailsitterSim:
    def __init__(self, config_path=None):
        if config_path is None:
            # Locate relative to script 🚀
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "sim_config.json")
            
        with open(config_path, 'r') as f:
            self.config = json.load(f)
            
        self.origin = self.config["origin"]
        self.drone_cfg = self.config["drone"]
        self.net_cfg = self.config["network"]
        
        # State Vectors (Atomic Access)
        self.lat = self.origin["lat"]
        self.lon = self.origin["lon"]
        self.alt = self.origin["alt"]
        self.roll = 0.0
        self.pitch = 0.0 # Vertical hover = 90 deg? No, ArduPilot uses 0 for level hover in VTOL mode?
        # Standard convention: Pitch 0 = Horizon. Vertical Hover = Pitch 90.
        self.yaw = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.vz = 0.0
        self.batt_pct = 98
        self.is_armed = False
        self.mode = "QSTABILIZE"
        self.mission_active = False
        self.current_waypoint = 0
        self.waypoints = []
        self.is_transitioned = False # Track mission phase 🛰️
        
        self.lock = threading.Lock()
        self.mode_map = {
            "STABILIZE": 0, "CIRCLE": 1, "FBWA": 5, "AUTO": 10, "RTL": 11,
            "LOITER": 12, "TAKEOFF": 13, "TRANSITION": 14, "QSTABILIZE": 17,
            "QHOVER": 18, "QLOITER": 19, "QLAND": 20, "QRTL": 21
        }
        self.target_lat = self.lat
        self.target_lon = self.lon
        self.target_alt = self.alt
        
        self.last_hb = 0
        self.target_speed_ms = self.drone_cfg["cruise_speed_ms"]
        
        # Connection: Active Broadcast (Push) to GCS 🚀
        self.conn = mavutil.mavlink_connection(
            f"udpout:{self.net_cfg['gcs_ip']}:{self.net_cfg['gcs_port']}",
            source_system=self.drone_cfg["sysid"],
            source_component=self.drone_cfg["compid"]
        )
        
        self.running = True
        self.start_time = time.time()
        self.last_update = self.start_time
        self.last_hb = 0
        
    def _get_boot_ms(self):
        return int((time.time() - self.start_time) * 1000)

    def _get_distance_metres(self, lat1, lon1, lat2, lon2):
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        return math.sqrt((dlat*dlat) + (dlon*dlon)) * 1.113195e5

    def _get_bearing(self, lat1, lon1, lat2, lon2):
        off_x = lon2 - lon1
        off_y = lat2 - lat1
        bearing = 90.0 + math.degrees(math.atan2(-off_y, off_x))
        if bearing < 0: bearing += 360.0
        return bearing
        
    def run(self):
        print(f"Mission SITL: Twister Dual-Engine Simulator Active at {self.lat}, {self.lon}")
        print(f"MAVLink 2.0 Broadcast: {self.net_cfg['gcs_ip']}:{self.net_cfg['gcs_port']}")
        
        # Listen for GCS Commands in background
        threading.Thread(target=self._recv_loop, daemon=True).start()
        
        while self.running:
            now = time.time()
            dt = now - self.last_update
            self.last_update = now
            
            self._update_physics(dt)
            self._broadcast_telemetry()
            
            time.sleep(0.05) # 20Hz Loop
            
    def _update_physics(self, dt):
        if not self.is_armed:
            return
            
        # Basic VTOL Physics for Mission Testing
        if self.mode == "AUTO":
            target_alt = self.drone_cfg["transition_alt_m"]
            
            if self.alt >= target_alt:
                self.is_transitioned = True

            if not self.is_transitioned:
                # 1. Vertical Climb Mode
                if self.vz == 0: print(f"[PHYSICS] Mode: {self.mode} | Action: Vertical Takeoff to {target_alt}m", flush=True)
                self.vz = self.drone_cfg["climb_rate_ms"]
                self.pitch = 0.0 # Standard Level Climb
                self.alt += self.vz * dt
            else:
                # 2. Waypoint Navigation
                self.vz = 0.0
                
                # --- MISSION ENGINE: Consume non-navigation commands instantly ---
                while len(self.waypoints) > 0 and self.current_waypoint < len(self.waypoints):
                    wp = self.waypoints[self.current_waypoint]
                    cmd = wp.command if hasattr(wp, 'command') else wp.get('command', 0)
                    
                    if cmd == 178: # MAV_CMD_DO_CHANGE_SPEED
                        new_speed = wp.param2 if hasattr(wp, 'param2') else wp.get('param2', self.target_speed_ms)
                        if new_speed > 0: self.target_speed_ms = new_speed
                        print(f"Mission SITL: [EXEC] DO_CHANGE_SPEED -> {self.target_speed_ms} m/s", flush=True)
                        self.current_waypoint += 1
                        continue # Re-check next item in same frame
                    elif cmd in [16, 22, 82, 84, 85]: # NAV_WAYPOINT, NAV_TAKEOFF, NAV_VTOL_TAKEOFF...
                        break
                    else:
                        # Skip other non-positional items (Condition, Jump, etc.)
                        self.current_waypoint += 1

                if len(self.waypoints) > 0 and self.current_waypoint < len(self.waypoints):
                    wp = self.waypoints[self.current_waypoint]
                    target_lat = wp.x / 1e7 if hasattr(wp, 'x') else wp['lat']
                    target_lon = wp.y / 1e7 if hasattr(wp, 'y') else wp['lon']
                    target_alt_msl = wp.z if hasattr(wp, 'z') else wp['alt']
                    
                    dist = self._get_distance_metres(self.lat, self.lon, target_lat, target_lon)
                    
                    if dist < 5.0: # 5m Arrival Radius
                        print(f"Mission SITL: Waypoint {self.current_waypoint} reached! (Dist: {dist:.1f}m)", flush=True)
                        with self.lock:
                            self.conn.mav.mission_item_reached_send(self.current_waypoint)
                        self.current_waypoint += 1
                        
                        # 🛰️ Mission End Guard: Transition to LOITER at final WP
                        if self.current_waypoint >= len(self.waypoints):
                            print("Mission SITL: [AUTO-RECOVERY] Final Waypoint hit. Entering Coordinated Orbit.", flush=True)
                            self.mode = "LOITER"
                            self.target_lat = target_lat
                            self.target_lon = target_lon
                        return 
                    
                    # --- FLIGHT DYNAMICS: Coordinated Turn Model ---
                    target_bearing = self._get_bearing(self.lat, self.lon, target_lat, target_lon)
                    diff = (target_bearing - self.yaw + 180) % 360 - 180
                    
                    # Limit turn rate based on config (Realistic arcs)
                    max_step = self.drone_cfg["max_yaw_rate_deg"] * dt
                    step = max(-max_step, min(max_step, diff * 0.1)) # Smoothly move but cap rate
                    
                    prev_yaw = self.yaw
                    self.yaw = (self.yaw + step) % 360
                    
                    # Coordinated Banking (Roll): Proportional to turn rate
                    turn_rate_s = step / dt
                    # INVERTED for GCS HUD Calibration 🛰️
                    target_roll = - (turn_rate_s * self.drone_cfg["bank_factor"])
                    self.roll = max(-self.drone_cfg["max_roll_deg"], min(self.drone_cfg["max_roll_deg"], target_roll))
                    
                    self.pitch = 0.0 # Level cruise
                    
                    # Apply Speed Clamping (15-35 m/s)
                    speed = max(self.drone_cfg["min_speed_ms"], min(self.drone_cfg["max_speed_ms"], self.target_speed_ms))
                    
                    # Directional Velocity based on current Yaw
                    self.vx = speed * math.cos(math.radians(90 - self.yaw))
                    self.vy = speed * math.sin(math.radians(90 - self.yaw))
                    
                    # Update lat/lon
                    self.lat += (self.vy * dt) / 111111.0
                    self.lon += (self.vx * dt) / (111111.0 * math.cos(math.radians(self.lat)))
                    
                    # Vertical correction (move toward target altitude)
                    if self.alt < target_alt_msl - 1: self.alt += 2.0 * dt
                    elif self.alt > target_alt_msl + 1: self.alt -= 2.0 * dt
                else:
                    # MISSION COMPLETE FALLBACK: Coordinated Loiter and Pitch Level 🛰️
                    self.mode = "LOITER"
                    self.pitch = 0.0
                    self.vx = 0.0
                    self.vy = 0.0
                    print(f"[PHYSICS] Mission Complete | Mode: {self.mode} | Target: Last Waypoint", flush=True)
        elif self.mode in ["FBWA", "CIRCLE", "LOITER"]:
            # Level high-speed horizontal cruise or orbiting 🛰️
            self.pitch = 0.0
            self.vz = 0.0
            speed = self.drone_cfg["cruise_speed_ms"]
            
            if self.mode in ["CIRCLE", "LOITER"]:
                # Orbit physics around target_lat/lon 🛰️
                dist = self._get_distance_metres(self.lat, self.lon, self.target_lat, self.target_lon)
                radius = 50.0 # Standard loiter radius
                
                bearing_to_center = self._get_bearing(self.lat, self.lon, self.target_lat, self.target_lon)
                bearing_from_center = (bearing_to_center + 180) % 360
                
                old_yaw = self.yaw
                if dist < 5.0:
                    self.yaw = 0.0
                elif dist < radius - 5:
                    # Too close: fly out
                    self.yaw = bearing_from_center
                elif dist > radius + 15:
                    # Too far: fly in
                    self.yaw = bearing_to_center
                else:
                    # On the ring: Pure tangent
                    self.yaw = (bearing_to_center + 90) % 360
                
                # Coordinated Turn Physics for orbits 🛰️
                yaw_diff = (self.yaw - old_yaw + 180) % 360 - 180
                turn_rate = yaw_diff / dt
                # INVERTED for GCS HUD Calibration 🛰️
                target_roll = - (turn_rate * self.drone_cfg["bank_factor"])
                self.roll = max(-self.drone_cfg["max_roll_deg"], min(self.drone_cfg["max_roll_deg"], target_roll))
            else:
                self.roll = 0.0 # Level FBWA / Straight Recovery 🛰️
                self.pitch = 0.0 
                # Maintain heading or default to North if mission just completed
                if self.vx == 0 and self.vy == 0:
                    self.yaw = 0.0
            
            # Use cruise speed for standard orbit
            current_orbit_speed = self.drone_cfg["cruise_speed_ms"]
            self.vx = current_orbit_speed * math.cos(math.radians(90 - self.yaw))
            self.vy = current_orbit_speed * math.sin(math.radians(90 - self.yaw))
            self.lat += (self.vy * dt) / 111111.0
            self.lon += (self.vx * dt) / (111111.0 * math.cos(math.radians(self.lat)))
        elif self.mode in ["QLOITER", "QRTL", "QSTABILIZE", "TAKEOFF", "TRANSITION", "RTL"]:
            # Hover, Vertical Climb, or Transition 🛰️
            self.vz = 0.0
            
            if self.mode == "TAKEOFF":
                climb_rate = 2.2 # 2.2m/s realistic heavy climb 🛰️
                self.vx = 0.0
                self.vy = 0.0
                self.pitch = 0.0
                if self.alt < self.target_alt:
                    # Pure Vertical Climb
                    self.alt += climb_rate * dt
                else:
                    self.mode = "TRANSITION"
                    print(f"Mission SITL: Reach Takeoff Alt ({self.target_alt:.1f}m). Initiating Forward Transition...", flush=True)
            
            elif self.mode in ["QRTL", "RTL"]:
                # 1. Return Home Logic 🛰️
                dist = self._get_distance_metres(self.lat, self.lon, self.origin["lat"], self.origin["lon"])
                
                if dist > 45.0:
                    # Fly toward home (horizontal) 🛰️
                    self.yaw = self._get_bearing(self.lat, self.lon, self.origin["lat"], self.origin["lon"])
                    speed = self.drone_cfg["cruise_speed_ms"]
                    self.vx = speed * math.cos(math.radians(90 - self.yaw))
                    self.vy = speed * math.sin(math.radians(90 - self.yaw))
                    self.pitch = 0.0
                    self.roll = 0.0 # Forced Level Rollout during Return 🛰️
                elif self.mode == "RTL":
                    # RTL: Station-keeping Orbit (Fixed-Wing) 🛰️
                    self.mode = "LOITER"
                    self.target_lat = self.origin["lat"]
                    self.target_lon = self.origin["lon"]
                    print("Mission SITL: [RTL] Home reached. Entering Station-Keeping Orbit.", flush=True)
                else:
                    # QRTL: Back-Transition Flare (Pitch-Up) 🛰️
                    # Flare at 15 deg/sec up to 90
                    target_pitch = 90.0
                    if self.pitch < target_pitch:
                        self.pitch += 15.0 * dt
                        # Horizontal air-braking (Drag)
                        current_speed = math.sqrt(self.vx**2 + self.vy**2)
                        bleed = 5.0 * dt
                        if current_speed > 0:
                            ratio = (max(0, current_speed - bleed)) / current_speed
                            self.vx *= ratio
                            self.vy *= ratio
                    
                    if self.pitch >= 85.0 and math.sqrt(self.vx**2 + self.vy**2) < 2.0:
                        # 2. Arrived & Vertical: Initiate Landing Sequence 🛰️
                        self.vx = 0.0
                        self.vy = 0.0
                        self.pitch = 90.0
                        
                        # --- REALSITIC LANDING FLARE ---
                        descent_rate = 1.5 # Standard descent
                        if self.alt < 2.0:
                            descent_rate = 0.5 # Flare for soft touchdown
                        
                        if self.alt > 0.05:
                            self.alt -= descent_rate * dt
                        else:
                            self.alt = 0.0
                            self.is_armed = False # Auto-disarm on touchdown
                            self.mode = "QSTABILIZE"
                            print("Mission SITL: TOUCHDOWN (Soft Flare)! Recovery complete.", flush=True)

            elif self.mode == "TRANSITION":
                # Tilt forward and accelerate 🛰️
                target_pitch = -45.0 # Dramatic tailsitter tilt
                if self.pitch > target_pitch:
                    self.pitch -= 15.0 * dt
                    # --- TRANSITION SETTLE ---
                    # Lose vertical lift before airspeed generates wing lift
                    self.alt -= 2.5 * dt
                
                self.vx += 5.0 * dt # Accelerate forward
                current_speed = math.sqrt(self.vx**2 + self.vy**2)
                
                if current_speed >= 15.0:
                    self.mode = "LOITER"
                    self.pitch = 0.0 # Return to cruise pitch
                    print(f"Mission SITL: Transition complete ({current_speed:.1f} m/s). Entering Orbitring.", flush=True)
            
            elif self.mode in ["QLOITER", "QRTL", "QSTABILIZE"]:
                self.vx = 0.0
                self.vy = 0.0
                self.pitch = 0.0
                if self.alt < 20: self.alt += 2.0 * dt
            
            # Update lat/lon
            self.lat += (self.vy * dt) / 111111.0
            self.lon += (self.vx * dt) / (111111.0 * math.cos(math.radians(self.lat)))
        else:
            # Other modes: No movement for now
            pass
            
    def _broadcast_telemetry(self):
        # 1. Heartbeat (1Hz)
        now = time.time()
        with self.lock:
            if now - self.last_hb >= 1.0:
                self.last_hb = now
                custom_mode = self.mode_map.get(self.mode, 0)
                base_mode = mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
                if self.is_armed:
                    base_mode |= mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                
                self.conn.mav.heartbeat_send(
                    mavutil.mavlink.MAV_TYPE_FIXED_WING, # ID 1 for ArduPlane/VTOL mapping
                    mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                    base_mode,
                    custom_mode,
                    mavutil.mavlink.MAV_STATE_ACTIVE if self.is_armed else mavutil.mavlink.MAV_STATE_STANDBY
                )
                # Mission status broadcast
                if len(self.waypoints) > 0:
                    self.conn.mav.mission_current_send(self.current_waypoint)
                
                print(f"Mission SITL: Heartbeat dispatched (Mode: {self.mode}) [ACTIVE]", flush=True)
                
            # 2. System Status (2Hz)
            self.conn.mav.sys_status_send(
                0, 0, 0, 500, int(12400), # 12.4V
                self.batt_pct, 0, 0, 0, 0, 0, 0, 0
            )
        
        with self.lock:
            # 3. Attitude (10Hz)
            self.conn.mav.attitude_send(
                self._get_boot_ms(),
                math.radians(self.roll),
                math.radians(self.pitch),
                math.radians(self.yaw),
                0, 0, 0
            )
            
            # 4. Global Position INT (10Hz)
            self.conn.mav.global_position_int_send(
                self._get_boot_ms(),
                int(self.lat * 1e7),
                int(self.lon * 1e7),
                int(self.alt * 1000),
                int((self.alt - self.origin["alt"]) * 1000),
                int(self.vx * 100),
                int(self.vy * 100),
                int(self.vz * 100),
                int(self.yaw * 100)
            )
            
            # 5. VFR_HUD (5Hz)
            # Standard MAVLink VFR_HUD: Airspeed, Groundspeed, Heading, Throttle, Alt, Climb rate 🛰️
            spd_2d = math.sqrt(self.vx**2 + self.vy**2)
            self.conn.mav.vfr_hud_send(
                spd_2d,      # Airspeed
                spd_2d,      # Groundspeed
                int(self.yaw),
                50,          # Throttle (Assume cruising)
                self.alt,
                -self.vz     # Climb rate (inverted for VFR_HUD convention)
            )

    def _recv_loop(self):
        while self.running:
            with self.lock:
                try:
                    msg = self.conn.recv_match(blocking=False)
                except Exception as e:
                    # Ignore common Windows UDP transition errors e.g. 10022 or 10054
                    time.sleep(0.01)
                    continue

            if not msg:
                time.sleep(0.01)
                continue

            # DEBUG: Print incoming message types to trace communication
            mtype = msg.get_type()
            # if mtype != 'HEARTBEAT': print(f"DEBUG SITL: Received {mtype}")

            with self.lock:
                if mtype == 'COMMAND_LONG':
                    print(f"DEBUG SITL: Command {msg.command} received from {msg.get_srcSystem()}:{msg.get_srcComponent()}")
                    if msg.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
                        self.is_armed = (msg.param1 == 1)
                        if not self.is_armed:
                            self.is_transitioned = False # Reset on disarm
                        print(f"Mission SITL: Drone {'ARMED' if self.is_armed else 'DISARMED'} via MAVLink command.", flush=True)
                        self.conn.mav.command_ack_send(
                            msg.command, 
                            mavutil.mavlink.MAV_RESULT_ACCEPTED, 
                            target_system=msg.get_srcSystem(), 
                            target_component=msg.get_srcComponent()
                        )
                    elif msg.command == mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED:
                        self.target_speed_ms = msg.param2
                        print(f"Mission SITL: Target Speed updated to {self.target_speed_ms} m/s", flush=True)
                        self.conn.mav.command_ack_send(
                            msg.command, 
                            mavutil.mavlink.MAV_RESULT_ACCEPTED, 
                            target_system=msg.get_srcSystem(), 
                            target_component=msg.get_srcComponent()
                        )
                        
                    elif msg.command == mavutil.mavlink.MAV_CMD_NAV_TAKEOFF:
                        if self.is_armed:
                            self.mode = "TAKEOFF"
                            self.target_alt = self.origin["alt"] + 50.0
                            self.target_lat = self.lat
                            self.target_lon = self.lon
                            print(f"Mission SITL: Initiating Vertical Takeoff to {self.target_alt}m...", flush=True)
                            self.conn.mav.command_ack_send(
                                msg.command, 
                                mavutil.mavlink.MAV_RESULT_ACCEPTED, 
                                target_system=msg.get_srcSystem(), 
                                target_component=msg.get_srcComponent()
                            )

                    elif msg.command == mavutil.mavlink.MAV_CMD_DO_SET_MODE:
                        # ArduPilot Command Long DO_SET_MODE uses param2 for custom mode 🛰️
                        new_mode_id = int(msg.param2 if msg.param2 != 0 else msg.param1)
                        mode_found = False
                        for m_name, m_id in self.mode_map.items():
                            if m_id == new_mode_id:
                                self.mode = m_name
                                mode_found = True
                                if m_name != "AUTO":
                                    self.is_transitioned = False # Reset if leaving AUTO
                                
                                # [TACTICAL FIX] Lock current position for manual Loiter/Circle 🛰️
                                if m_name in ["LOITER", "CIRCLE"]:
                                    self.target_lat = self.lat
                                    self.target_lon = self.lon
                                    print(f"Mission SITL: Dynamic Orbit Center locked at {self.lat:.6f}, {self.lon:.6f}")
                                break
                        print(f"Mission SITL: Mode change (ID: {new_mode_id}) -> {self.mode if mode_found else 'UNKNOWN'}")
                        self.conn.mav.command_ack_send(
                            msg.command, 
                            mavutil.mavlink.MAV_RESULT_ACCEPTED, 
                            target_system=msg.get_srcSystem(), 
                            target_component=msg.get_srcComponent()
                        )

                elif msg.get_type() == 'MISSION_COUNT':
                    self.expected_count = msg.count
                    self.wp_buffer = []
                    print(f"Mission SITL: Receiving mission count -> {msg.count} items. Requesting Seq 0...", flush=True)
                    self.conn.mav.mission_request_int_send(msg.get_srcSystem(), msg.get_srcComponent(), 0)

                elif msg.get_type() == 'MISSION_ITEM_INT':
                    print(f"Mission SITL: Received Mission Item {msg.seq}/{self.expected_count-1}", flush=True)
                    self.wp_buffer.append(msg)
                    if len(self.wp_buffer) < self.expected_count:
                        self.conn.mav.mission_request_int_send(msg.get_srcSystem(), msg.get_srcComponent(), len(self.wp_buffer))
                    else:
                        self.waypoints = self.wp_buffer
                        self.current_waypoint = 0
                        self.conn.mav.mission_ack_send(msg.get_srcSystem(), msg.get_srcComponent(), mavutil.mavlink.MAV_MISSION_ACCEPTED)
                        print(f"Mission SITL: Upload complete. {len(self.waypoints)} Waypoints ready for Twitcher.", flush=True)

                elif msg.get_type() == 'MISSION_SET_CURRENT':
                    self.current_waypoint = msg.seq
                    print(f"Mission SITL: Current target item set to {msg.seq}.")
                    # ArduPilot doesn't usually respond to this with MISSION_COUNT, but let's keep logic if needed
                    # self.conn.mav.mission_count_send(msg.get_srcSystem(), msg.get_srcComponent(), len(self.waypoints))

                elif msg.get_type() == 'MISSION_REQUEST_LIST':
                    self.conn.mav.mission_count_send(msg.get_srcSystem(), msg.get_srcComponent(), len(self.waypoints))

                elif msg.get_type() == 'MISSION_REQUEST_INT':
                    if msg.seq < len(self.waypoints):
                        wp = self.waypoints[msg.seq]
                        self.conn.mav.mission_item_int_send(
                            msg.get_srcSystem(), msg.get_srcComponent(), 
                            wp.seq, wp.frame, wp.command, wp.current, wp.autocontinue,
                            wp.param1, wp.param2, wp.param3, wp.param4,
                            wp.x, wp.y, wp.z
                        )

                elif msg.get_type() == 'SET_MODE':
                    # ArduPilot Mode Mapping: 0=STABILIZE, 10=AUTO, 19=QLOITER 🚀
                    for m_name, m_id in self.mode_map.items():
                        if m_id == msg.custom_mode:
                            self.mode = m_name
                            if m_name != "AUTO":
                                self.is_transitioned = False # Reset if leaving AUTO
                            break
                    print(f"Mission SITL: Mode change requested -> {self.mode} (ID: {msg.custom_mode})")

    def _get_distance_metres(self, lat1, lon1, lat2, lon2):
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2) * math.sin(dlat/2) + math.cos(math.radians(lat1)) \
            * math.cos(math.radians(lat2)) * math.sin(dlon/2) * math.sin(dlon/2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return 6371000 * c

    def _get_bearing(self, lat1, lon1, lat2, lon2):
        off_x = lon2 - lon1
        off_y = lat2 - lat1
        bearing = 90.0 + math.degrees(math.atan2(-off_y, off_x))
        return bearing % 360

    def _get_boot_ms(self):
        return int((time.time() - self.start_time) * 1000)

if __name__ == "__main__":
    sim = TailsitterSim()
    sim.run()
