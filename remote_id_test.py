import asyncio
import struct
from bleak import BleakScanner

# ASTM F3411 / OpenDroneID Service UUID
REMOTE_ID_UUID_16 = "0000fffa-0000-1000-8000-00805f9b34fb"

# OpenDroneID Message Types
MSG_TYPE_BASIC_ID = 0
MSG_TYPE_LOCATION = 1
MSG_TYPE_AUTH = 2
MSG_TYPE_SELF_ID = 3
MSG_TYPE_SYSTEM = 4
MSG_TYPE_OPERATOR_ID = 5
MSG_TYPE_MESSAGE_PACK = 0xF

def decode_location_message(payload: bytes):
    """
    Attempts to decode an OpenDroneID Location Message (Type 1 or 2 depending on standard version, 
    but typically Message Type is packed into the high nibble of Byte 0).
    """
    try:
        if len(payload) < 13:
            return "Payload too short for Location Message"

        # Byte 0: Header (High nibble = Message Type, Low nibble = Protocol Version)
        header = payload[0]
        msg_type = (header & 0xF0) >> 4
        
        # Byte 1: Status, Height Type, etc.
        # Byte 2: Direction
        # Byte 3: Speed Horizontal
        # Byte 4: Speed Vertical
        # Bytes 5-8: Latitude (int32_t, degrees * 1e7)
        # Bytes 9-12: Longitude (int32_t, degrees * 1e7)
        # Bytes 13-14: Altitude Baro (uint16_t)
        # Bytes 15-16: Altitude Geo (uint16_t)
        
        # Unpack Lat/Lon (Little Endian or Big Endian? ASD-STAN/ASTM uses Little Endian usually)
        lat_raw = struct.unpack_from('<i', payload, 5)[0]
        lon_raw = struct.unpack_from('<i', payload, 9)[0]
        
        lat = lat_raw / 10000000.0
        lon = lon_raw / 10000000.0
        
        return f"Lat: {lat:.6f}, Lon: {lon:.6f}"
    except Exception as e:
        return f"Decode error: {e}"

def detection_callback(device, advertisement_data):
    # Check if the device is advertising the Remote ID Service Data
    if REMOTE_ID_UUID_16 in advertisement_data.service_data:
        payload = advertisement_data.service_data[REMOTE_ID_UUID_16]
        
        print(f"\n--- Remote ID Detected! ---")
        print(f"Device MAC/UUID: {device.address}")
        print(f"Device Name: {device.name or advertisement_data.local_name or 'Unknown'}")
        print(f"RSSI: {advertisement_data.rssi} dBm")
        print(f"Raw Payload ({len(payload)} bytes): {payload.hex()}")
        
        if len(payload) > 0:
            header = payload[0]
            msg_type = (header & 0xF0) >> 4
            version = header & 0x0F
            print(f"Parsed Header -> Type: {msg_type}, Version: {version}")
            
            # Message Type 1 or 2 usually holds the Location (Vector) data depending on the implementation
            if msg_type in [1, 2]: 
                loc_info = decode_location_message(payload)
                print(f"Decoded Location: {loc_info}")

async def main():
    print("Initializing Bluetooth Scanner for DJI Remote ID (UUID: 0xFFFA)...")
    print("Make sure your Mac's Bluetooth is ON, and your DJI Mini 3 is powered on with GPS lock.")
    print("Press Ctrl+C to stop.\n")
    
    scanner = BleakScanner(detection_callback)
    await scanner.start()
    
    try:
        # Run scanner indefinitely
        while True:
            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        pass
    finally:
        await scanner.stop()
        print("\nScanner stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting.")
