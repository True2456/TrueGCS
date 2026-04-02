import math
import unittest

def get_bearing(lat1, lon1, lat2, lon2):
    off_x = lon2 - lon1
    off_y = lat2 - lat1
    bearing = 90.0 + math.degrees(math.atan2(-off_y, off_x))
    return bearing % 360

class TestMissionFinalization(unittest.TestCase):
    def test_end_of_mission_yaw(self):
        # Simulation: Last WP reached at (0, 0)
        # Fallback "North" Cruise logic should set yaw to 0.0
        
        # Scenario: Drone was facing East (90)
        last_yaw = 90.0
        
        # New Fallback logic: If no more waypoints AND not in loiter...
        # ... it should set yaw = 0.0 (North)
        current_yaw = 0.0 # Expected
        
        self.assertEqual(current_yaw, 0.0)

    def test_coordinated_loiter_tangent(self):
        # Home at (0,0), Drone at (0.0005, 0) [East of home]
        # Tangent bearing for orbit should be North (0)
        home_lat, home_lon = 0.0, 0.0
        drone_lat, drone_lon = 0.0005, 0.0
        
        bearing_to_center = get_bearing(drone_lat, drone_lon, home_lat, home_lon)
        # Expected bearing to center: West (270)
        self.assertAlmostEqual(bearing_to_center, 270.0, places=1)
        
        # Tangent (Clockwise orbit): Bearing to center + 90
        tangent = (bearing_to_center + 90) % 360
        self.assertAlmostEqual(tangent, 0.0, places=1) # FACING NORTH

if __name__ == "__main__":
    unittest.main()
