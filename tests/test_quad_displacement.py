import time
import math
from pymavlink import mavutil

def get_distance(lat1, lon1, lat2, lon2):
    return math.sqrt((lat2-lat1)**2 + (lon2-lon1)**2) * 1.113195e5

def test_displacement():
    master = mavutil.mavlink_connection('udp:127.0.0.1:14550')
    print("Connecting to Quad SITL...")
    master.wait_heartbeat()
    
    target_lat = -29.987222 + 0.001 # approx 110m North
    target_lon = 153.228056
    
    print("[STEP 1] Arming & Takeoff...")
    master.mav.command_long_send(master.target_system, master.target_component, 
                                 mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
    time.sleep(1)
    master.mav.command_long_send(master.target_system, master.target_component, 
                                 mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 30.0)
    
    print("Waiting for takeoff height...")
    time.sleep(10)
    
    print("[STEP 2] Uploading 100m North Waypoint...")
    master.mav.mission_count_send(master.target_system, master.target_component, 1)
    msg = master.recv_match(type=['MISSION_REQUEST', 'MISSION_REQUEST_INT'], blocking=True, timeout=5)
    if msg:
        master.mav.mission_item_int_send(master.target_system, master.target_component, 0, 
                                         6, 16, 0, 1, 0, 0, 0, 0, int(target_lat*1e7), int(target_lon*1e7), 30)
        print("Mission Uploaded.")

    print("[STEP 3] Switching to AUTO...")
    master.mav.command_long_send(master.target_system, master.target_component, 
                                 mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0, 1, 3, 0, 0, 0, 0, 0)
    
    print("\n[VERIFICATION] Monitoring Displacement for 10 seconds...")
    last_dist = 999999
    start_pos = None
    
    for i in range(20):
        msg = master.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=1.0)
        if msg:
            cur_lat = msg.lat / 1e7
            cur_lon = msg.lon / 1e7
            if start_pos is None: start_pos = (cur_lat, cur_lon)
            
            dist = get_distance(cur_lat, cur_lon, target_lat, target_lon)
            travelled = get_distance(cur_lat, cur_lon, start_pos[0], start_pos[1])
            print(f"Dist to Target: {dist:.1f}m | Travelled from Start: {travelled:.1f}m")
            
            if dist < last_dist:
                last_dist = dist
            
        time.sleep(0.5)

    if travelled > 10.0:
        print("\nSUCCESS: Quadcopter is ACTIVELY TRAVELING (Displacement > 10m)")
    else:
        print("\nFAILED: Quadcopter is STATIONARY (Displacement < 10m)")

if __name__ == '__main__':
    test_displacement()
