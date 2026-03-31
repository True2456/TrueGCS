import subprocess, time, cv2
def test():
    gst_path = "C:\\ProgramData\\Mission Planner\\gstreamer\\1.0\\x86_64\\bin\\gst-launch-1.0.exe"
    port = 5008
    dp = 12345
    # The EXACT GCS String
    cmd = f'"{gst_path}" -q udpsrc port={port} address=127.0.0.1 ! queue ! h264parse ! mpegtsmux ! udpsink host=127.0.0.1 port={dp} sync=false'
    print(f"Launching GST: {cmd}")
    p = subprocess.Popen(cmd, shell=False)
    time.sleep(2) # Give it 2 seconds
    
    import os
    os.environ['OPENCV_FFMPEG_READ_TIMEOUT'] = '2000'
    opts = f"udp://127.0.0.1:{dp}?overrun_nonfatal=1&fifo_size=5000000"
    
    print("Testing connection...")
    cap = cv2.VideoCapture(opts, cv2.CAP_FFMPEG)
    print(f"Cap isOpened: {cap.isOpened()}")
    if cap.isOpened():
        ret, frame = cap.read()
        print(f"Read success: {ret}, frame size: {frame.size if ret else 'None'}")
    cap.release()
    p.kill()

if __name__ == "__main__":
    test()
