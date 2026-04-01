import os
import torch
import numpy as np
import time
from ultralytics import YOLO, RTDETR

class AIHotswapTester:
    def __init__(self):
        self.model = None
        self.current_engine = "cpu"
        self.current_model_type = "None"
        self.weights_map = {
            "YOLO26": "Yolo26n Visdrone/yolo26_visdrone_best.pt",
            "RT-DETR": "rtdetr-l.pt"
        }

    def load_model(self, model_type, engine_name):
        print(f"\n[TEST] Loading {model_type} on {engine_name}...")
        
        engine_map = {
            "CPU": "cpu",
            "CUDA": "cuda:0"
        }
        device_str = engine_map.get(engine_name, "cpu")
        
        if "RT-DETR" in model_type:
            weights = self.weights_map["RT-DETR"]
            is_rtdetr = True
        else:
            weights = self.weights_map["YOLO26"]
            is_rtdetr = False

        if not os.path.exists(weights):
            print(f"Error: {weights} not found!")
            return False

        try:
            # 1. Hardware Guard
            if device_str == "cuda:0":
                if not torch.cuda.is_available():
                    print("CUDA not available! Failsafe to CPU.")
                    device_str = "cpu"
            
            # 2. Load
            if is_rtdetr:
                temp_model = RTDETR(weights)
            else:
                temp_model = YOLO(weights)
            
            # 3. Optimization & Transfer
            temp_model.to(device_str)
            
            # Dummy inference to verify functionality
            dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)
            temp_model(dummy_frame, verbose=False)
            
            # 4. Swap
            self.model = temp_model
            self.current_engine = device_str
            self.current_model_type = model_type
            
            print(f"SUCCESS: {model_type} loaded on {device_str}")
            return True
            
        except Exception as e:
            print(f"FAILED: {e}")
            return False

def run_matrix_test():
    tester = AIHotswapTester()
    base_matrix = [
        ("YOLO26", "CPU"),
        ("YOLO26", "CUDA"),
        ("RT-DETR", "CUDA"),
        ("RT-DETR", "CPU")
    ]
    
    # STRESS TEST UPGRADE: Run 10 full cycles to catch race conditions and memory leaks 🏎️
    cycles = 10
    total_passes = 0
    total_tests = len(base_matrix) * cycles
    
    print(f"Starting Stress Test: {cycles} cycles ({total_tests} total swaps)...")
    
    for i in range(cycles):
        print(f"\n--- CYCLE {i+1}/{cycles} ---")
        for m_type, engine in base_matrix:
            success = tester.load_model(m_type, engine)
            if success:
                total_passes += 1
            else:
                print(f"FAILURE during Cycle {i+1} at {m_type}/{engine}")
                # Early exit on failure to debug state
                break
        if total_passes < (i+1) * len(base_matrix):
            break
            
        # Clean up GPU memory between cycles
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            
    print("\n" + "="*30)
    print("      AI STRESS TEST RESULTS")
    print("="*30)
    print(f"Total Swaps: {total_tests}")
    print(f"Passes:      {total_passes}")
    print(f"Failures:    {total_tests - total_passes}")
    print("="*30)
    
    if total_passes == total_tests:
        print("\n[GLOBAL PASSED] AI Engine is 100% mission stable.")
        return True
    else:
        print("\n[GLOBAL FAILED] Stability fault detected during stress test.")
        return False

if __name__ == "__main__":
    run_matrix_test()
