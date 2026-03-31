import cv2
import time
opts = "udp://127.0.0.1:5011?overrun_nonfatal=1&fifo_size=5000000"
for i in range(5):
    print(f"Try {i}")
    cap = cv2.VideoCapture(opts, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("Failed!")
    time.sleep(1)
