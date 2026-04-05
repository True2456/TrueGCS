from pymavlink import mavutil
import time
import socket

def diagnose_telemetry():
    print("--- GCS Telemetry Sniffer: Initiating Search ---", flush=True)
    print("Listening on UDP 0.0.0.0:14550...", flush=True)
    
    try:
        # Create a raw listener to see what's actually hitting the port
        connection = mavutil.mavlink_connection('udpin:0.0.0.0:14550')
    except Exception as e:
        print(f"ERROR: Could not bind to port 14550. Is the GCS already running? {e}", flush=True)
        return

    start_time = time.time()
    packet_count = 0
    
    print("Scanning for GLOBAL_POSITION_INT and HEARTBEAT packets...", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    try:
        while True:
            msg = connection.recv_match(type=['GLOBAL_POSITION_INT', 'HEARTBEAT'], blocking=True, timeout=1.0)
            
            if msg:
                packet_count += 1
                sysid = msg.get_srcSystem()
                compid = msg.get_srcComponent()
                msg_type = msg.get_type()
                
                if msg_type == 'GLOBAL_POSITION_INT':
                    lat = msg.lat / 1e7
                    lon = msg.lon / 1e7
                    alt = msg.relative_alt / 1000.0
                    
                    # ALERT: Flag ghost coordinates
                    status = "[DRONE]"
                    if lat == 0 and lon == 0:
                        status = "[GHOST!]"
                    elif sysid == 255 or sysid == 0:
                        status = "[LOOPBACK]"
                        
                    print(f"{status} SysID: {sysid:3} | CompID: {compid:3} | Lat: {lat:11.7f} | Lon: {lon:11.7f} | Alt: {alt:5.1f}m", flush=True)
                
                elif msg_type == 'HEARTBEAT':
                    # Only print every 10th heartbeat to avoid flooding, unless it's a new system
                    if packet_count % 10 == 0:
                        print(f"[HB_ALIVE] SysID: {sysid:3} | CompID: {compid:3} | Type: {msg.type} | Autopilot: {msg.autopilot}", flush=True)

            if time.time() - start_time > 30:
                print("--- Diagnostic Session Timeout (30s) ---", flush=True)
                break
                
    except KeyboardInterrupt:
        print("\n--- Diagnostic Session Interrupted by User ---", flush=True)
    finally:
        connection.close()

if __name__ == "__main__":
    diagnose_telemetry()
