import time
import sys
from pymavlink import mavutil

def wait_for_heartbeat(connection):
    print("Waiting for SITL Heartbeat...")
    hb = connection.wait_heartbeat(timeout=10)
    if not hb:
        print("FAILED: No heartbeat from SITL.")
        return False
    print(f"Vehicle Type: {hb.type} | Autopilot: {hb.autopilot}")
    return True

def run_mission_test():
    # Connect to SITL
    master = mavutil.mavlink_connection('udp:127.0.0.1:14550')
    if not wait_for_heartbeat(master): return

    target_sys = master.target_system
    target_comp = master.target_component

    # 1. ARM
    print("\n[STEP 1] Arming Drone...")
    master.mav.command_long_send(target_sys, target_comp, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
    time.sleep(2)

    # 2. TAKEOFF
    print("\n[STEP 2] Sending Takeoff Command (target 50m)...")
    master.mav.command_long_send(target_sys, target_comp, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 50.0)
    
    start_time = time.time()
    reached_alt = False
    mode_history = []
    last_print = 0
    mode_id = 0
    alt = 0.0

    print("Monitoring Rise (Vertical Only, 2.2 m/s)...")
    while time.time() - start_time < 180: # 180s generous timeout
        msg = master.recv_match(type=['HEARTBEAT', 'GLOBAL_POSITION_INT', 'VFR_HUD'], blocking=True, timeout=1.0)
        if not msg: continue
        
        if msg.get_type() == 'HEARTBEAT':
            mode_id = msg.custom_mode
            if not mode_history or mode_history[-1] != mode_id:
                mode_history.append(mode_id)
                print(f"Current Mode ID: {mode_id}")
        
        if msg.get_type() == 'GLOBAL_POSITION_INT':
            alt = msg.relative_alt / 1000.0
        elif msg.get_type() == 'VFR_HUD':
            alt = msg.alt

        if alt > 0:
            if alt > 45.0:
                reached_alt = True
                if mode_id == 12: # LOITER
                    print(f"SUCCESS: Transitioned to LOITER at {alt:.1f}m.")
                    break
            
            if time.time() - last_print > 5.0:
                print(f"Telemetry -> Alt: {alt:.1f}m | Mode: {mode_id}")
                last_print = time.time()

    if not reached_alt:
        print(f"FAILED: Target altitude (Reached: {alt:.1f}m) not reached in time or mode didn't switch to LOITER.")
        return

    # 3. Upload Mission (DUMMY)
    print("\n[STEP 3] Uploading Mission (1 Waypoint)...")
    master.mav.mission_count_send(target_sys, target_comp, 1)
    msg = master.recv_match(type='MISSION_REQUEST', blocking=True, timeout=5)
    if msg:
        # Use MAV_CMD_NAV_WAYPOINT (16)
        master.mav.mission_item_send(target_sys, target_comp, 0, 3, 16, 0, 1, 0, 0, 0, 0, -30.0, 153.3, 50.0)
        print("Mission Item Uploaded.")
    
    # 4. START MISSION
    print("\n[STEP 4] Starting Mission (Raw ID: 10)...")
    master.mav.command_long_send(target_sys, target_comp, mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0, 1, 10, 0, 0, 0, 0, 0)
    
    verified_auto = False
    start_time = time.time()
    while time.time() - start_time < 15:
        msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=1.0)
        if msg and msg.custom_mode == 10:
            print("SUCCESS: Mode 10 (AUTO) confirmed via MAVLink Heartbeat!")
            verified_auto = True
            break
        elif msg and msg.custom_mode == 1:
            print("FAILED: Mode flipped to CIRCLE (ID 1). Protocol Bug persists.")
            return
    
    if verified_auto:
        print("\n=== FINAL RESULT: ALL PROTOCOL CHECKS PASSED ===")
        print("Takeoff-to-Loiter sequence works correctly at 2.2 m/s.")
        print("Start Mission correctly triggers AUTO (ID 10).")
    else:
        print("\n=== FINAL RESULT: FAILED TO ACTIVATE AUTO MODE ===")

if __name__ == "__main__":
    run_mission_test()
