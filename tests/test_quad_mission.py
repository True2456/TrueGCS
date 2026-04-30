import time
from pymavlink import mavutil

def test_quad_mission():
    print("Connecting to Quad SITL on UDP 127.0.0.1:14550...")
    master = mavutil.mavlink_connection('udp:127.0.0.1:14550')
    hb = master.wait_heartbeat()
    print(f"Vehicle Type: {hb.type} | Autopilot: {hb.autopilot}")

    # 1. ARM
    print("\n[STEP 1] Arming Drone...")
    master.mav.command_long_send(master.target_system, master.target_component, 
                                 mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
    time.sleep(2)

    # 2. TAKEOFF
    print("\n[STEP 2] Sending Takeoff Command (target 30m)...")
    master.mav.command_long_send(master.target_system, master.target_component, 
                                 mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 30.0)
    
    start_time = time.time()
    reached_alt = False
    while time.time() - start_time < 30:
        msg = master.recv_match(type=['VFR_HUD', 'HEARTBEAT'], blocking=True, timeout=1.0)
        if not msg: continue
        if msg.get_type() == 'VFR_HUD':
            alt = msg.alt
            if alt > 25.0:
                print(f"Reached Target Alt: {alt:.1f}m")
                reached_alt = True
                break
        if time.time() - start_time % 5 == 0:
            print("Climbing...")

    if not reached_alt:
        print("FAILED: Takeoff climb failed.")
        return

    # 2. Upload Mission
    print("\n[STEP 2] Uploading Mission (1 Waypoint)...")
    master.mav.mission_count_send(master.target_system, master.target_component, 1)
    msg = master.recv_match(type=['MISSION_REQUEST', 'MISSION_REQUEST_INT'], blocking=True, timeout=5)
    if msg:
        master.mav.mission_item_int_send(master.target_system, master.target_component, 0, 
                                         mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, 
                                         16, 0, 1, 0, 0, 0, 0, int(-30.0*1e7), int(153.3*1e7), 30)
        print("Mission Item Uploaded.")

    # 3. START MISSION (AUTO Mode 3 for Copter)
    print("\n[STEP 3] Switching to AUTO (Mode 3)...")
    master.mav.command_long_send(master.target_system, master.target_component, 
                                 mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0, 1, 3, 0, 0, 0, 0, 0)
    
    start_time = time.time()
    while time.time() - start_time < 10:
        msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=1.0)
        if msg and msg.custom_mode == 3:
            print("SUCCESS: Quad in AUTO Mode (3)!")
            print("=== QUADCOPTER MISSION READY ===")
            return
    print("FAILED: Could not activate AUTO mode.")

if __name__ == "__main__":
    test_quad_mission()
