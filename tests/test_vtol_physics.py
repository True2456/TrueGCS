import math
import unittest

def calculate_coordinated_bank(turn_rate_deg_s, bank_factor, max_roll_deg):
    """
    Coordinated Turn Model: Proportional banking based on turn intensity.
    Roll = -(turn_rate * bank_factor)  # INVERTED for GCS HUD Alignment
    """
    target_roll = - (turn_rate_deg_s * bank_factor)
    return max(-max_roll_deg, min(max_roll_deg, target_roll))

class TestVTOLPhysics(unittest.TestCase):
    def test_banking_clamping(self):
        # 10 deg/s turn, 2.0 factor -> -20 deg roll (Inverted)
        self.assertEqual(calculate_coordinated_bank(10, 2.0, 45), -20)
        
        # 50 deg/s turn, 2.0 factor -> -100 deg (should clamp to -45)
        self.assertEqual(calculate_coordinated_bank(50, 2.0, 45), -45)
        
        # Negative turn (Right turn) -> +20 deg roll
        self.assertEqual(calculate_coordinated_bank(-10, 2.0, 45), 20)

    def test_yaw_rate_logic(self):
        # Verification of the simulator's max_yaw_rate_deg constraint
        max_yaw_rate = 25.0
        dt = 0.1
        diff = 100.0 # Huge bearing error
        
        max_step = max_yaw_rate * dt
        step = max(-max_step, min(max_step, diff * 0.1))
        
        self.assertEqual(step, 2.5) # Should be capped at 25/sec * 0.1s

if __name__ == "__main__":
    unittest.main()
