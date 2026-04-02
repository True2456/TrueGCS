import time
from pymavlink import mavutil

def test_mission_upload():
    print("Connecting to SITL on UDP 127.0.0.1:14550...")
    # GCS connects to the same port the SITL broadcasts to
    master = mavutil.mavlink_connection('udpin:0.0.0.0:14550')
    
    print("Waiting for heartbeat...")
    master.wait_heartbeat()
    print(f"Heartbeat from system {master.target_system} component {master.target_component}")

    # Define a simple mission (3 waypoints)
    wps = [
        {'lat': -29.987, 'lon': 153.228, 'alt': 50},
        {'lat': -29.988, 'lon': 153.229, 'alt': 50},
        {'lat': -29.989, 'lon': 153.230, 'alt': 50}
    ]

    print(f"Uploading mission with {len(wps)} items...")
    
    # 1. Send MISSION_COUNT
    master.mav.mission_count_send(master.target_system, master.target_component, len(wps))
    
    start_time = time.time()
    uploaded_count = 0
    
    while uploaded_count < len(wps):
        if time.time() - start_time > 10:
            print("FAILED: Mission upload timed out!")
            return False
            
        msg = master.recv_match(type=['MISSION_REQUEST_INT', 'MISSION_ACK'], blocking=True, timeout=1)
        if not msg:
            continue
            
        if msg.get_type() == 'MISSION_REQUEST_INT':
            seq = msg.seq
            wp = wps[seq]
            print(f"Sending waypoint #{seq}...")
            master.mav.mission_item_int_send(
                master.target_system, master.target_component, seq,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                0, 1, 0, 0, 0, 0,
                int(wp['lat'] * 1e7), int(wp['lon'] * 1e7), wp['alt']
            )
            uploaded_count += 1
            
        elif msg.get_type() == 'MISSION_ACK':
            if msg.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                print("SUCCESS: Mission accepted by SITL!")
                return True
            else:
                print(f"FAILED: Mission rejected with type {msg.type}")
                return False
                
    # Final check for ACK if not received in loop
    msg = master.recv_match(type='MISSION_ACK', blocking=True, timeout=2)
    if msg and msg.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
        print("SUCCESS: Mission accepted by SITL!")
        return True
    
    print("FAILED: Did not receive MISSION_ACK from SITL.")
    return False

if __name__ == "__main__":
    test_mission_upload()
