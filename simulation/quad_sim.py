import time
import math
import json
import threading
import socket
import os
import sys
import signal

# Ensure MAVLink 2.0
os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil

class QuadSim:
    def __init__(self, port=14550, config_path=None):
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "sim_config.json")
            
        with open(config_path, 'r') as f:
            self.config = json.load(f)
            
        self.origin = self.config["origin"]
        self.drone_cfg = self.config["drone"]
        self.net_cfg = self.config["network"]
        
        # State Vectors
        self.lat = self.origin["lat"]
        self.lon = self.origin["lon"]
        self.alt = self.origin["alt"]
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.vz = 0.0
        self.batt_pct = 98
        self.is_armed = False
        self.mode = "STABILIZE"
        self.current_waypoint = 0
        self.waypoints = []
        self.gps_enabled = True
        
        self.lock = threading.Lock()
        
        # ArduCopter Mode IDs 🛸
        self.mode_map = {
            "STABILIZE": 0, "ALT_HOLD": 2, "AUTO": 3, "GUIDED": 4, 
            "LOITER": 5, "RTL": 6, "CIRCLE": 7, "LAND": 9
        }
        
        self.target_lat = self.lat
        self.target_lon = self.lon
        self.target_alt = self.alt
        self.target_speed_ms = 24.0 # Match VTOL Speed 🚀
        
        self.sysid = 2 
        self.nav_port = port + 1 
        
        self.conns = []
        self.conns.append(mavutil.mavlink_connection(f"udpout:{self.net_cfg['gcs_ip']}:{port}", source_system=self.sysid))
        self.conns.append(mavutil.mavlink_connection(f"udpout:127.0.0.1:{self.nav_port}", source_system=self.sysid))
        self.conns.append(mavutil.mavlink_connection(f"udpin:0.0.0.0:{self.nav_port}", source_system=self.sysid))
        
        self.running = True
        self.start_time = time.time()
        self.last_update = self.start_time
        
    def _get_boot_ms(self):
        return int((time.time() - self.start_time) * 1000)

    def stop(self, *args):
        print("Mission SITL: Quad Shutting down...", flush=True)
        self.running = False
        with self.lock:
            for conn in self.conns:
                try: conn.close()
                except: pass
        sys.exit(0)

    def run(self):
        print(f"Mission SITL: Quadcopter HIGH-SPEED Active at {self.lat}, {self.lon}", flush=True)
        threading.Thread(target=self._recv_loop, daemon=True).start()
        threading.Thread(target=self._telemetry_loop, daemon=True).start()
        
        while self.running:
            now = time.time()
            dt = now - self.last_update
            self.last_update = now
            
            self._update_physics(dt)
            time.sleep(0.05) # 20Hz Loop (Flawless)
            
    def _update_physics(self, dt):
        if not self.is_armed:
            self.vx = self.vy = self.vz = 0.0
            return
            
        if self.mode == "AUTO":
            if not self.waypoints or self.current_waypoint >= len(self.waypoints):
                self.mode = "LOITER"
                self.vx = self.vy = 0.0
                return

            if self.alt < 15.0: # Lower floor for faster transit
                self.vz = 3.0
                self.alt += self.vz * dt
                self.vx = self.vy = 0.0
            else:
                self.vz = 0.0
                wp = self.waypoints[self.current_waypoint]
                t_lat, t_lon, t_alt = wp.x/1e7, wp.y/1e7, wp.z
                
                dist = self._get_distance_metres(self.lat, self.lon, t_lat, t_lon)
                if dist < 5.0:
                    print(f"Mission SITL: WP {self.current_waypoint} Hit!", flush=True)
                    with self.lock:
                        for conn in self.conns:
                            conn.mav.mission_item_reached_send(self.current_waypoint)
                    self.current_waypoint += 1
                    return

                self.yaw = self._get_bearing(self.lat, self.lon, t_lat, t_lon)
                speed = self.target_speed_ms
                
                # Precise Integration (Flawless Model) 🛰️
                self.vx = speed * math.sin(math.radians(self.yaw))
                self.vy = speed * math.cos(math.radians(self.yaw))
                
                self.lat += (self.vy * dt) / 111111.0
                self.lon += (self.vx * dt) / (111111.0 * math.cos(math.radians(self.lat)))
                
                if self.alt < t_alt: self.alt += 2.0 * dt
                elif self.alt > t_alt: self.alt -= 2.0 * dt
                
                self.pitch = 15.0 
                if int(time.time()) % 2 == 0:
                    print(f"Mission SITL: [AUTO] Speed: {speed}m/s | Dist: {dist:.1f}m", flush=True)

        elif self.mode == "GUIDED":
            if self.alt < self.target_alt:
                self.alt += 3.0 * dt
            else:
                self.mode = "LOITER"

        elif self.mode in ["LOITER", "STABILIZE"]:
            self.vx = self.vy = 0.0
            self.pitch = math.sin(time.time() * 2) * 2.0
            self.roll = math.cos(time.time() * 2) * 2.0

    def _telemetry_loop(self):
        while self.running:
            self._broadcast_telemetry()
            time.sleep(0.1)

    def _broadcast_telemetry(self):
        now = time.time()
        with self.lock:
            custom_mode = self.mode_map.get(self.mode, 0)
            base_mode = mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
            if self.is_armed: base_mode |= mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
            
            for conn in self.conns:
                conn.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_FIXED_WING, mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA, base_mode, custom_mode, mavutil.mavlink.MAV_STATE_ACTIVE if self.is_armed else mavutil.mavlink.MAV_STATE_STANDBY)
                if len(self.waypoints) > 0: conn.mav.mission_current_send(self.current_waypoint)
                boot_ms = self._get_boot_ms()
                conn.mav.sys_status_send(0, 0, 0, 500, 12400, self.batt_pct, 0, 0, 0, 0, 0, 0, 0)
                conn.mav.attitude_send(boot_ms, math.radians(self.roll), math.radians(self.pitch), math.radians(self.yaw), 0, 0, 0)
                conn.mav.global_position_int_send(boot_ms, int(self.lat*1e7), int(self.lon*1e7), int(self.alt*1000), int(self.alt*1000), int(self.vx*100), int(self.vy*100), int(self.vz*100), int(self.yaw*100))
                conn.mav.vfr_hud_send(math.sqrt(self.vx**2 + self.vy**2), math.sqrt(self.vx**2 + self.vy**2), int(self.yaw), 50, self.alt, -self.vz)

    def _recv_loop(self):
        while self.running:
            for current_conn in self.conns:
                with self.lock:
                    try:
                        msg = current_conn.recv_match(blocking=False)
                    except:
                        continue
                if msg:
                    mtype = msg.get_type()
                    if mtype == 'COMMAND_LONG':
                        if msg.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
                            self.is_armed = (msg.param1 == 1)
                            current_conn.mav.command_ack_send(msg.command, mavutil.mavlink.MAV_RESULT_ACCEPTED, target_system=msg.get_srcSystem(), target_component=msg.get_srcComponent())
                        elif msg.command == mavutil.mavlink.MAV_CMD_NAV_TAKEOFF:
                            if self.is_armed:
                                self.mode = "GUIDED"
                                self.target_alt = self.alt + 30.0
                                current_conn.mav.command_ack_send(msg.command, mavutil.mavlink.MAV_RESULT_ACCEPTED, target_system=msg.get_srcSystem(), target_component=msg.get_srcComponent())
                        elif msg.command == mavutil.mavlink.MAV_CMD_DO_SET_MODE:
                            new_mode_id = int(msg.param2 if msg.param2 != 0 else msg.param1)
                            for m_name, m_id in self.mode_map.items():
                                if m_id == new_mode_id: self.mode = m_name; break
                            current_conn.mav.command_ack_send(msg.command, mavutil.mavlink.MAV_RESULT_ACCEPTED, target_system=msg.get_srcSystem(), target_component=msg.get_srcComponent())
                    elif mtype == 'SET_MODE':
                        for m_name, m_id in self.mode_map.items():
                            if m_id == msg.custom_mode: self.mode = m_name; break
                    elif mtype == 'MISSION_COUNT':
                        self.expected_count = msg.count
                        self.wp_buffer = []
                        current_conn.mav.mission_request_int_send(msg.get_srcSystem(), msg.get_srcComponent(), 0)
                    elif mtype == 'MISSION_ITEM_INT':
                        self.wp_buffer.append(msg)
                        if len(self.wp_buffer) < self.expected_count:
                            current_conn.mav.mission_request_int_send(msg.get_srcSystem(), msg.get_srcComponent(), len(self.wp_buffer))
                        else:
                            self.waypoints = self.wp_buffer
                            self.current_waypoint = 0
                            current_conn.mav.mission_ack_send(msg.get_srcSystem(), msg.get_srcComponent(), mavutil.mavlink.MAV_MISSION_ACCEPTED)
            time.sleep(0.01)

    def _get_distance_metres(self, lat1, lon1, lat2, lon2):
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return 6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def _get_bearing(self, lat1, lon1, lat2, lon2):
        off_x = lon2 - lon1
        off_y = lat2 - lat1
        bearing = 90.0 + math.degrees(math.atan2(-off_y, off_x))
        return bearing % 360

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=14550)
    args = parser.parse_args()
    sim = QuadSim(port=args.port)
    sim.run()
