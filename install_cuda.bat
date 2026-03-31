@echo off
echo =======================================================
echo  ISR GROUND CONTROL STATION - NVIDIA CUDA UPGRADE
echo =======================================================
echo.
echo Upgrading YOLOv8 PyTorch Backend to use CUDA cu121 natively...
echo This will allow the GCS to seamlessly detect objects at 30+ FPS using your RTX 3060.
echo.
echo WARNING: This download is approximately ~2.5GB. Please do not close this window.
echo.

call venv\Scripts\activate.bat
pip uninstall -y torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install ultralytics

echo.
echo =======================================================
echo  INSTALLATION COMPLETE
echo =======================================================
echo You may now start the GCS and select "CUDA" in the Configuration Tab!
pause
