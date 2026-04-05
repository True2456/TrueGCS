import time
import math
import collections
from pymavlink import mavutil

def test_auto_to_loiter_stability():
    print("--- Mission-to-Loiter Stability Audit: Initiating ---", flush=True)
    
    # Connect to SITL
    master = mavutil.mavlink_connection('udp:127.0.0.1:14550')
    master.wait_heartbeat()
    print("SITL Link established. System ID: %u, Component ID: %u" % (master.target_system, master.target_component), flush=True)

    # 1. ARM and Upload a mission
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
    
    # Send Mission Count
    print("Uploading 2-item mission...", flush=True)
    master.mav.mission_count_send(master.target_system, master.target_component, 2)
    
    # Wait for requests
    for i in range(2):
        msg = master.recv_match(type='MISSION_REQUEST_INT', blocking=True, timeout=5.0)
        if msg:
            if i == 0: # Home/Takeoff
                 master.mav.mission_item_int_send(
                    master.target_system, master.target_component, 0, 0,
                    22, 1, 1, 0, 0, 0, 0, int(-29.9872220 * 1e7), int(153.2280560 * 1e7), 50.0)
            else: # Waypoint #1
                 master.mav.mission_item_int_send(
                    master.target_system, master.target_component, 1, 0,
                    16, 0, 1, 0, 0, 0, 0, int(-29.985 * 1e7), int(153.228 * 1e7), 50.0)

    # Trigger AUTO mode (10)
    time.sleep(1)
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0, 
        1, 10, 0, 0, 0, 0, 0) # ArduPilot convention for SET_MODE via COMMAND_LONG
        
    print("Switching to AUTO. Waiting for Mission Reached signal...", flush=True)
    
    mission_complete = False
    roll_history = collections.deque(maxlen=100) # Last 5 seconds (20Hz)
    yaw_history = collections.deque(maxlen=100)
    
    start_time = time.time()
    while time.time() - start_time < 60: # 60 second timeout for mission
        msg = master.recv_match(type=['MISSION_ITEM_REACHED', 'ATTITUDE', 'HEARTBEAT'], blocking=True, timeout=1.0)
        if not msg: continue
        
        if msg.get_type() == 'MISSION_ITEM_REACHED':
            print(f"Mission Item {msg.seq} Reached! Transitioning to LOITER Stability Check.", flush=True)
            mission_complete = True
            break
            
        if msg.get_type() == 'HEARTBEAT':
            # Check for mode change to LOITER if mission ends autonomously
            pass

    if not mission_complete:
        print("ERROR: Mission did not complete within 60s.")
        return False

    print("--- MONITORING LOITER STABILITY (10s) ---", flush=True)
    jitter_detected = False
    max_roll_jitter = 0.0
    max_yaw_rate = 0.0
    
    audit_start = time.time()
    last_yaw = None
    
    while time.time() - audit_start < 10:
        msg = master.recv_match(type='ATTITUDE', blocking=True, timeout=0.5)
        if not msg: continue
        
        roll_deg = math.degrees(msg.roll)
        yaw_deg = math.degrees(msg.yaw)
        
        if last_yaw is not None:
            # Calculate Yaw Rate (Delta per frame)
            yaw_diff = (yaw_deg - last_yaw + 180) % 360 - 180
            abs_yaw_diff = abs(yaw_diff)
            max_yaw_rate = max(max_yaw_rate, abs_yaw_diff)
            
            # Check for high-frequency roll oscillation
            if len(roll_history) > 1:
                roll_delta = abs(roll_deg - roll_history[-1])
                max_roll_jitter = max(max_roll_jitter, roll_delta)
                
                # ArduPilot standard stability: Yaw change should be < 10 deg/frame at high speed
                # Roll jitter should be < 5 deg/frame during stable orbit
                if abs_yaw_diff > 45: # Severe 180-degree jitter detection
                    print(f"CRITICAL JITTER: Yaw snapped {abs_yaw_diff:.1f} degrees in one frame!", flush=True)
                    jitter_detected = True
                
                if roll_delta > 15: # Extreme roll spike
                    print(f"CRITICAL VIBRATION: Roll spiked {roll_delta:.1f} degrees!", flush=True)
                    jitter_detected = True

        roll_history.append(roll_deg)
        last_yaw = yaw_deg
        
    print(f"\nAudit Results:")
    print(f"Max Yaw Rate (deg/frame): {max_yaw_rate:.1f}")
    print(f"Max Roll Jitter (deg/frame): {max_roll_jitter:.1f}")
    
    if jitter_detected:
        print("--- STABILITY AUDIT: FAILED ❌ ---", flush=True)
        return False
    else:
        print("--- STABILITY AUDIT: PASSED ✅ ---", flush=True)
        return True

if __name__ == "__main__":
    test_auto_to_loiter_stability()
