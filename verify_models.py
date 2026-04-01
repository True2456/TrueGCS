import os
import torch
import numpy as np
from ultralytics import YOLO, RTDETR

def test_load_and_infer(model_path, model_type="YOLO"):
    print(f"\n--- Testing {model_path} ({model_type}) ---")
    if not os.path.exists(model_path):
        print(f"Error: {model_path} not found!")
        return False
    
    devices = ['cpu']
    if torch.cuda.is_available():
        devices.append('cuda:0')
    
    dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)
    
    for device in devices:
        try:
            print(f"Loading on {device}...")
            if "RTDETR" in model_type:
                model = RTDETR(model_path)
            else:
                model = YOLO(model_path)
            
            model.to(device)
            print(f"Success loading {model_path} on {device}")
            
            # Real Inference Check 🏎️
            print(f"Running dummy inference on {device}...")
            results = model(dummy_frame, verbose=False)
            
            if results and len(results) > 0:
                print(f"Inference SUCCESS: Result object received.")
                # Check for boxes attribute (standard for YOLO/RTDETR)
                if hasattr(results[0], 'boxes'):
                    print(f"Structure Check: 'boxes' attribute found. Ready for mission.")
                else:
                    print(f"Structure Warning: 'boxes' attribute missing in results.")
            else:
                print(f"Inference Error: No results returned.")
                return False
                
        except Exception as e:
            print(f"CRITICAL ERROR on {device}: {e}")
            return False
    return True

if __name__ == "__main__":
    yolo_path = "Yolo26n Visdrone/yolo26_visdrone_best.pt"
    rtdetr_path = "rtdetr-l.pt"
    
    s1 = test_load_and_infer(yolo_path, "YOLO")
    s2 = test_load_and_infer(rtdetr_path, "RTDETR")
    
    if s1 and s2:
        print("\n[PASSED] All models verified with live inference check.")
    else:
        print("\n[FAILED] Model verification failed. Check hardware/file integrity.")
