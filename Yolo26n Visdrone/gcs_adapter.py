from ultralytics import YOLO
import cv2
import torch

class YOLO26GCSAdapter:
    """
    A simple adapter class to integrate the trained YOLO26 model into a GCS.
    Optimized for Nvidia GPUs (like RTX 3060).
    """
    def __init__(self, model_path='yolo26_visdrone_best.pt', conf=0.15):
        print(f"Loading YOLO26 Model: {model_path}")
        self.model = YOLO(model_path)
        self.conf = conf
        self.device = 0 if torch.cuda.is_available() else 'cpu'
        print(f"Running on: {self.device}")
        
    def infer(self, frame):
        """
        Run inference on a single frame. Optimized for drone feeds.
        """
        results = self.model.predict(
            frame, 
            conf=self.conf, 
            device=self.device, 
            half=(self.device == 0),
            imgsz=640,
            verbose=False
        )
        return results[0]

    def draw_results(self, frame, results):
        """Draws bounding boxes and labels on the frame."""
        return results.plot()

# Integration:
# adapter = YOLO26GCSAdapter('yolo26_visdrone_best.pt')
# results = adapter.infer(frame)
# processed_frame = adapter.draw_results(frame, results)
