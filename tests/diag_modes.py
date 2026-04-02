import time
from pymavlink import mavutil

def diagnose():
    print("SITL Mode Diagnostic Tool")
    print("Connecting to SITL on UDPIN 0.0.0.0:14550...")
    
    # Connect as if we were the GCS (Listening on 14550)
    master = mavutil.mavlink_connection('udpin:0.0.0.0:14550')
    
    print("Waiting for Heartbeat...")
    hb = master.wait_heartbeat(timeout=5)
    if not hb:
        print("FAIL: No heartbeat received from SITL.")
        return
    
    print(f"HB Received - SysID: {master.target_system}, CompID: {master.target_component}")
    print(f"Initial Mode (ID): {hb.custom_mode}")
    print(f"Initial FlightMode (Name): {getattr(master, 'flightmode', 'UNKNOWN')}")
    
    modes_to_test = ["AUTO", "CIRCLE", "QLOITER", "STABILIZE"]
    
    for mode in modes_to_test:
        print(f"\nRequesting Mode Change to: {mode}")
        master.set_mode(mode)
        
        # Wait for acknowledgment in heartbeat
        start_t = time.time()
        success = False
        while time.time() - start_t < 3:
            msg = master.wait_heartbeat(timeout=1)
            if msg and getattr(master, 'flightmode', 'UNKNOWN') == mode:
                print(f"SUCCESS: SITL reported mode {mode} (ID: {msg.custom_mode})")
                success = True
                break
        
        if not success:
            print(f"FAIL: SITL did not transition to {mode}. Last reported mode: {getattr(master, 'flightmode', 'UNKNOWN')} (ID: {master.messages['HEARTBEAT'].custom_mode if 'HEARTBEAT' in master.messages else 'N/A'})")

    print("\nDiagnostic Complete.")

if __name__ == "__main__":
    diagnose()
