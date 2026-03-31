import subprocess
import time

gst_path = "C:\\ProgramData\\Mission Planner\\gstreamer\\1.0\\x86_64\\bin\\gst-launch-1.0.exe"
# Generates a dummy RAW H264 UDP stream
cmd = f'"{gst_path}" videotestsrc is-live=true ! video/x-raw,width=1280,height=720,framerate=30/1 ! x264enc tune=zerolatency ! h264parse ! udpsink host=127.0.0.1 port=5008'
p = subprocess.Popen(cmd, shell=False)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    p.terminate()
