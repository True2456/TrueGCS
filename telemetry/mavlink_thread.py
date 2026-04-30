import time
import math
import threading
from PySide6.QtCore import QThread, Signal, QObject
from pymavlink import mavutil

class TelemetrySignals(QObject):
    # Signals for updating the UI with Multi-Drone routing
    drone_discovered = Signal(int, int, str) # node_id, sysid, color
    heartbeat_received = Signal(int, int, bool) # node_id, sysid, is_armed
    position_updated = Signal(int, int, float, float, float) # node_id, sysid, lat, lon, alt
    attitude_updated = Signal(int, int, float, float, float) # node_id, sysid, roll, pitch, yaw
    hud_updated = Signal(int, int, float, float, float, str) # node_id, sysid, speed, battery, alt, mode
    status_text_updated = Signal(int, int, str) # node_id, sysid, txt
    parameter_updated = Signal(int, int, str, float) # node_id, sysid, param, val
    parameters_loaded = Signal(int, int) # node_id, sysid
    parameter_progress = Signal(int, int, int, int) # node_id, sysid, current, total
    modes_available = Signal(int, int, list) # node_id, sysid, list
    drone_lost = Signal(int, int) # node_id, sysid
    armed_status_changed = Signal(int, int, bool) # node_id, sysid, is_armed
    distance_sensor_updated = Signal(int, int, float) # node_id, sysid, dist_m
    gps2_updated = Signal(int, int, int, float) # node_id, sysid, fix_type, hdop
    ekf_status_updated = Signal(int, int, int) # node_id, sysid, flags
    nav_updated = Signal(int, int, float) # node_id, sysid, wp_dist

class TelemetryThread(QThread):
    def __init__(self, node_id, color, connection_string="COM18", baud=115200, parent=None):
        super().__init__(parent)
        self.node_id = node_id
        self.color = color
        self.connection_string = connection_string
        self.baud = baud
        self.running = True
        self.signals = TelemetrySignals()
        self.master = None
        
        # Multiplex state caching (indexed by sysid)
        self.parameters = {}
        self.total_params = {}
        self.params_received = {}
        self._last_mode = {}
        self._last_hud_summary = {}
        self._modes_emitted = {}
        self.known_drones = set()
        self.last_heartbeats = {}
        self._last_cleanup_time = 0
        self._pending_missions = {} # sysid -> [wp1, wp2, ...]
        # Latest known mount orientation (degrees), indexed by sysid.
        # Used to align gimbal controllers so "center slew" doesn't assume 0 degrees.
        self.mount_angles = {}
        self.lock = threading.Lock()

    def _ensure_drone(self, sysid):
        if sysid not in self.known_drones:
            self.known_drones.add(sysid)
            self.parameters[sysid] = {}
            self.total_params[sysid] = 0
            self.params_received[sysid] = 0
            self._last_mode[sysid] = ""
            self._last_hud_summary[sysid] = (-1.0, -1.0, -1.0)
            self._modes_emitted[sysid] = False
            self.last_heartbeats[sysid] = time.time()
            self.mount_angles[sysid] = (0.0, 0.0)  # (pitch_deg, yaw_deg)
            self.signals.drone_discovered.emit(self.node_id, sysid, self.color)
        else:
            self.last_heartbeats[sysid] = time.time()

    def run(self):
        """MAVLink reception multiplexer loop with robust hardware cleanup."""
        try:
            print(f"Telemetry [{self.node_id}]: Connecting to {self.connection_string} @ {self.baud}")
            self.master = mavutil.mavlink_connection(self.connection_string, baud=self.baud)
            
            # Broadcast request for all nodes on this pipe to stream data
            self.master.mav.request_data_stream_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,
                4, # 4 Hz
                1  # Start
            )

            while self.running:
                try:
                    with self.lock:
                        msg = self.master.recv_match(blocking=False)
                    if not msg:
                        time.sleep(0.01)
                        continue

                    msg_type = msg.get_type()
                    sysid = msg.get_srcSystem()
                    
                    if msg_type in ['HEARTBEAT', 'GLOBAL_POSITION_INT', 'VFR_HUD', 'SYS_STATUS', 'ATTITUDE', 'STATUSTEXT', 'PARAM_VALUE']:
                        self._ensure_drone(sysid)
                    elif msg_type in ['MOUNT_STATUS', 'MOUNT_ORIENTATION']:
                        self._ensure_drone(sysid)

                    # Watchdog Check — Prune silent drones after 15s of no communication
                    if time.time() - self._last_cleanup_time > 5.0:
                        self._last_cleanup_time = time.time()
                        for s_id in list(self.known_drones):
                            if time.time() - self.last_heartbeats.get(s_id, 0) > 15.0:
                                print(f"Telemetry [{self.node_id}]: Drone {s_id} TIMEOUT (Heartbeat Lost)")
                                self.known_drones.remove(s_id)
                                self.signals.drone_lost.emit(self.node_id, s_id)

                    # --- MISSION PROTOCOL HANDLING ---
                    if msg_type in ('MISSION_REQUEST', 'MISSION_REQUEST_INT'):
                        seq = msg.seq
                        if sysid in self._pending_missions and seq < len(self._pending_missions[sysid]):
                            wp = self._pending_missions[sysid][seq]
                            print(f"Telemetry [{self.node_id}]: Fulfilling Mission Request (Seq {seq}) for SysID {sysid}")
                            with self.lock:
                                self.master.mav.mission_item_int_send(
                                    sysid, msg.target_component, seq,
                                    wp['frame'], wp['command'], wp['current'], wp['autocontinue'],
                                    wp['param1'], wp['param2'], wp['param3'], wp['param4'],
                                    int(wp['x'] * 1e7), int(wp['y'] * 1e7), float(wp['z'])
                                )
                        else:
                            print(f"Telemetry [{self.node_id}]: REJECTED Mission Request (Seq {seq}) for SysID {sysid}")
                    
                    elif msg_type == 'MISSION_ACK':
                        if msg.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                            self.signals.status_text_updated.emit(self.node_id, sysid, "MISSION UPLOADED")
                        else:
                            self.signals.status_text_updated.emit(self.node_id, sysid, f"MISSION REJECTED: {msg.type}")
                        if sysid in self._pending_missions:
                            del self._pending_missions[sysid]

                    elif msg_type == 'GLOBAL_POSITION_INT':
                        lat = msg.lat / 1e7
                        lon = msg.lon / 1e7
                        alt = msg.relative_alt / 1000.0 # meters
                        self.signals.position_updated.emit(self.node_id, sysid, lat, lon, alt)
                    
                    elif msg_type == 'DISTANCE_SENSOR':
                        # LightWare SF20 Lidar Rangefinder 🛰️
                        dist_m = msg.current_distance / 100.0 # cm -> m
                        self.signals.distance_sensor_updated.emit(self.node_id, sysid, dist_m)
                    
                    elif msg_type == 'GPS2_RAW':
                        # Terrain Relative Navigation (TRN) Feed 🛰️
                        self.signals.gps2_updated.emit(self.node_id, sysid, msg.fix_type, msg.eph / 100.0)

                    elif msg_type == 'GPS_INPUT':
                        # Visual Navigation / Source ID 14 🛰️
                        if msg.gps_id == 14:
                            # Map to the same TRN diagnostic signal for HUD persistence 🛡️
                            self.signals.gps2_updated.emit(self.node_id, sysid, msg.fix_type, msg.hdop)

                    elif msg_type == 'EKF_STATUS_REPORT':
                        # Horizontal Position Health Monitor 🛰️
                        self.signals.ekf_status_updated.emit(self.node_id, sysid, int(msg.flags))

                    elif msg_type == 'NAV_CONTROLLER_OUTPUT':
                        # Mission Waypoint Distance 🛰️
                        self.signals.nav_updated.emit(self.node_id, sysid, float(msg.wp_dist))
                    
                    elif msg_type == 'VFR_HUD':
                        # Clean Airspeed and Independent Altitude for HUD display 🛰️
                        # This ensures values persist even if Global Position (GPS) stops.
                        self.signals.hud_updated.emit(
                            self.node_id, sysid, 
                            msg.airspeed,   # Pitot Speed
                            -1.0, 
                            msg.alt,        # Baro / Lidar Alt
                            self._last_mode[sysid]
                        )

                    elif msg_type == 'SYS_STATUS':
                        batt_v = msg.voltage_battery / 1000.0
                        last_batt = self._last_hud_summary[sysid][1]
                        if last_batt == -1.0 or abs(batt_v - last_batt) > 0.1:
                            self._last_hud_summary[sysid] = (self._last_hud_summary[sysid][0], batt_v, self._last_hud_summary[sysid][2])
                            self.signals.hud_updated.emit(self.node_id, sysid, -1.0, batt_v, -1.0, self._last_mode[sysid])

                    elif msg_type == 'HEARTBEAT':
                        is_armed = msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                        self.signals.heartbeat_received.emit(self.node_id, sysid, bool(is_armed))
                        
                        flight_mode = getattr(self.master, 'flightmode', "UNKNOWN")
                        if flight_mode == "UNKNOWN" or flight_mode == "":
                            mapping = self.master.mode_mapping()
                            if mapping:
                                inv_map = {v: k for k, v in mapping.items()}
                                flight_mode = inv_map.get(msg.custom_mode, "")
                            
                            # Standard ArduPilot Fallbacks (Plane/VTOL) 🛰️
                            if not flight_mode:
                                ardu_plane_map = {0:"MANUAL", 1:"CIRCLE", 2:"STABILIZE", 5:"FBWA", 10:"AUTO", 11:"RTL", 12:"LOITER", 13:"TAKEOFF", 14:"TRANSITION", 17:"QSTABILIZE", 18:"QHOVER", 19:"QLOITER"}
                                flight_mode = ardu_plane_map.get(msg.custom_mode, f"MODE_{msg.custom_mode}")

                        if hasattr(self.master, 'mode_mapping'):
                            mapping = self.master.mode_mapping()
                            if mapping and not self._modes_emitted[sysid]:
                                self._modes_emitted[sysid] = True
                                self.signals.modes_available.emit(self.node_id, sysid, list(mapping.keys()))

                        # Emit clean mode name 🛰️ (No prefix)
                        if flight_mode != self._last_mode[sysid]:
                            self._last_mode[sysid] = flight_mode
                            self.signals.hud_updated.emit(self.node_id, sysid, -1.0, -1.0, -1.0, flight_mode)
                        
                        # Emit armed status separately 🛰️
                        self.signals.armed_status_changed.emit(self.node_id, sysid, bool(is_armed))

                    elif msg_type == 'ATTITUDE':
                        roll = math.degrees(msg.roll)
                        pitch = math.degrees(msg.pitch)
                        yaw = math.degrees(msg.yaw)
                        self.signals.attitude_updated.emit(self.node_id, sysid, roll, pitch, yaw)

                    elif msg_type in ('MOUNT_STATUS', 'MOUNT_ORIENTATION'):
                        # Attempt to read mount angles in degrees (field names vary slightly by message)
                        mount_pitch = getattr(msg, 'mount_pitch', None)
                        mount_yaw = getattr(msg, 'mount_yaw', None)
                        mount_roll = getattr(msg, 'mount_roll', None)
                        if mount_pitch is None:
                            mount_pitch = getattr(msg, 'pitch', None)
                        if mount_yaw is None:
                            mount_yaw = getattr(msg, 'yaw', None)
                        if mount_roll is None:
                            mount_roll = getattr(msg, 'roll', None)
                        if mount_pitch is not None and mount_yaw is not None:
                            try:
                                self.mount_angles[sysid] = (float(mount_pitch), float(mount_yaw))
                            except Exception:
                                # Ignore malformed values
                                pass

                    elif msg_type == 'STATUSTEXT':
                        self.signals.status_text_updated.emit(self.node_id, sysid, msg.text)
                    
                    elif msg_type == 'PARAM_VALUE':
                        param_id = msg.param_id
                        param_value = msg.param_value
                        self.parameters[sysid][param_id] = param_value
                        self.signals.parameter_updated.emit(self.node_id, sysid, param_id, param_value)
                        
                        self.total_params[sysid] = msg.param_count
                        self.params_received[sysid] += 1
                        self.signals.parameter_progress.emit(self.node_id, sysid, self.params_received[sysid], self.total_params[sysid])
                        
                        if self.params_received[sysid] >= self.total_params[sysid] and self.total_params[sysid] > 0:
                            self.signals.parameters_loaded.emit(self.node_id, sysid)

                except Exception as e:
                    print(f"MAVLink message process error: {e}")
                    time.sleep(0.01)
        except Exception as e:
            print(f"MAVLink connection error: {e}")
        finally:
            print(f"Telemetry [{self.node_id}]: Shutting down and releasing hardware...")
            if self.master:
                try:
                    self.master.close()
                except:
                    pass
            self.master = None

    def stop(self):
        """Signals the thread to terminate and waits for cleanup."""
        self.running = False
        self.wait(2000)

    # ----------------------------------------------------
    # MAVLink TARGETED TRANSMIT Commands
    # ----------------------------------------------------

    def mount_control(self, target_sysid, pitch, roll, yaw):
        if not self.master: return
        with self.lock:
            self.master.target_system = target_sysid
            self.master.mav.command_long_send(
                self.master.target_system, self.master.target_component,
                mavutil.mavlink.MAV_CMD_DO_MOUNT_CONTROL, 1,
                pitch, roll, yaw, 0, 0, 0,
                mavutil.mavlink.MAV_MOUNT_MODE_MAVLINK_TARGETING
            )

    def arm(self, target_sysid, armed=True):
        """Sends MAV_CMD_COMPONENT_ARM_DISARM to the drone."""
        if not self.master: return
        with self.lock:
            self.master.target_system = target_sysid
            self.master.mav.command_long_send(
                self.master.target_system, self.master.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
                1 if armed else 0, # param1: 0 to disarm, 1 to arm
                0, 0, 0, 0, 0, 0
            )
        print(f"Telemetry [{self.node_id}]: {'ARM' if armed else 'DISARM'} command sent to SysID {target_sysid}")
        
    def set_gps_enabled(self, enabled, is_gps2=False):
        """Custom command to toggle GPS simulation in SITL 🛰️"""
        # Command 31010: Custom GPS Toggle
        # Param1: GPS1 Status (1=On, 0=Off, -1=No Change)
        # Param2: GPS2 Status (1=On, 0=Off, -1=No Change)
        p1 = (1.0 if enabled else 0.0) if not is_gps2 else -1.0
        p2 = (1.0 if enabled else 0.0) if is_gps2 else -1.0
        
        self.master.mav.command_long_send(
            self.master.target_system, self.master.target_component,
            31010, 0, p1, p2, 0, 0, 0, 0, 0
        )
        print(f"Telemetry [{self.node_id}]: GPS {'ENABLE' if enabled else 'DISABLE'} command sent to SysID {self.master.target_system}")

    def set_waypoint(self, target_sysid, lat, lon, alt=50):
        if not self.master: return
        with self.lock:
            self.master.target_system = target_sysid
            self.master.mav.command_long_send(
                self.master.target_system, self.master.target_component,
                mavutil.mavlink.MAV_CMD_DO_REPOSITION, 0, -1,
                mavutil.mavlink.MAV_DO_REPOSITION_FLAGS_CHANGE_MODE, 0, 0,
                lat, lon, alt
            )

    def fetch_parameters(self, target_sysid, param_names=None):
        if not self.master: return
        with self.lock:
            self.master.target_system = target_sysid
            if param_names and isinstance(param_names, list):
                for param in param_names:
                    self.master.mav.param_request_read_send(
                        self.master.target_system, self.master.target_component,
                        param.encode('utf-8'), -1
                    )

    def request_all_params_list(self, target_sysid):
        if not self.master: return
        with self.lock:
            self.master.target_system = target_sysid
            self.parameters[target_sysid].clear()
            self.params_received[target_sysid] = 0
            self.total_params[target_sysid] = 0
            self.master.mav.param_request_list_send(self.master.target_system, self.master.target_component)

    def set_parameter(self, target_sysid, param_id, value):
        if not self.master: return
        with self.lock:
            self.master.target_system = target_sysid
            self.master.mav.param_set_send(
                self.master.target_system, self.master.target_component,
                param_id.encode('utf-8'), float(value),
                mavutil.mavlink.MAV_PARAM_TYPE_REAL32
            )

    def set_flight_mode(self, target_sysid, mode_name):
        if not self.master: return
        with self.lock:
            self.master.target_system = target_sysid
            try:
                # Explicit ArduPilot Plane/VTOL Master ID Map 🛰️
                id_map = {
                    "STABILIZE": 0, "CIRCLE": 1, "FBWA": 5, "AUTO": 10, "RTL": 11,
                    "LOITER": 12, "TAKEOFF": 13, "TRANSITION": 14, "QSTABILIZE": 17,
                    "QHOVER": 18, "QLOITER": 19, "QLAND": 20, "QRTL": 21
                }
                custom_id = id_map.get(mode_name, 0)
                
                if custom_id > 0 or mode_name == "STABILIZE":
                    self.master.mav.command_long_send(
                        target_sysid,
                        self.master.target_component,
                        mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                        0, # Confirmation
                        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, # Param1
                        custom_id, # Param2
                        0, 0, 0, 0, 0 # Param3-7
                    )
                else:
                    self.master.set_mode(mode_name)
            except Exception as e:
                print(f"Failed to set mode: {e}")

    def send_takeoff(self, target_sysid, alt=50.0):
        """Sends MAV_CMD_NAV_TAKEOFF to the drone."""
        if not self.master: return
        
        # Implicitly arm since Brain UI ARM button was removed
        self.arm(target_sysid, True)
        
        with self.lock:
            self.master.target_system = target_sysid
            self.master.mav.command_long_send(
                self.master.target_system, self.master.target_component,
                mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0,
                0, 0, 0, 0, 0, 0, alt
            )
        print(f"Telemetry [{self.node_id}]: Takeoff command (Alt: {alt}m) sent to SysID {target_sysid}")

    def start_mission(self, target_sysid):
        """Switches drone to AUTO mode to begin mission."""
        if not self.master: return
        
        # Implicitly arm since Brain UI ARM button was removed
        self.arm(target_sysid, True)
        
        with self.lock:
            self.master.target_system = target_sysid
            # Force ArduPilot Plane AUTO mode (10) via explicit MAV_CMD_DO_SET_MODE 🛰️
            self.master.mav.command_long_send(
                target_sysid,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                0, # Confirmation
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, # Param1
                10, # Param2: AUTO 🛰️
                0, 0, 0, 0, 0
            )
            print(f"Telemetry [{self.node_id}]: Explicit Mission Start (ID: 10) sent to SysID {target_sysid}")

    def upload_mission(self, target_sysid, wps):
        """
        wps: list of dicts {lat, lon, alt, speed}
        Translates to MAVLink mission sequence (Seq 0 is HOME).
        """
        if not self.master: return
        self.master.target_system = target_sysid
        
        # Construct ArduPilot mission sequence
        # Seq 0: MAV_CMD_NAV_WAYPOINT (Home - required placeholder)
        # We'll use the first WP as home if none exists
        full_mission = []
        
        # Home (Entry 0)
        full_mission.append({
            'frame': mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            'command': mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
            'current': 0, 'autocontinue': 1,
            'param1': 0, 'param2': 0, 'param3': 0, 'param4': 0,
            'x': wps[0]['lat'], 'y': wps[0]['lon'], 'z': wps[0]['alt']
        })
        
        last_speed = -1
        for i, wp in enumerate(wps):
            # 1. Inject Speed Change ONLY if it changes or is the first WP
            if wp['speed'] != last_speed:
                full_mission.append({
                    'frame': mavutil.mavlink.MAV_FRAME_MISSION,
                    'command': mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED,
                    'current': 0, 'autocontinue': 1,
                    'param1': 1, # Type: Groundspeed
                    'param2': wp['speed'], # Speed
                    'param3': -1, 'param4': 0,
                    'x': 0, 'y': 0, 'z': 0
                })
                last_speed = wp['speed']
            
            # 2. Waypoint
            full_mission.append({
                'frame': mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                'command': mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                'current': 1 if i == 0 else 0, # Seq 1 is the first nav point usually
                'autocontinue': 1,
                'param1': 0, 'param2': 0, 'param3': 0, 'param4': 0,
                'x': wp['lat'], 'y': wp['lon'], 'z': wp['alt']
            })
            
        self._pending_missions[target_sysid] = full_mission
        with self.lock:
            self.master.mav.mission_count_send(target_sysid, self.master.target_component, len(full_mission))
        print(f"Telemetry [{self.node_id}]: Initiating upload of {len(full_mission)} items to SysID {target_sysid}")

