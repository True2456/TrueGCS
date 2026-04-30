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
        
        # Wire Brain mission relay to the GCS upload pipeline 🛰️
        self.brain.on_mission_received = self.upload_search_mission
        
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

    def upload_search_mission(self, nid, sysid, waypoints):
        """
        Called when the Brain relays a survey mission.
        nid: str node ID (e.g. "1") — telemetry_nodes may use int keys
        sysid: int MAVLink system ID (e.g. 1)
        waypoints: list of {lat, lon, alt, speed}
        """
        # telemetry_nodes keys may be int or str — try both
        tel = self.window.telemetry_nodes.get(nid)
        if tel is None:
            try:
                tel = self.window.telemetry_nodes.get(int(nid))
            except (ValueError, TypeError):
                pass
        if tel is None:
            print(f"FleetObserver: Mission rejected — node '{nid}' not found. "
                  f"Available: {list(self.window.telemetry_nodes.keys())} "
                  f"(types: {[type(k).__name__ for k in self.window.telemetry_nodes.keys()]})")
            return
        print(f"FleetObserver: Uploading {len(waypoints)} waypoints to Node {nid} SysID {sysid}")
        tel.upload_mission(int(sysid), waypoints)
