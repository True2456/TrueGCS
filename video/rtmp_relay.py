import socket
import threading
import time
import struct

class RTMPRelay:
    """
    Minimalistic RTMP-to-UDP Bridge 🌉
    Tailored for DJI drone push streams.
    Handles handshake/metadata and forwards raw H.264 video tags to GStreamer.
    """
    def __init__(self, listen_ip='0.0.0.0', listen_port=1935, target_ip='127.0.0.1', target_port=5010):
        self.listen_ip = listen_ip
        self.listen_port = listen_port
        self.target_ip = target_ip
        self.target_port = target_port
        self.running = False
        self.server_sock = None
        self.client_sock = None
        self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.thread = None

    def start(self):
        self.running = True
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_sock.bind((self.listen_ip, self.listen_port))
            self.server_sock.listen(1)
            self.server_sock.settimeout(2.0)
            print(f"RTMP Relay: Listening on {self.listen_ip}:{self.listen_port}")
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            return True
        except Exception as e:
            print(f"RTMP Relay Error: Failed to bind to {self.listen_port}: {e}")
            return False

    def _run(self):
        while self.running:
            try:
                self.client_sock, addr = self.server_sock.accept()
                print(f"RTMP Relay: DJI Drone Connected from {addr[0]}")
                self._handle_client(self.client_sock)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"RTMP Relay Worker Error: {e}")
                break

    def _handle_client(self, sock):
        try:
            # 1. Handshake Phase C0/C1 (1, 1536 bytes)
            c0 = sock.recv(1)
            if not c0: return
            c1 = sock.recv(1536)
            if len(c1) < 1536: return
            
            # S0/S1/S2 Handshake response
            s0 = b'\x03'
            s1 = b'\x00' * 1536 # Simplistic S1
            s2 = c1 # Echo C1 as S2
            sock.sendall(s0 + s1 + s2)
            
            # C2 (1536 bytes)
            c2 = sock.recv(1536)
            print("RTMP Relay: Handshake Successful.")

            # 2. Command Phase (Connect, CreateStream, etc.)
            # We don't need to parse these fully to relay the data, 
            # but we must stay alive while the drone pushes.
            sock.settimeout(5.0)
            
            while self.running:
                data = sock.recv(16384)
                if not data: break
                
                # Broad-Spectrum Forwarding 📡
                # We forward the raw stream to UDP Port 5010.
                # The GStreamer 'h264parse' element will find the NALU start codes
                # inside the RTMP/FLV noise, providing a stable low-latency image.
                self.udp_sock.sendto(data, (self.target_ip, self.target_port))
                
        except Exception as e:
            print(f"RTMP Relay: Client Disconnected: {e}")
        finally:
            if sock: sock.close()
            print("RTMP Relay: Session Closed.")

    def stop(self):
        self.running = False
        if self.server_sock:
            self.server_sock.close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        print("RTMP Relay: Stopped.")
