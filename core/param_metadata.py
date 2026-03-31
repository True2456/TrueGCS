import os
import json
import requests
from PySide6.QtCore import QObject, Signal, QThread

METADATA_URL = "https://autotest.ardupilot.org/Parameters/ArduPlane/apm.pdef.json"
CACHE_DIR = "cache"
CACHE_FILE = os.path.join(CACHE_DIR, "param_metadata.json")

class MetadataDownloader(QThread):
    finished = Signal(dict)
    error = Signal(str)

    def run(self):
        try:
            if not os.path.exists(CACHE_DIR):
                os.makedirs(CACHE_DIR)
            
            print(f"Metadata Service: Downloading {METADATA_URL}...")
            response = requests.get(METADATA_URL, timeout=15)
            if response.status_code == 200:
                data = response.json()
                with open(CACHE_FILE, "w") as f:
                    json.dump(data, f)
                self.finished.emit(data)
                print("Metadata Service: Download complete.")
            else:
                self.error.emit(f"HTTP {response.status_code}")
        except Exception as e:
            self.error.emit(str(e))

class ParamMetadataProvider(QObject):
    """Handles fetching and deep-lookup of ArduPilot parameter metadata."""
    loaded = Signal()

    def __init__(self):
        super().__init__()
        self.data = {}
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r") as f:
                    self.data = json.load(f)
                print(f"Metadata Service: Loaded {len(self.data)} groups from cache.")
            except Exception as e:
                print(f"Metadata Service: Cache load failed: {e}")

    def fetch_latest(self):
        self.downloader = MetadataDownloader()
        self.downloader.finished.connect(self._on_fetch_success)
        self.downloader.start()

    def _on_fetch_success(self, data):
        self.data = data
        self.loaded.emit()

    def get_param_info(self, param_name):
        """Finds metadata for a parameter by name (searches nested prefix groups and 'ArduPlane' root)."""
        if not self.data:
            return None
        
        # 1. Check direct level (uncommon)
        if param_name in self.data:
            return self.data[param_name]
        
        # 2. Check group-based lookup (e.g. data['Q_']['Q_ENABLE'])
        for group_key, params in self.data.items():
            if isinstance(params, dict) and param_name in params:
                return params[param_name]
        
        # 3. Check ArduPlane/Plane key if it exists
        for vehicle in ['ArduPlane', 'Plane', 'ArduCopter', 'Copter']:
            if vehicle in self.data:
                vehicle_data = self.data[vehicle]
                if param_name in vehicle_data:
                    return vehicle_data[param_name]
                # Deep search vehicle
                for group in vehicle_data.values():
                    if isinstance(group, dict) and param_name in group:
                        return group[param_name]
        
        return None
