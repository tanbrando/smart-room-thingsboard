#!/usr/bin/env bash
# Chỉ cài thư viện cho Smart Room, dùng venv CÓ SẴN.
#   bash install.sh
# Đổi venv khác:  VENV_DIR=/duong/dan/.venv bash install.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${VENV_DIR:-/home/qntv/IOT/.venv}"
PYTHON="$VENV_DIR/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "Không tìm thấy venv tại $VENV_DIR" >&2
    exit 1
fi

echo "==> Cài gói hệ thống (OpenCV, Picamera2, GPIO)"
sudo apt update
sudo apt install -y \
    python3-numpy python3-opencv opencv-data python3-picamera2 \
    gpiod python3-lgpio

# Cài gói RPi.GPIO (hỗ trợ cả Debian Trixie/Bookworm và các bản cũ)
sudo apt install -y python3-rpi-lgpio 2>/dev/null || sudo apt install -y python3-rpi.gpio 2>/dev/null || true

# venv phải thấy được gói apt (cv2, picamera2)
if grep -q "include-system-site-packages = false" "$VENV_DIR/pyvenv.cfg"; then
    echo "==> Bật include-system-site-packages cho venv"
    sed -i 's/include-system-site-packages = false/include-system-site-packages = true/' "$VENV_DIR/pyvenv.cfg"
fi

echo "==> Kiểm tra các gói trong venv"
if "$PYTHON" -c "import paho.mqtt.client, RPi.GPIO, adafruit_dht" 2>/dev/null; then
    echo "    Đã có đủ, bỏ qua bước cài."
else
    echo "    Thiếu gói, cài từ requirements.txt"
    "$PYTHON" -m pip install -r "$PROJECT_DIR/requirements.txt"
fi

echo "==> Xong."
