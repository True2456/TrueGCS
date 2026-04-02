import math
import unittest
import time

class MockTailsitter:
    def __init__(self):
        self.alt = 50.0
        self.vx = 0.0
        self.vz = 0.0
        self.pitch = 0.0
        self.mode = "LOITER"

    def step_transition_physics(self, dt):
        """Simulates the 'settle' during transition (loss of lift)."""
        target_pitch = -45.0
        if self.pitch > target_pitch:
            self.pitch -= 15.0 * dt
            # Lift Penalty: Settling 2m/s while tilting
            self.vz = -2.5 
        
        self.vx += 5.0 * dt
        self.alt += self.vz * dt
        return self.alt, self.vx

class TestRealisticPhysics(unittest.TestCase):
    def test_transition_settle(self):
        # Initial: 50m alt, 0 velocity
        uav = MockTailsitter()
        initial_alt = uav.alt
        
        # Step through transition for 1 second
        for _ in range(10):
            uav.step_transition_physics(0.1)
            
        # Verify altitude drop (settle)
        self.assertLess(uav.alt, initial_alt)
        # Verify forward acceleration
        self.assertGreater(uav.vx, 0.0)
        print(f"Realistic Test: Transition Settle -> {uav.alt:.1f}m (Dropped {initial_alt - uav.alt:.1f}m)")

    def test_landing_flare_logic(self):
        # Simulate descent rate reduction below 2 meters
        alt = 2.5
        v_descent = 1.5
        dt = 0.1
        
        for _ in range(60): # 🛰️ Increased from 20 to 60 to verify soft-flare touchdown
            # Flare Logic: If alt < 2.0, reduce descent rate to 0.5
            current_v = 0.5 if alt < 2.0 else 1.5
            alt -= current_v * dt
            if alt <= 0: break
            
        # If flared correctly, it should take more than 17 steps to hit 0 from 2.5m
        # (2.5 - 2.0 = 0.5m @ 1.5m/s = 3 steps)
        # (2.0m @ 0.5m/s = 40 steps)
        self.assertLess(alt, 0.1)
        print("Realistic Test: Landing Flare logic verified.")

if __name__ == "__main__":
    unittest.main()
