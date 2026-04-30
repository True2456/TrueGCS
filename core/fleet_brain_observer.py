import json
from core.brain_client import BrainClient
from PySide6.QtCore import QObject

class FleetBrainObserver(QObject):
    """
    An independent observer that mirrors GCS state to the Fleet Brain
    and executes remote commands without modifying core GCS logic.
    """
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.brain = BrainClient(station_name="TrueGCS-Master")
        self.brain.start()
        
        # We need to bridge incoming commands to the GCS window's existing handlers
        self.brain.nodes = self.window.telemetry_nodes # Live link to nodes
        
        # Intercept node discovery to sync with the brain
        self._wrap_signal_connections()
        
    def _wrap_signal_connections(self):
        # We find all existing nodes and sync them
        for nid, tel in self.window.telemetry_nodes.items():
            self.sync_node(tel)
            
        # We monkeypatch the connection function to catch future nodes
        # Note: In main.py, connect_telemetry_signals is local, 
        # so we'll need to hook it after it's defined or just monitor the node manager.
        pass

    def sync_node(self, tel):
        """Called when a new node is discovered/added."""
        print(f"FleetObserver: SYNCING Node {tel.node_id} to Strategic Brain...")
        tel.signals.position_updated.connect(self.brain.update_position)
        tel.signals.hud_updated.connect(self.brain.update_hud)
        self.brain.register_node(tel.node_id, tel)
        print(f"FleetObserver: Node {tel.node_id} linked to Brain.")
