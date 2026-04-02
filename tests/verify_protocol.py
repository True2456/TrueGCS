import time
from pymavlink import mavutil

def test_heartbeat_modes():
    print("MAVLink Protocol Verification Script")
    # Connect to the SITL (Listening on 14550)
    master = mavutil.mavlink_connection('udpin:0.0.0.0:14550')
    
    print("Waiting for Heartbeat...")
    hb = master.wait_heartbeat(timeout=5)
    if not hb:
        print("FAIL: No heartbeat received from SITL.")
        return

    print(f"Vehicle Type: {hb.type} (MAV_TYPE_VTOL_DUOROTOR is 21)")
    print(f"Autopilot: {hb.autopilot} (MAV_AUTOPILOT_ARDUPILOTMEGA is 3)")
    print(f"Base Mode Flags: {bin(hb.base_mode)}")
    print(f"Custom Mode ID: {hb.custom_mode}")
    
    # Check if pymavlink can map it
    print(f"Pymavlink mapped flight mode: {getattr(master, 'flightmode', 'UNKNOWN')}")
    
    # Try setting AUTO explicitly
    print("\nAttempting to set mode 'AUTO' (should be 10 for Plane)...")
    master.set_mode('AUTO')
    
    # Monitor result for 3 seconds
    start_t = time.time()
    while time.time() - start_t < 3:
        msg = master.wait_heartbeat(timeout=1)
        if msg:
            mode_name = getattr(master, 'flightmode', 'UNKNOWN')
            print(f"Current SITL Heartbeat -> ID: {msg.custom_mode} | Name: {mode_name}")
            if msg.custom_mode == 10:
                print("SUCCESS: AUTO correctly reached (ID 10).")
                break
            elif msg.custom_mode == 1:
                print("BUG DETECTED: Requested AUTO but reached CIRCLE (ID 1).")
                break

if __name__ == "__main__":
    test_heartbeat_modes()
