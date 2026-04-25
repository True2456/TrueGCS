import os
import io
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet

class TrueShield:
    """
    TrueGCS Model Protection System (Shield)
    Provides AES-256 encryption/decryption for AI weights.
    """
    
    @staticmethod
    def generate_key(passphrase: str, salt: bytes = b'truegcs_salt_2026') -> bytes:
        """Derives a stable 32-byte key from a passphrase."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))

    def __init__(self, key_passphrase: str = "TrueGCS_Tactical_Alpha_2026"):
        key = self.generate_key(key_passphrase)
        self.fernet = Fernet(key)

    def encrypt_file(self, input_path: str, output_path: str):
        """Encrypts a .pt file into a .tsm file."""
        with open(input_path, 'rb') as f:
            data = f.read()
        
        encrypted_data = self.fernet.encrypt(data)
        
        with open(output_path, 'wb') as f:
            f.write(encrypted_data)
        print(f"Shield: Encrypted {os.path.basename(input_path)} -> {os.path.basename(output_path)}")

    def decrypt_to_buffer(self, input_path: str) -> io.BytesIO:
        """Decrypts a .tsm file into an in-memory buffer."""
        with open(input_path, 'rb') as f:
            encrypted_data = f.read()
        
        decrypted_data = self.fernet.decrypt(encrypted_data)
        return io.BytesIO(decrypted_data)

    def decrypt_to_temp_file(self, input_path: str) -> str:
        """
        Decrypts a .tsm file into a temporary hidden file.
        Returns the path to the temporary file.
        """
        import tempfile
        import atexit
        
        with open(input_path, 'rb') as f:
            encrypted_data = f.read()
            
        decrypted_data = self.fernet.decrypt(encrypted_data)
        
        # Create a temp file that is deleted on exit
        fd, temp_path = tempfile.mkstemp(suffix=".pt", prefix=".shield_")
        with os.fdopen(fd, 'wb') as f:
            f.write(decrypted_data)
            
        def cleanup():
            try: os.remove(temp_path)
            except: pass
            
        atexit.register(cleanup)
        return temp_path
