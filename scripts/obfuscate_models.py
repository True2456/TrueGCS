import os
import sys

# Add project root to path so we can import core.shield
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.shield import TrueShield

def obfuscate_all():
    shield = TrueShield()
    models_dir = "models"
    
    if not os.path.exists(models_dir):
        print(f"Error: {models_dir} directory not found.")
        return

    files = [f for f in os.listdir(models_dir) if f.endswith(".pt")]
    
    if not files:
        print("No .pt files found in models/ directory.")
        return

    print(f"Shield: Found {len(files)} models to protect.")
    
    for f in files:
        input_path = os.path.join(models_dir, f)
        output_path = os.path.join(models_dir, f.replace(".pt", ".tsm"))
        
        shield.encrypt_file(input_path, output_path)
        
        # Optional: Remove original .pt file
        os.remove(input_path)
        print(f"Shield: Removed original {f}")

    print("\nShield: All models are now protected (.tsm).")
    print("Shield: Remember to update video_thread.py to load .tsm files.")

if __name__ == "__main__":
    obfuscate_all()
