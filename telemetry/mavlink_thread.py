import time
import math
from PySide6.QtCore import QThread, Signal, QObject
from pymavlink import mavutil

class TelemetrySignals(QObject):
    # Signals for updating the UI
    heartbeat_received = Signal(bool)
    position_updated = Signal(float, float, float) # lat, lon, alt
    attitude_updated = Signal(float, float, float) # roll, pitch, yaw
    hud_updated = Signal(float, float, float, str) # speed, battery, alt, mode
    status_text_updated = Signal(str)
    parameter_updated = Signal(str, float)
    parameters_loaded = Signal()
    parameter_progress = Signal(int, int) # current, total
    modes_available = Signal(list)

class TelemetryThread(QThread):
    def __init__(self, connection_string="COM18", baud=115200, parent=None):
        super().__init__(parent)
        self.connection_string = connection_string
        self.baud = baud
        self.running = True
        self.signals = TelemetrySignals()
        self.master = None
        self.parameters = {}
        self.total_params = 0
        self.params_received = 0
        
        # Signal throttling / cache (Init with -1.0 to force first update)
        self._last_mode = ""
        self._last_hud_summary = (-1.0, -1.0, -1.0) # speed, batt, alt

    def run(self):
        """MAVLink reception loop with robust hardware cleanup."""
        try:
            print(f"Telemetry: Connecting to {self.connection_string} @ {self.baud}")
            self.master = mavutil.mavlink_connection(self.connection_string, baud=self.baud)
            
            # Request some basic data streams
            self.master.mav.request_data_stream_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,
                4, # 4 Hz
                1  # Start
            )

            while self.running:
                try:
                    msg = self.master.recv_match(blocking=False)
                    if not msg:
                        time.sleep(0.01)
                        continue

                    msg_type = msg.get_type()

                    if msg_type == 'GLOBAL_POSITION_INT':
                        lat = msg.lat / 1e7
                        lon = msg.lon / 1e7
                        alt = msg.relative_alt / 1000.0 # meters
                        self.signals.position_updated.emit(lat, lon, alt)
                    
                    elif msg_type == 'VFR_HUD':
                        if abs(msg.groundspeed - self._last_hud_summary[0]) > 0.5:
                            self._last_hud_summary = (msg.groundspeed, self._last_hud_summary[1], self._last_hud_summary[2])
                            self.signals.hud_updated.emit(msg.groundspeed, -1.0, -1.0, "")

                    elif msg_type == 'SYS_STATUS':
                        batt_v = msg.voltage_battery / 1000.0
                        last_batt = self._last_hud_summary[1]
                        if last_batt == -1.0 or abs(batt_v - last_batt) > 0.1:
                            self._last_hud_summary = (self._last_hud_summary[0], batt_v, self._last_hud_summary[2])
                            self.signals.hud_updated.emit(-1.0, batt_v, -1.0, self._last_mode)

                    elif msg_type == 'HEARTBEAT':
                        is_armed = msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                        self.signals.heartbeat_received.emit(True)
                        flight_mode = getattr(self.master, 'flightmode', "UNKNOWN")
                        if flight_mode == "UNKNOWN" or flight_mode == "":
                            mapping = self.master.mode_mapping()
                            if mapping:
                                inv_map = {v: k for k, v in mapping.items()}
                                flight_mode = inv_map.get(msg.custom_mode, f"MODE_{msg.custom_mode}")
                                if not getattr(self, '_modes_emitted', False):
                                    self._modes_emitted = True
                                    self.signals.modes_available.emit(list(mapping.keys()))
                        elif hasattr(self.master, 'mode_mapping'):
                            mapping = self.master.mode_mapping()
                            if mapping and not getattr(self, '_modes_emitted', False):
                                self._modes_emitted = True
                                self.signals.modes_available.emit(list(mapping.keys()))

                        if is_armed:
                            flight_mode = "[ARM] " + flight_mode
                        if flight_mode != self._last_mode:
                            self._last_mode = flight_mode
                            self.signals.hud_updated.emit(-1.0, -1.0, -1.0, flight_mode)

                    elif msg_type == 'ATTITUDE':
                        roll = math.degrees(msg.roll)
                        pitch = math.degrees(msg.pitch)
                        yaw = math.degrees(msg.yaw)
                        self.signals.attitude_updated.emit(roll, pitch, yaw)

                    elif msg_type == 'STATUSTEXT':
                        self.signals.status_text_updated.emit(msg.text)
                    
                    elif msg_type == 'PARAM_VALUE':
                        param_id = msg.param_id
                        param_value = msg.param_value
                        self.parameters[param_id] = param_value
                        self.signals.parameter_updated.emit(param_id, param_value)
                        self.total_params = msg.param_count
                        self.params_received += 1
                        self.signals.parameter_progress.emit(self.params_received, self.total_params)
                        if self.params_received >= self.total_params and self.total_params > 0:
                            self.signals.parameters_loaded.emit()

                except Exception as e:
                    print(f"MAVLink message process error: {e}")
                    time.sleep(0.01)
        except Exception as e:
            print(f"MAVLink connection error: {e}")
        finally:
            print("Telemetry: Shutting down and releasing hardware...")
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

    def mount_control(self, pitch, roll, yaw):
        if not self.master: return
        self.master.mav.command_long_send(
            self.master.target_system, self.master.target_component,
            mavutil.mavlink.MAV_CMD_DO_MOUNT_CONTROL, 1,
            pitch, roll, yaw, 0, 0, 0,
            mavutil.mavlink.MAV_MOUNT_MODE_MAVLINK_TARGETING
        )

    def set_waypoint(self, lat, lon, alt=50):
        if not self.master: return
        self.master.mav.command_long_send(
            self.master.target_system, self.master.target_component,
            mavutil.mavlink.MAV_CMD_DO_REPOSITION, 0, -1,
            mavutil.mavlink.MAV_DO_REPOSITION_FLAGS_CHANGE_MODE, 0, 0,
            lat, lon, alt
        )

    def fetch_parameters(self, param_names=None):
        if not self.master: return
        if param_names and isinstance(param_names, list):
            for param in param_names:
                self.master.mav.param_request_read_send(
                    self.master.target_system, self.master.target_component,
                    param.encode('utf-8'), -1
                )

    def request_all_params_list(self):
        if not self.master: return
        self.parameters.clear()
        self.params_received = 0
        self.total_params = 0
        self.master.mav.param_request_list_send(self.master.target_system, self.master.target_component)

    def set_parameter(self, param_id, value):
        if not self.master: return
        self.master.mav.param_set_send(
            self.master.target_system, self.master.target_component,
            param_id.encode('utf-8'), float(value),
            mavutil.mavlink.MAV_PARAM_TYPE_REAL32
        )

    def set_flight_mode(self, mode_name):
        if not self.master: return
        try:
            self.master.set_mode(mode_name)
        except Exception as e:
            print(f"Failed to set mode: {e}")
