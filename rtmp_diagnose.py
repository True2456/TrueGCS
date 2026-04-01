import socket
import threading
import time
import struct
import subprocess
import os
import sys

# STANDALONE RTMP DIAGNOSTIC TEST (V4)
# Fixed Subprocess Execution for Windows.
# No Emojis.

def find_gst():
    mp_path = r"C:\ProgramData\Mission Planner\gstreamer\1.0\x86_64\bin\gst-launch-1.0.exe"
    paths = [mp_path, r"C:\gstreamer\1.0\msvc_x86_64\bin\gst-launch-1.0.exe", r"C:\gstreamer\1.0\x86_64\bin\gst-launch-1.0.exe"]
    for p in paths:
        if os.path.exists(p): return p
    return "gst-launch-1.0"

class RTMPDiagnosticRelay:
    def __init__(self, listen_ip='0.0.0.0', listen_port=15560, target_ip='127.0.0.1', target_port=5010):
        self.listen_ip, self.listen_port = listen_ip, listen_port
        self.target_ip, self.target_port = target_ip, target_port
        self.running = False
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.chunk_size = 1400
        self.on_ready_callback = None
        self.notified = False

    def start(self):
        self.running = True
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_sock.bind((self.listen_ip, self.listen_port))
            self.server_sock.listen(5)
            print(f"[TEST] Diagnostic Server: Listening on port {self.listen_port}")
            threading.Thread(target=self._run, daemon=True).start()
            return True
        except Exception as e: print(f"[TEST] Error Binding: {e}"); return False

    def _run(self):
        while self.running:
            try:
                client, addr = self.server_sock.accept()
                print(f"[TEST] Connection received from {addr}")
                self.notified = False 
                self._handle(client)
            except: break

    def _amf_string(self, s): return struct.pack('>H', len(s)) + s.encode('ascii')
    def _amf_number(self, n): return b'\x00' + struct.pack('>d', float(n))

    def _send_rtmp_packet(self, sock, chunk_stream_id, message_type, body, stream_id=0):
        header = struct.pack('B', (0 << 6) | chunk_stream_id)
        header += b'\x00\x00\x00' + struct.pack('>I', len(body))[1:]
        header += struct.pack('B', message_type) + struct.pack('<I', stream_id)
        sock.sendall(header + body)

    def _handle(self, sock):
        try:
            c0 = sock.recv(1)
            c1 = sock.recv(1536)
            sock.sendall(b'\x03' + b'\x00' * 1536 + c1)
            c2 = sock.recv(1536)
            print("[TEST] RTMP Handshake Successful.")
            
            ready_to_forward = False
            packet_count = 0
            
            while True:
                data = sock.recv(65536)
                if not data: break
                
                packet_count += 1
                if not ready_to_forward:
                    # Open gate on media bit detection OR after 15 command packets
                    if (len(data) > 8 and (data[0] >> 6) <= 1 and data[7] in (8, 9, 18)) or packet_count > 15:
                        ready_to_forward = True
                        print(f"[TEST] Incoming Stream Data. Notifying GStreamer trigger...")
                        if self.on_ready_callback and not self.notified:
                            self.notified = True
                            threading.Thread(target=self.on_ready_callback, daemon=True).start()

                if ready_to_forward:
                    for i in range(0, len(data), self.chunk_size):
                        self.udp_sock.sendto(data[i:i+self.chunk_size], (self.target_ip, self.target_port))

                if b'connect' in data:
                    res = b'\x02' + self._amf_string('_result') + self._amf_number(1) + b'\x05\x03'
                    res += self._amf_string('level') + b'\x02' + self._amf_string('status')
                    res += self._amf_string('code') + b'\x02' + self._amf_string('NetConnection.Connect.Success')
                    res += b'\x00\x00\x09'
                    self._send_rtmp_packet(sock, 3, 20, res)

                if b'publish' in data:
                    res = b'\x02' + self._amf_string('onStatus') + self._amf_number(0) + b'\x05\x03'
                    res += self._amf_string('level') + b'\x02' + self._amf_string('status')
                    res += self._amf_string('code') + b'\x02' + self._amf_string('NetStream.Publish.Start')
                    res += b'\x00\x00\x09'
                    self._send_rtmp_packet(sock, 3, 20, res)
                    
        except Exception as e: print(f"[TEST] Connection Ended: {e}")

if __name__ == "__main__":
    gst_exe = find_gst()
    if "Mission Planner" in gst_exe:
        base_gst = os.path.dirname(os.path.dirname(gst_exe))
        dll_dir = os.path.join(base_gst, "bin")
        os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
        os.environ["GST_PLUGIN_PATH"] = os.path.join(base_gst, "lib", "gstreamer-1.0")
        if sys.version_info >= (3, 8):
            try: os.add_dll_directory(dll_dir)
            except: pass

    relay = RTMPDiagnosticRelay()
    
    def launch_gst():
        # Diagnostic GStreamer Pipeline: Shows a local window immediately.
        # This bypasses all Python UI and OpenCV.
        # Uses shell=True on Windows for reliable path resolution with quoting.
        pipeline = f'udpsrc port=5010 address=127.0.0.1 buffer-size=4000000 ! flvdemux ! parsebin ! decodebin ! autovideosink sync=false'
        print(f"[TEST] Launching GStreamer: {pipeline}")
        subprocess.Popen(f'"{gst_exe}" -v {pipeline}', shell=True)

    relay.on_ready_callback = launch_gst
    
    if relay.start():
        print("\n[DIAGNOSTIC ACTIVE V4]")
        print(f"1. Target IP: 192.168.1.165")
        print(f"2. GStreamer will launch automatically AFTER handshake.")
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            print("[TEST] Diagnostic Stopped.")
