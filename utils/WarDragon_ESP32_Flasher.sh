#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# Variables
ESPTOOL_REPO="https://github.com/alphafox02/esptool"
FIRMWARE_URL="https://github.com/alphafox02/T-Halow/raw/refs/heads/wifi_rid/firmware/firmware_T-Halow_DragonOS_RID_Scanner_WiFi.bin"
FIRMWARE_FILE="firmware_T-Halow_DragonOS_RID_Scanner_WiFi.bin"
ESPTOOL_DIR="esptool"
SERVICE_NAME="zmq-decoder.service"
ESP_PORT="/dev/esp0"

# Clone the esptool repository if it doesn't already exist
if [ ! -d "$ESPTOOL_DIR" ]; then
    echo "Cloning esptool repository..."
    git clone "$ESPTOOL_REPO"
else
    echo "Directory '$ESPTOOL_DIR' already exists. Skipping clone."
fi

# Change to the esptool directory
cd "$ESPTOOL_DIR"

# Download the firmware if it doesn't already exist
if [ ! -f "$FIRMWARE_FILE" ]; then
    echo "Downloading firmware..."
    wget "$FIRMWARE_URL" -O "$FIRMWARE_FILE"
else
    echo "Firmware file '$FIRMWARE_FILE' already exists. Skipping download."
fi

# Stop the zmq-decoder service if it is running
echo "Stopping $SERVICE_NAME if running..."
sudo systemctl stop "$SERVICE_NAME" || echo "$SERVICE_NAME is not running or could not be stopped."

# Flash the firmware using esptool.py
echo "Flashing firmware to the device..."
python3 esptool.py \
    --chip esp32s3 \
    --port "$ESP_PORT" \
    --baud 115200 \
    --before default_reset \
    --after hard_reset \
    write_flash -z \
    --flash_mode dio \
    --flash_freq 80m \
    --flash_size 16MB \
    0x10000 "$FIRMWARE_FILE"

echo "Firmware flashing complete."

# Restart the zmq-decoder service
echo "Starting $SERVICE_NAME..."
sudo systemctl start "$SERVICE_NAME"

echo "Service restarted. Script complete."
