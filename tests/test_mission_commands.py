import time
import sys
import os
import subprocess
from pymavlink import mavutil

def test_mission_commands():
    print("Testing MAVLink 'DO' Command Handling (Speed Change Injection)...")
    connection_string = 'udpin:0.0.0.0:14550'
    master = mavutil.mavlink_connection(connection_string)
    
    print("Waiting for SITL heartbeat...")
    master.wait_heartbeat()
    print("Connected.")

    # Mission with Speed Change Injection
    # Seq 0: Home
    # Seq 1: WP (Lat A)
    # Seq 2: DO_CHANGE_SPEED (Expected to be skipped as a nav target)
    # Seq 3: WP (Lat B)
    
    def send_wp(seq, cmd, x, y, z, p2=0):
        master.mav.mission_item_int_send(
            master.target_system, master.target_component, seq,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            cmd, 0, 1, 0, p2, 0, 0,
            int(x * 1e7), int(y * 1e7), int(z)
        )

    wps = [
        (mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, -29.987, 153.228, 50),
        (mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, -29.988, 153.229, 50),
        (mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED, 0, 0, 0, 25), # Param 2 is speed
        (mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, -29.989, 153.230, 50)
    ]

    print(f"Uploading mission with {len(wps)} items...")
    master.mav.mission_count_send(master.target_system, master.target_component, len(wps))
    
    for i in range(len(wps)):
        msg = master.recv_match(type='MISSION_REQUEST_INT', blocking=True, timeout=5)
        if not msg: raise Exception("No request")
        cmd, x, y, z, p2 = 0, 0, 0, 0, 0
        if wps[i][0] == mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED:
            cmd, x, y, z = wps[i][0], 0, 0, 0
            p2 = wps[i][4]
        else:
            cmd, x, y, z = wps[i]
        
        send_wp(i, cmd, x, y, z, p2)

    msg = master.recv_match(type='MISSION_ACK', blocking=True, timeout=5)
    print(f"Mission ACK: {msg.type}")

    print("Arming...")
    master.mav.command_long_send(master.target_system, master.target_component, 
                                 mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
    master.wait_heartbeat()
    
    print("Starting Mission (AUTO)...")
    master.mav.set_mode_send(master.target_system, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 10)
    
    start_time = time.time()
    reached = []
    while time.time() - start_time < 40:
        msg = master.recv_match(type='MISSION_ITEM_REACHED', blocking=True, timeout=0.1)
        if msg:
            print(f"Reached Sequence: {msg.seq}")
            reached.append(msg.seq)
            if msg.seq == 3:
                print("SUCCESS: Target Waypoint 3 reached despite speed change injection at Seq 2.")
                return True
    
    print(f"FAILED: Reached {reached}")
    return False

if __name__ == "__main__":
    # Start SITL in background
    sitl_proc = subprocess.Popen([sys.executable, "simulation/vtol_sim.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(3)
    try:
        success = test_mission_commands()
        if not success: sys.exit(1)
    finally:
        sitl_proc.terminate()
