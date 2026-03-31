import subprocess
import time

gst_path = "C:\\ProgramData\\Mission Planner\\gstreamer\\1.0\\x86_64\\bin\\gst-launch-1.0.exe"
cmd = f'"{gst_path}" -q udpsrc port=5008 address=127.0.0.1 ! queue ! h264parse ! mpegtsmux ! udpsink host=127.0.0.1 port=5011 sync=false'
print(f"Launching: {cmd}")
p = subprocess.Popen(cmd, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(2)
poll = p.poll()
if poll is not None:
    print(f"CRASHED! Code {poll}")
    print(p.stderr.read().decode())
else:
    print("RUNNING FINE!")
    p.kill()
