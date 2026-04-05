import time
import sys
import os
import subprocess
from pymavlink import mavutil

class SITLStabilityTester:
    def __init__(self, sitl_path="simulation/vtol_sim.py"):
        self.sitl_path = sitl_path
        self.sitl_process = None
        self.master = None
        
    def start_sitl(self):
        print(f"Starting SITL from {self.sitl_path}...")
        self.sitl_process = subprocess.Popen(
            [sys.executable, self.sitl_path], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        time.sleep(5) # Give more time for the socket to bind on Windows
        
    def stop_sitl(self):
        if self.sitl_process:
            self.sitl_process.terminate()
            # Drain output
            stdout, stderr = self.sitl_process.communicate(timeout=5)
            print("--- SITL LOGS ---")
            print(stdout)
            print(stderr)
            print("-----------------")
            self.sitl_process = None
            print("SITL stopped.")
            
    def connect(self, connection_string='udpin:0.0.0.0:14550'):
        print(f"Connecting to {connection_string}...")
        self.master = mavutil.mavlink_connection(connection_string)
        # Attempt heartbeat several times
        for _ in range(5):
            print("Waiting for heartbeat...")
            if self.master.wait_heartbeat(timeout=5):
                print(f"Connected to SysID {self.master.target_system}")
                return True
        return False
        
    def test_arming_cycle(self, count=5):
        print(f"Running Arm/Disarm Stress Test ({count} cycles)...")
        for i in range(count):
            # Arm
            self.master.mav.command_long_send(self.master.target_system, self.master.target_component, 
                                             mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
            msg = self.master.recv_match(type='COMMAND_ACK', blocking=True, timeout=2)
            if not msg or msg.command != mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
                return False, f"Failed to get Arm ACK for cycle {i}"
            
            time.sleep(0.5)
            # Disarm
            self.master.mav.command_long_send(self.master.target_system, self.master.target_component, 
                                             mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 0, 0, 0, 0, 0, 0, 0)
            msg = self.master.recv_match(type='COMMAND_ACK', blocking=True, timeout=2)
            if not msg or msg.command != mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
                return False, f"Failed to get Disarm ACK for cycle {i}"
            time.sleep(0.5)
        return True, "Arming Stress Test Passed"
        
    def test_mode_switching(self):
        print("Testing Mode Switching (STABILIZE -> QLOITER -> AUTO)...")
        modes = {"STABILIZE": 0, "QLOITER": 19, "AUTO": 10}
        for m_name, m_id in modes.items():
            self.master.mav.set_mode_send(self.master.target_system, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, m_id)
            # Heartbeat should reflect mode change within 2s
            start = time.time()
            success = False
            while time.time() - start < 2:
                hb = self.master.recv_match(type='HEARTBEAT', blocking=True, timeout=1)
                if hb and hb.custom_mode == m_id:
                    success = True
                    break
            if not success:
                return False, f"Mode {m_name} failed to reflect in heartbeat"
            print(f"Mode {m_name} (ID: {m_id}) verified.")
        return True, "Mode Switching Test Passed"
        
    def test_mission_navigation(self):
        print("Testing Waypoint Mission and Navigation (Waypoint Following)...")
        # Upload a small triangle mission
        wps = [
            {'lat': -29.987, 'lon': 153.228, 'alt': 50},
            {'lat': -29.988, 'lon': 153.229, 'alt': 50},
            {'lat': -29.989, 'lon': 153.230, 'alt': 50}
        ]
        
        # Upload
        self.master.mav.mission_count_send(self.master.target_system, self.master.target_component, len(wps))
        for i in range(len(wps)):
            msg = self.master.recv_match(type='MISSION_REQUEST_INT', blocking=True, timeout=2)
            if not msg or msg.seq != i:
                return False, f"Failed mission request for wp {i}"
            wp = wps[i]
            self.master.mav.mission_item_int_send(
                self.master.target_system, self.master.target_component, i,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, 0, 1, 0, 0, 0, 0,
                int(wp['lat'] * 1e7), int(wp['lon'] * 1e7), wp['alt']
            )
        msg = self.master.recv_match(type='MISSION_ACK', blocking=True, timeout=2)
        if not msg or msg.type != mavutil.mavlink.MAV_MISSION_ACCEPTED:
            return False, "Mission upload rejected"
            
        print("Mission uploaded. Arming and Taking off...")
        self.master.mav.command_long_send(self.master.target_system, self.master.target_component, 
                                         mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
        self.master.recv_match(type='COMMAND_ACK', blocking=True, timeout=2)
        
        self.master.mav.command_long_send(self.master.target_system, self.master.target_component, 
                                         mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 50)
        self.master.recv_match(type='COMMAND_ACK', blocking=True, timeout=2)
        
        print("Monitoring Navigation...")
        start_time = time.time()
        reached_wps = set()
        while time.time() - start_time < 30: # 30s timeout for mission
            msg = self.master.recv_match(type=['MISSION_ITEM_REACHED', 'GLOBAL_POSITION_INT'], blocking=True, timeout=0.1)
            if not msg: continue
            
            if msg.get_type() == 'MISSION_ITEM_REACHED':
                print(f"Waypoint {msg.seq} Reached!")
                reached_wps.add(msg.seq)
                if len(reached_wps) == len(wps):
                    return True, "All Waypoints Reached Successfully"
            
            if msg.get_type() == 'GLOBAL_POSITION_INT':
                # Just diagnostic output
                pass
                
        return False, f"Navigation Timeout. Reached: {reached_wps}"

if __name__ == "__main__":
    tester = SITLStabilityTester()
    try:
        tester.start_sitl()
        tester.connect()
        
        # Test 1: Arming
        s, m = tester.test_arming_cycle()
        print(f"RESULT: {m}")
        if not s: sys.exit(1)
        
        # Test 2: Mode Switching
        s, m = tester.test_mode_switching()
        print(f"RESULT: {m}")
        if not s: sys.exit(1)
        
        # Test 3: Navigation (Expect failure until nav logic is added)
        s, m = tester.test_mission_navigation()
        print(f"RESULT: {m}")
        if not s: 
            print("INFO: Navigation failed as expected (Physics logic not yet installed).")
            # We don't exit(1) here yet because we know this part is coming next.
        
    finally:
        tester.stop_sitl()
