import cv2
import numpy as np
import math
import time
from PySide6.QtCore import QThread, Signal, Qt, QObject, QTimer
from PySide6.QtGui import QImage
from ultralytics import YOLO, RTDETR, YOLOWorld
import threading

class CaptureDaemon:
    def __init__(self, cap):
        self.cap = cap
        self.running = True
        self.frame = None
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        
    def _update(self):
        while self.running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.frame = frame
                    
    def read(self):
        with self.lock:
            return self.frame is not None, self.frame
            
    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)

class InferenceDaemon:
    def __init__(self, model_getter, model_lock):
        self.model_getter = model_getter
        self.lock = threading.Lock()
        self.model_lock = model_lock # Master AI Recursive Sync Lock 🔐
        self.running = True
        self.paused = False # Tactical Mission State ⛓️
        self.idle_event = threading.Event()
        self.idle_event.set() # Initially idle
        self.latest_frame = None
        self.results = None
        self.pending_prompt = None
        self.active_class_ids = None # Mission Class Filter ⛓️
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        
    def _update(self):
        while self.running:
            if self.paused:
                self.idle_event.set() # Confirm we are strictly idle ⛓️
                time.sleep(0.01) # Hold for Mission Reset
                continue
            
            self.idle_event.clear() # Engaging calculations 🏎️
                
            frame = None
            with self.lock:
                frame = self.latest_frame
                self.latest_frame = None # Consume it
            
            if frame is not None:
                # Acquire Atomic Model Access 🔐
                with self.model_lock:
                    model, engine = self.model_getter()
                    if model:
                        try:
                            use_fp16 = (engine == "CUDA")
                            # Handle dynamic Zero-Shot class updates (within the model lock)
                            with self.lock:
                                if self.pending_prompt and hasattr(model, "set_classes"):
                                    try:
                                        classes = [c.strip() for c in self.pending_prompt.split(",")]
                                        model.set_classes(classes)
                                        self.pending_prompt = None
                                        print(f"InferenceDaemon: YOLO-World classes updated to {classes}")
                                    except Exception as e:
                                        print(f"InferenceDaemon: Failed to set World classes: {e}")
                                        
                            # Perform detection with tactical class filtering 🏎️
                            with self.lock:
                                cls_list = self.active_class_ids
                            
                            # TACTICAL BLACKOUT: Skip inference if specifically empty [] 🧱🚀
                            if cls_list is not None and len(cls_list) == 0:
                                res = None
                            else:
                                res = model(frame, verbose=False, half=use_fp16, conf=0.25, imgsz=640, classes=cls_list)
                            
                            with self.lock:
                                self.results = res
                                num_targets = len(res[0].boxes) if res else 0
                                if num_targets > 0:
                                    print(f"InferenceDaemon: Detected {num_targets} targets.")
                        except Exception as e:
                            print(f"InferenceDaemon CRITICAL: {e}")
                            import traceback
                            traceback.print_exc()
                        finally:
                            self.idle_event.set() # Reset to idle after frame is pushed
                    else:
                        self.idle_event.set()
                        time.sleep(0.005) # Prevent CPU spinning if no model
            else:
                self.idle_event.set()
                time.sleep(0.005) # Prevent CPU spinning if no frame
                
    def update_prompt(self, prompt):
        with self.lock:
            self.pending_prompt = prompt

    def update_class_filter(self, ids):
        with self.lock:
            # We preserve the list even if empty 🚀
            # ids=None means "Show All" (Legacy)
            # ids=[] means "Tactical Blackout" (New)
            self.active_class_ids = ids
            print(f"InferenceDaemon: Tactical filter updated -> {self.active_class_ids}")

    def update_frame(self, frame):
        with self.lock:
            self.latest_frame = frame
            
    def pause(self):
        """Strategic Mission Pause with Safety Handshake ⛓️"""
        with self.lock:
            self.paused = True
            self.results = None # Clear ghost brackets
        
        # Wait for the AI to finish its current frame (max 2 seconds)
        print("Mission Control: Waiting for Inference Engine to enter IDLE state...")
        if not self.idle_event.wait(timeout=2.0):
            print("Mission Control: CRITICAL! Inference Engine Handshake Timeout.")
            
    def resume(self):
        with self.lock:
            self.paused = False
            self.idle_event.clear()

    def get_results(self):
        with self.lock:
            return self.results

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)

class VideoThread(QThread):
    # Signals a QImage to be displayed in the UI
    frame_ready = Signal(QImage)
    # Signals the PID error (X, Y) to calculate gimbal adjustments
    tracking_error = Signal(int, int) 
    # Signals status info (status_text, offset_x, offset_y, confidence)
    target_status = Signal(str, int, int, float)
    source_frame_size = Signal(int, int)
    ai_ready = Signal(str, str) # Emitted when model is fully loaded and optimized 🚀
    
    def __init__(self, stream_url="udp://@:5010", parent=None):
        super().__init__(parent)
        self.stream_url = str(stream_url)
        self.running = True
        
        self._current_engine = "CPU"
        self._is_loading = False # Safety Guard for Overlapping Loads 🛡️
        self._cancel_load = False
        self._current_model_type = "YOLO"
        self._world_prompt = "person, car, drone"
        self.model = None
        default_engine = "CPU"
        try:
            import torch
            if torch.cuda.is_available():
                default_engine = "CUDA"
        except Exception:
            default_engine = "CPU"

        # Queue initial load 🚀 (model_type, engine)
        self.pending_model_swap = ("YOLO", default_engine)
        self.hud_status = "INITIALIZING..."
        self.loading_thread = None
        self.model_lock = threading.RLock() # Recursive Lock to prevent deadlocks 🔐
        self.show_detections = False # Mission Toggle 📡
        self.tracking_point = None
        self.lock_on_box = None
        self.lock_on_conf = 0.0
        self.tracking_mode = "none"
        self._boxes_lock = threading.Lock()
        self._latest_boxes = []
        self._latest_confs = []
        # Click marker overlay (user feedback only)
        self._click_marker = None  # (x, y) in source frame coords
        self._click_marker_until = 0.0
        self._last_detection_print_sig = None
        self.active_class_ids = None # Pilot's Preference ⛓️
        self.inference_daemon = None
        self.capture_daemon = None
        self.gst_process = None

    def set_click_marker(self, x: int | None, y: int | None, ttl_s: float = 1.5) -> None:
        """Show a temporary cross at (x,y) in the *source frame* coordinates."""
        if x is None or y is None:
            self._click_marker = None
            self._click_marker_until = 0.0
            return
        self._click_marker = (int(x), int(y))
        self._click_marker_until = time.time() + float(ttl_s)
        
    def set_show_detections(self, state):
        """Public signal receiver to toggle AI HUD visibility."""
        self.show_detections = bool(state)
        print(f"VideoThread: set_show_detections={self.show_detections}")

    def set_ai_config(self, engine, model_type):
        """Atomic mission configuration 🔐"""
        # Guard against overlapping requests – cancel current load and queue new config
        if getattr(self, "_is_loading", False):
            print("VideoThread: Cancelling current load for new AI config request.")
            self._cancel_load = True
            self._pending_ai_config = (engine, model_type)
            return
        # If model_type is None, unload model and disable detections
        if model_type == "None":
            # Signal cancellation of any ongoing load
            self._cancel_load = True
            if getattr(self, "_is_loading", False):
                print("VideoThread: Cancelling ongoing model load for unload request.")
                # Let load_model_async notice the cancel flag and exit gracefully
            print("VideoThread: Unloading detection model as requested.")
            self.model = None
            self.set_show_detections(False)
            self._current_engine = engine
            self._current_model_type = model_type
            self.pending_model_swap = (model_type, engine)
            self._cancel_load = False
            return
        # Preserve current detection visibility state
        prev_show = self.show_detections
        if prev_show:
            self.set_show_detections(False)
        
        # Ensure previous load is finished or cancelled before starting a new one
        if self.loading_thread and self.loading_thread.is_alive():
            print("VideoThread: Cancelling previous AI load to prioritize new request...")
            self._cancel_load = True
            # We don't join here because it would block the UI thread
            # instead 'load_model_async' will check the flag and exit
        
        self._is_loading = True
        self._cancel_load = False
        self._current_engine = engine
        self._current_model_type = model_type
        self.pending_model_swap = (model_type, engine)
        print(f"VideoThread: Applying AI config -> {model_type} on {engine}")
        
        self.loading_thread = threading.Thread(
            target=self.load_model_async,
            args=(model_type, engine),
            daemon=True
        )
        self.loading_thread.start()
        
        # Restore detection visibility after load completes
        if prev_show:
            self._restore_show = True
        
    def set_world_prompt(self, prompt):
        self._world_prompt = prompt
        if self.inference_daemon:
            self.inference_daemon.update_prompt(prompt)
            
    def get_ai_model(self):
        with self.model_lock:
            return self.model, self._current_engine

    def load_model_async(self, model_type, engine_name):
        """Internal method designed for the isolated LoadingThread 🚀"""
        engine_map = {
            "CPU": "cpu",
            "CUDA": "cuda:0",
            "DirectML": "dml", 
            "TensorRT": "cuda"
        }
        
        device_str = engine_map.get(engine_name, "cpu")
        self.hud_status = f"DOWNLOADING {model_type}..."
        print(f"Mission Loader: Fetching AI weights for {model_type} onto {device_str}...")
        
        try:
            # Check for cancellation before proceeding
            if getattr(self, "_cancel_load", False):
                print("VideoThread: Model load cancelled before start.")
                self._is_loading = False
                self._cancel_load = False
                # Resume daemon if it was paused
                if self.inference_daemon:
                    self.inference_daemon.resume()
                # Apply any pending AI config after cancellation
                if getattr(self, "_pending_ai_config", None):
                    eng, mdl = self._pending_ai_config
                    self._pending_ai_config = None
                    self.set_ai_config(eng, mdl)
                return
            # 1. Mission Isolation (Safety Pause) ⛓️
            if self.inference_daemon:
                self.inference_daemon.pause()
                
            # Check again after pause in case cancel arrived during pause
            if getattr(self, "_cancel_load", False):
                print("VideoThread: Model load cancelled after pause.")
                self._is_loading = False
                self._cancel_load = False
                if self.inference_daemon:
                    self.inference_daemon.resume()
                return
            
            try:
                # Mission Load Interrupt Guard 🛡️
                if getattr(self, "_cancel_load", False):
                    self._is_loading = False
                    return
                    
                # 2. Tactical Load into Buffer 🚀
                import os
                # Atomic hotswap weight mapping 🏎️
                mt = (model_type or "").upper()
                weights = "yolov8n.pt" # Default failsafe fallback
                is_rtdetr = False
                is_world = False
                
                if "RT-DETR" in mt:
                    weights = "rtdetr-l.pt"
                    is_rtdetr = True
                elif "YOLO26" in mt or "VISDRONE" in mt:
                    # Target the high-performance YOLO26 architecture for mission search
                    weights = "Yolo26n Visdrone/yolo26_visdrone_best.pt"
                else:
                    weights = "yolo26n.pt" # Standardize on YOLO26 for 2026 missions!

                # Mission Loader: Failsafe Weights Check
                if not os.path.exists(weights):
                    print(f"Mission Loader: WARNING! {weights} not found. Reverting to base YOLOv8n.")
                    weights = "yolov8n.pt"
                    is_rtdetr = False
                    is_world = False

                # Mission Load Interrupt Guard (Pre-Inference Context Creation)
                if getattr(self, "_cancel_load", False):
                    self._is_loading = False
                    return

                # 2. Tactical Load into Buffer 🚀 (With Corrupted File Protection 🛡️)
                try:
                    if is_rtdetr:
                        temp_model = RTDETR(weights)
                    elif is_world:
                        # Fallback for YOLO-World if specifically requested pt is missing
                        if not os.path.exists(weights):
                            print(f"Mission Loader: {weights} missing. Using zero-shot YOLO-World base.")
                            weights = "yolov8s-worldv2.pt" # Official Ultralytics name
                        temp_model = YOLOWorld(weights)
                        classes = [c.strip() for c in self._world_prompt.split(",")]
                        temp_model.set_classes(classes)
                    else:
                        temp_model = YOLO(weights)
                except Exception as e:
                    print(f"Mission Loader: FATAL! {weights} is corrupted. Deleting and falling back.")
                    try: os.remove(weights)
                    except: pass
                    weights = "yolov8n.pt"
                    temp_model = YOLO(weights)
                
                # 3. Hardware Guard (Environment Check)
                import sys
                if device_str == "cuda:0":
                    import torch
                    if not torch.cuda.is_available():
                        # Explain why CUDA failed (e.g. they have +cpu version installed)
                        torch_v = getattr(torch, "__version__", "unknown")
                        print(f"Mission Loader: CUDA requested but not found in Torch {torch_v}. Forcing CPU Failsafe.")
                        device_str = "cpu"
                
                # Optimization & Transfer
                if device_str != "cpu":
                    self.hud_status = f"OPTIMIZING {engine_name}..."
                    temp_model.to(device_str)
                    dummy = np.zeros((640,640,3), dtype=np.uint8)
                    import torch
                    if torch.cuda.is_available(): torch.cuda.empty_cache()
                    temp_model(dummy, verbose=False) 
    
                # 4. PERFORM ATOMIC SWAP 🔐
                # We perform the swap within a critical section to ensure the InferenceDaemon 
                # cannot use the model during the transfer.
                with self.model_lock:
                    print(f"Mission Loader: Commencing atomic handover for {model_type}...")
                    
                    try:
                        # Explicit Memory Release for Hardware Context Stability 🧹
                        # We clear the active model FIRST to free VRAM for RT-DETR (which is large)
                        self.model = None
                        print("Mission Loader Debug: Active model cleared.")
                        
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                            print("Mission Loader Debug: CUDA Cache purged.")
                            import gc
                            gc.collect()
                        
                        self.model = temp_model
                        print("Mission Loader Debug: New Weights assigned.")
                        
                        self._current_engine = device_str              
                        self.hud_status = "AI READY"
                        print(f"Mission Loader: AI Core swapped successfully onto {device_str}.")
                        self.ai_ready.emit(device_str, model_type)
                        print("Mission Loader Debug: AI Signal emitted.")
                    except Exception as e:
                        print(f"Mission Loader CRITICAL: Handover failure -> {e}")
                
                # Reset loading guard
                self._is_loading = False
                # Apply any pending AI config after this load finishes
                if getattr(self, "_pending_ai_config", None):
                    eng, mdl = self._pending_ai_config
                    self._pending_ai_config = None
                    print(f"VideoThread: Applying pending AI config -> {mdl} on {eng}")
                    self.set_ai_config(eng, mdl)
                # Restore detection visibility if requested
                if getattr(self, "_restore_show", False):
                    self.set_show_detections(True)
                    del self._restore_show
                # 5. Mission Resume (Guaranteed) 🛰️
                if self.inference_daemon:
                    self.inference_daemon.resume()
                    
            finally:
                # Reset loading guard
                self._is_loading = False
                # Restore detection visibility if requested
                if getattr(self, "_restore_show", False):
                    self.set_show_detections(True)
                    del self._restore_show
                # 5. Mission Resume (Guaranteed) 🛰️
                if self.inference_daemon:
                    self.inference_daemon.resume()
                    
        except Exception as e:
            print(f"Mission Loader: FATAL FAILURE during AI fetch: {e}")
            self.hud_status = "RECON FAULT"
            # Dynamic Recovery (Auto-Heal Corrupted Downloads)
            try:
                if "corrupted" in str(e).lower() or "zip archive" in str(e).lower():
                    import os
                    if "RT-DETR" in model_type: bad_path = "rtdetr-l.pt"
                    elif "World" in model_type: bad_path = "yolov8s-worldv2.pt"
                    else: bad_path = "yolo26n.pt"
                    
                    if os.path.exists(bad_path):
                        print(f"Mission Loader: Purging corrupted weights: {bad_path}")
                        os.remove(bad_path)
                
                with self.model_lock:
                    if self.model is None:
                        self.model = YOLO("yolov8n.pt")
            except:
                pass

        # Reset tracking point as the new model has a different 'View'
        self.tracking_point = None
        self.lock_on_box = None
        self.lock_on_conf = 0.0
        # PRESERVE show_detections (Pilot's Choice is Sticky!) 📡

    def set_show_detections(self, enabled):
        self.show_detections = enabled
        if not enabled:
            self.lock_on_box = None
            self.tracking_point = None
            self.target_status.emit("SEARCHING", 0, 0, 0.0)
        print(f"VideoThread: set_show_detections={enabled}")

    def set_tracking_point(self, x, y):
        if x is None or y is None:
            self.tracking_point = None
            self.lock_on_box = None
            self.target_status.emit("SEARCHING", 0, 0, 0.0)
            return
        
        self.tracking_point = (x, y)
        print(f"VideoThread: set_tracking_point=({x}, {y})")

    def set_tracking_mode(self, mode):
        mode_val = str(mode or "none").lower()
        if mode_val not in ("none", "nearest", "seed", "center"):
            mode_val = "none"
        self.tracking_mode = mode_val
        if self.tracking_mode == "none":
            self.set_tracking_point(None, None)

    def set_active_classes(self, ids):
        self.active_class_ids = ids
        if self.inference_daemon:
            self.inference_daemon.update_class_filter(ids)

    def handle_click(self, x, y):
        # Always show click feedback cross
        self.set_click_marker(x, y)
        mode = self.tracking_mode
        if mode == "none":
            return
        if mode in ("seed", "center"):
            self.set_tracking_point(x, y)
            return

        with self._boxes_lock:
            boxes = list(self._latest_boxes)
            confs = list(self._latest_confs)
        if not boxes:
            self.set_tracking_point(x, y)
            return

        min_dist = float("inf")
        best_idx = -1
        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = box
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            dist = np.sqrt((cx - x) ** 2 + (cy - y) ** 2)
            if dist < min_dist:
                min_dist = dist
                best_idx = i
        if best_idx >= 0:
            box = boxes[best_idx]
            self.lock_on_box = np.array(box)
            self.lock_on_conf = confs[best_idx] if best_idx < len(confs) else 0.0
            cx = int((box[0] + box[2]) / 2.0)
            cy = int((box[1] + box[3]) / 2.0)
            self.set_tracking_point(cx, cy)

    def run(self):
        # Native Subprocess Engine Architecture
        target_src = self.stream_url
        self.gst_process = None
        cap = None
        self._rtmp_relay = None
        
        # 1. RTMP Server Support (DJI Push Mode) 🚁
        is_rtmp = "rtmp://" in str(target_src).lower()
        if is_rtmp:
            from video.rtmp_relay import RTMPRelay
            # DJI RTMP is usually on 1935. We listen and forward to 5010 internal
            self._rtmp_relay = RTMPRelay(listen_port=1935, target_port=5010)
            if self._rtmp_relay.start():
                target_src = "udp://127.0.0.1:5010"
                print("VideoThread: RTMP Relay listening for drone on Port 1935.")
            else:
                self.hud_status = "RTMP PORT BUSY"
                return

        if "udp://" in str(target_src).lower() and hasattr(self, "gst_path"):
            import subprocess
            
            target_ip = target_src.split("://")[1].split(":")[0] if "://" in target_src else "127.0.0.1"
            try: target_port = target_src.split(":")[-1]
            except: target_port = "5008"
            if target_ip == "@": target_ip = "0.0.0.0"
            
            cmd = ""
            # Dynamically select a randomized internal loopback port to aggressively bypass orphaned WSAEADDRINUSE socket locks from crashed ghost sessions!
            import random
            self._dynamic_loopback_port = random.randint(15000, 25000)
            
            if is_rtmp:
                # SPECIALIZED RTMP PIPELINE: Requires parsebin for DJI stability 🎯
                cmd = f'"{self.gst_path}" -q udpsrc port={target_port} address={target_ip} buffer-size=10000000 ! parsebin ! mpegtsmux alignment=7 ! queue max-size-buffers=3 leaky=downstream ! udpsink host=127.0.0.1 port={self._dynamic_loopback_port} sync=false'
            elif getattr(self, "relay_mp", False):
                cmd = f'"{self.gst_path}" -q udpsrc port={target_port} address={target_ip} buffer-size=10000000 ! queue max-size-buffers=3 ! parsebin ! tee name=t ! queue max-size-buffers=3 ! rtph264pay ! queue max-size-buffers=3 ! udpsink host=127.0.0.1 port=5600 sync=false t. ! queue max-size-buffers=3 ! mpegtsmux alignment=7 ! queue max-size-buffers=3 ! udpsink host=127.0.0.1 port={self._dynamic_loopback_port} sync=false'
            else:
                cmd = f'"{self.gst_path}" -q udpsrc port={target_port} address={target_ip} buffer-size=10000000 ! queue max-size-buffers=3 ! parsebin ! mpegtsmux alignment=7 ! queue max-size-buffers=3 leaky=downstream ! udpsink host=127.0.0.1 port={self._dynamic_loopback_port} sync=false'
                
            print(f"Video Recon: Launching Localhost MPEG-TS Transcoder ->\n{cmd}")
            
            try:
                # Launch GStreamer directly via Windows API to prevent CMD quote-stripping corruption
                self.gst_process = subprocess.Popen(cmd, shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"Video Recon Subprocess Error: {e}")
            
            import os
            time.sleep(2.0) # Give GStreamer slightly more time to spool up
            # Restoring stable OpenCV ingestion overrides to prevent internal FFMPEG C++ segmentation faults!
            if "OPENCV_FFMPEG_CAPTURE_OPTIONS" in os.environ:
                del os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"]
            
            # Cap the internal stream timeout to completely prevent 30-second silent hangs!
            os.environ["OPENCV_FFMPEG_READ_TIMEOUT"] = "2000"
            
            # OpenCV native connection string targeting our dynamically generated secure port!
            # Annihilate the 5,000,000 byte latency cache using ultra-strict nobuffer FFmpeg arguments
            ffmpeg_options = f"udp://127.0.0.1:{self._dynamic_loopback_port}?fflags=nobuffer&flags=low_delay&strict=experimental"
            
            # Robust Dynamic Polling System: Explicitly calls .release() to prevent OpenCV C++ Struct Segfaults!
            retries = 0
            while self.running and retries < 15:
                temp_cap = cv2.VideoCapture(ffmpeg_options, cv2.CAP_FFMPEG)
                if temp_cap.isOpened():
                    self.cap = temp_cap
                    break
                temp_cap.release()
                print(f"Video Recon: Waiting for Video Payload on Port {self._dynamic_loopback_port}... ({retries+1}/15)")
                time.sleep(1.0)
                retries += 1
        else:
            try:
                self.cap = cv2.VideoCapture(int(target_src))
            except:
                self.cap = cv2.VideoCapture(target_src)
            
        if not hasattr(self, "cap") or not self.cap or not self.cap.isOpened():
            print(f"Video Recon: Critical Timeout! Failed to establish feed link {target_src}")
            return
        
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Low Latency
        
        # Sub-delegate the ingestion and inference to independent Daemons!
        self.capture_daemon = CaptureDaemon(self.cap)
        self.inference_daemon = InferenceDaemon(self.get_ai_model, self.model_lock)
        
        while self.running:
            try:
                # 0. Acquire Frame Vector asynchronously (Zero Latency Delay)
                ret, frame = self.capture_daemon.read()
                if not ret:
                    time.sleep(0.005)
                    continue
                
                # 1. Spawn Truly Asynchronous Mission Loader (Prevents Stutters! 🏎️)
                if self.pending_model_swap:
                    if self.loading_thread is None or not self.loading_thread.is_alive():
                        mod, eng = self.pending_model_swap
                        self.loading_thread = threading.Thread(
                            target=self.load_model_async, 
                            args=(mod, eng),
                            daemon=True
                        )
                        self.loading_thread.start()
                        self.pending_model_swap = None

                # 2. Update Inference Daemon with the latest frame for background processing
                if self.show_detections:
                    self.inference_daemon.update_frame(frame)
                
                # Base frame for display
                annotated_frame = frame.copy()
                h, w = annotated_frame.shape[:2]
                self.source_frame_size.emit(w, h)
                
                # 2. Grab latest results from the background InferenceDaemon (Non-Blocking!)
                results = self.inference_daemon.get_results() if self.show_detections else None
                boxes = results[0].boxes.xyxy.cpu().numpy() if (results and len(results) > 0) else []
                confs = results[0].boxes.conf.cpu().numpy() if (results and len(results) > 0) else []

                if self.show_detections and self.model is not None:
                    sig = f"{self._current_model_type}|{self._current_engine}"
                    if sig != self._last_detection_print_sig:
                        print(f"VideoThread: Detections active (model={sig})")
                        self._last_detection_print_sig = sig
                with self._boxes_lock:
                    self._latest_boxes = boxes.tolist() if len(boxes) > 0 else []
                    self._latest_confs = confs.tolist() if len(confs) > 0 else []
                    
                # 3. Identify Locked Target
                is_locked = False
                if self.tracking_point and len(boxes) > 0:
                    px, py = self.tracking_point
                    min_dist = float('inf')
                    found_idx = -1
                    
                    for i, box in enumerate(boxes):
                        x1, y1, x2, y2 = box
                        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                        dist = np.sqrt((cx - px)**2 + (cy - py)**2)
                        if dist < min_dist:
                            min_dist = dist
                            found_idx = i
                    
                    if found_idx != -1 and min_dist < 100:
                        self.lock_on_box = boxes[found_idx]
                        self.lock_on_conf = confs[found_idx]
                        is_locked = True
                        # Sticky point update
                        self.tracking_point = ((self.lock_on_box[0] + self.lock_on_box[2])/2, 
                                             (self.lock_on_box[1] + self.lock_on_box[3])/2)
                    else:
                        self.lock_on_box = None
                
                # 4. Draw & Annotate
                if time.time() < self._click_marker_until and self._click_marker is not None:
                    mx, my = self._click_marker
                    # Crosshair (cyan)
                    c = (0, 221, 255)
                    s = 12
                    cv2.line(annotated_frame, (mx - s, my), (mx + s, my), c, 2)
                    cv2.line(annotated_frame, (mx, my - s), (mx, my + s), c, 2)

                for i, box in enumerate(boxes):
                    x1, y1, x2, y2 = map(int, box)
                    current_locked = (self.lock_on_box is not None and np.array_equal(box, self.lock_on_box))
                    
                    if current_locked:
                        # Tactical Red Brackets
                        l = 15
                        cv2.line(annotated_frame, (x1, y1), (x1+l, y1), (0, 0, 255), 3)
                        cv2.line(annotated_frame, (x1, y1), (x1, y1+l), (0, 0, 255), 3)
                        cv2.line(annotated_frame, (x2, y1), (x2-l, y1), (0, 0, 255), 3)
                        cv2.line(annotated_frame, (x2, y1), (x2, y1+l), (0, 0, 255), 3)
                        cv2.line(annotated_frame, (x1, y2), (x1+l, y2), (0, 0, 255), 3)
                        cv2.line(annotated_frame, (x1, y2), (x1, y2-l), (0, 0, 255), 3)
                        cv2.line(annotated_frame, (x2, y2), (x2-l, y2), (0, 0, 255), 3)
                        cv2.line(annotated_frame, (x2, y2), (x2, y2-l), (0, 0, 255), 3)
                        
                        cv2.putText(annotated_frame, f"LOCK - {int(self.lock_on_conf*100)}%", (x1, y1-10), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 2)
                        
                        # PID Offset Calculation
                        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                        err_x = cx - (w // 2)
                        err_y = cy - (h // 2)
                        self.tracking_error.emit(err_x, err_y)
                        self.target_status.emit("LOCKED", err_x, err_y, self.lock_on_conf)
                    else:
                        # Emerald Green
                        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 1)
                
                # Global HUD Status Overlay (Tactical Telemetry)
                if self.hud_status:
                    num_targets = len(boxes)
                    status_text = f"RECON: {self.hud_status} | TARGETS: {num_targets}"
                    cv2.putText(annotated_frame, status_text, (20, 40), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 221, 255), 2)

                if self.lock_on_box is None and self.show_detections:
                    if self.tracking_point:
                        self.target_status.emit("LOST", 0, 0, 0.0)
                    else:
                        self.target_status.emit("SEARCHING", 0, 0, 0.0)

                # 4. Conversion & Emission (Always execute)
                rgb_image = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
                self.frame_ready.emit(qt_img)

            except Exception as e:
                print(f"VideoThread runtime error: {e}")
                time.sleep(0.01)

        if self.inference_daemon: self.inference_daemon.stop()
        if self.capture_daemon: self.capture_daemon.stop()
        if self._rtmp_relay: self._rtmp_relay.stop()
        if cap: cap.release()

    def stop(self):
        """Clean Teardown with Deep Resource Purge 🧹
        Ensures 100% of GPU memory and GStreamer handles are released instantly to prevent conflicts.
        """
        self.running = False
        
        # 1. Shutdown Inference Engine (Purge CUDA Context)
        if self.inference_daemon:
            print("VideoThread: Stopping Inference Daemon...")
            self.inference_daemon.stop()
        
        # 2. Release OpenCV/GStreamer Resources
        if self.capture_daemon:
            self.capture_daemon.stop()
        if getattr(self, "cap", None): 
            self.cap.release()
            
        # 3. Kill GStreamer Process (PID-Specific cleanup 🎯)
        if hasattr(self, "gst_process") and self.gst_process:
            pid = self.gst_process.pid
            try: self.gst_process.terminate()
            except: pass
            import os
            # Only kill This Specific PID to avoid hitting newly started parallel streams!
            os.system(f"taskkill /F /T /PID {pid} >nul 2>&1")

        # 4. Stop RTMP Relay if active
        if getattr(self, "_rtmp_relay", None):
            self._rtmp_relay.stop()

        # 5. DEEP PURGE: Release AI Model & GPU Memory Immediately 🔐
        with self.model_lock:
            print("VideoThread: Purging AI weights and CUDA Cache...")
            self.model = None
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            import gc
            gc.collect()

        # 5. Clean teardown wait for OS/CUDA context 🧱
        self.wait(500)
        print("VideoThread: Stream Cleanly Terminated.")
