from PySide6.QtCore import QObject, Signal

class GimbalPIDController(QObject):
    # Signals pitch, yaw adjustments in degrees
    gimbal_setpoint = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.Kp_p, self.Ki_p, self.Kd_p = 0.5, 0.01, 0.1
        self.error_p_sum, self.last_error_p = 0, 0
        self.Kp_y, self.Ki_y, self.Kd_y = 0.5, 0.01, 0.1
        self.error_y_sum, self.last_error_y = 0, 0
        
        self.mount_pitch, self.mount_yaw = 0.0, 0.0

    def update_gains(self, kp, ki, kd, is_pitch=True):
        if is_pitch:
            self.Kp_p, self.Ki_p, self.Kd_p = kp, ki, kd
            self.error_p_sum = 0 # Reset integrals on gain change
        else:
            self.Kp_y, self.Ki_y, self.Kd_y = kp, ki, kd
            self.error_y_sum = 0
        print(f"Updated {'Pitch' if is_pitch else 'Yaw'} Gains -> P:{kp} I:{ki} D:{kd}")

    def calculate_adjustment(self, error_x, error_y):
        self.error_y_sum += error_x
        d_error_x = error_x - self.last_error_y
        yaw_adj = (self.Kp_y * error_x) + (self.Ki_y * self.error_y_sum) + (self.Kd_y * d_error_x)
        self.last_error_y = error_x

        self.error_p_sum += error_y
        d_error_y = error_y - self.last_error_p
        pitch_adj = (self.Kp_p * error_y) + (self.Ki_p * self.error_p_sum) + (self.Kd_p * d_error_y)
        self.last_error_p = error_y

        self.mount_yaw = max(-90, min(90, self.mount_yaw + yaw_adj))
        self.mount_pitch = max(-90, min(90, self.mount_pitch + pitch_adj))

        # Emit the new setpoints
        self.gimbal_setpoint.emit(self.mount_pitch, self.mount_yaw)
