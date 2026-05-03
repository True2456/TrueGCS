import time
import os

def send_command(text):
    print(f"📡 Sending Tactical Command: '{text}'")
    with open("remote_pilot.cmd", "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    # Give the UI time to react
    time.sleep(20)

if __name__ == "__main__":
    print("🎬 Starting LIVE Tactical Demo...")
    time.sleep(5) # Wait for GCS to settle
    
    send_command("Launch to 50 metres")
    send_command("Deploy a waypoint mission")
    send_command("Bring the bird home")
    
    print("✅ Demo Sequence Complete.")
