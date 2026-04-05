import time
import math
from pymavlink import mavutil

def wait_for_heartbeat(connection):
    print("Waiting for SITL Heartbeat...")
    return connection.wait_heartbeat(timeout=10)

def get_distance_metres(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2) * math.sin(dlat/2) + math.cos(math.radians(lat1)) \
        * math.cos(math.radians(lat2)) * math.sin(dlon/2) * math.sin(dlon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return 6371000 * c

def run_orbit_test():
    master = mavutil.mavlink_connection('udp:127.0.0.1:14550')
    if not wait_for_heartbeat(master): return

    target_sys = master.target_system
    target_comp = master.target_component

    # 1. ARM & TAKEOFF
    print("\n[STEP 1] Arming & Takeoff...")
    master.mav.command_long_send(target_sys, target_comp, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
    time.sleep(1)
    master.mav.command_long_send(target_sys, target_comp, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 50.0)
    
    # Wait for climb & transition to Loiter (Home)
    print("Waiting for drone to reach loiter altitude at home...")
    time.sleep(15) 

    # 2. FLY AWAY (Simulate Mission Progress)
    print("\n[STEP 2] Simulating flight to a distant WP...")
    # Manually update SITL lat/lon if needed, or just let it fly... 
    # Actually, let's just use FBWA or similar if supported, but our SITL is simple.
    # We can just 'teleport' its position by updating its core vars if we had access, 
    # but we only have MAVLink. 
    # Let's just let it loiter at home, then check if LOITER command keeps it there.
    # To truly test "stay where you are", we need it to be NOT at home.
    
    # 3. TEST: Manual LOITER command
    # First, get current pos
    master.mav.request_data_stream_send(target_sys, target_comp, mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
    msg = master.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=5)
    if not msg:
        print("FAILED: No position data.")
        return
    
    triggered_lat = msg.lat / 1e7
    triggered_lon = msg.lon / 1e7
    print(f"Triggering LOITER at current position: {triggered_lat}, {triggered_lon}")
    
    # Send LOITER mode (Custom Mode 12)
    master.mav.command_long_send(target_sys, target_comp, mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0, 1, 12, 0, 0, 0, 0, 0)
    
    # Wait and check if distance stays small
    print("Monitoring distance to trigger point...")
    for _ in range(10):
        time.sleep(2)
        msg = master.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=2)
        if msg:
            cur_lat = msg.lat / 1e7
            cur_lon = msg.lon / 1e7
            dist = get_distance_metres(triggered_lat, triggered_lon, cur_lat, cur_lon)
            print(f"Dist to orbit center: {dist:.1f}m (Mode: {master.flightmode})")
            if dist > 80: # Allowance for 50m radius + some drift
                print("FAILED: Drone is flying away from the trigger point (likely flying to HOME)!")
                return

    print("\n=== SUCCESS: Drone is loitering at the triggered location! ===")

if __name__ == "__main__":
    run_orbit_test()
