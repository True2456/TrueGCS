import os
import sys
import shutil

def find_binary(name):
    """
    Locates a binary (ffmpeg, gst-launch-1.0, etc.) in a bundle-aware way.
    Checks:
    1. Alongside the executable (bundled)
    2. In the Resources folder (macOS bundle)
    3. Standard system paths (Homebrew, /usr/bin, etc.)
    """
    # 1. Check if we're running as a bundle
    if getattr(sys, 'frozen', False):
        # Base path of the bundle/executable
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller temp folder or Resources on Mac
            bundle_dir = sys._MEIPASS
        else:
            bundle_dir = os.path.dirname(sys.executable)
            
        # Try finding it in the bundle root
        ext = ".exe" if sys.platform == "win32" else ""
        bundled_path = os.path.join(bundle_dir, f"{name}{ext}")
        if os.path.exists(bundled_path):
            return bundled_path
            
    # 2. Check system PATH
    system_path = shutil.which(name)
    if system_path:
        return system_path
        
    # 3. macOS Specific Fallbacks (Homebrew)
    if sys.platform == "darwin":
        mac_paths = [
            f"/opt/homebrew/bin/{name}",
            f"/usr/local/bin/{name}",
            f"/opt/local/bin/{name}",
        ]
        for p in mac_paths:
            if os.path.exists(p):
                return p
                
    # 4. Windows Specific Fallbacks
    if sys.platform == "win32":
        win_paths = [
            f"C:\\ffmpeg\\bin\\{name}.exe",
            f"C:\\Program Files\\ffmpeg\\bin\\{name}.exe",
        ]
        for p in win_paths:
            if os.path.exists(p):
                return p
                
    return name # Fallback to name and hope it's in PATH
