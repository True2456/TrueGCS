from ultralytics import YOLO
import sys

def main():
    # Load the high-performance YOLO26 base architecture
    print("Mission Control: Initializing Transfer Learning on YOLO26 Architecture...")
    model = YOLO("yolo26n.pt") 

    # Start training on the official VisDrone dataset configuration
    # This will trigger the automated 2.3GB dataset fetch from Tianjin University
    # We use a batch size of 16 and image size of 640 for the RTX 3060 🏎️
    try:
        print("Mission Control: Starting official VisDrone data fetch (approx 2.3GB)...")
        results = model.train(
            data="VisDrone.yaml", 
            epochs=100, 
            imgsz=640, 
            batch=16, 
            device=0, # Use RTX 3060 CUDA
            workers=4,
            project="VisDrone_Mission",
            name="TacObs_v1"
        )
    except Exception as e:
        print(f"Mission Failure during training link: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
