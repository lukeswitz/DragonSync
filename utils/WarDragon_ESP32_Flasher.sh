#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# Variables
ESPTOOL_REPO="https://github.com/alphafox02/esptool"
ESPTOOL_DIR="esptool"
SERVICE_NAME="zmq-decoder.service"
ESP_PORT="/dev/esp0"

# Firmware options
declare -A FIRMWARE_OPTIONS=(
    [1]="WiFi RID Scanner"
    [2]="WiFI/BT Dual-RID Scanner"
)

declare -A FIRMWARE_URLS=(
    [1]="https://github.com/alphafox02/T-Halow/raw/refs/heads/wifi_rid/firmware/firmware_T-Halow_DragonOS_RID_Scanner_WiFi.bin"
    [2]="https://github.com/lukeswitz/T-Halow/raw/refs/heads/master/firmware/tHalow_s3dualcoreRIDfirmware.bin"
)

declare -A FIRMWARE_FILES=(
    [1]="firmware_T-Halow_DragonOS_RID_Scanner_WiFi.bin"
    [2]="tHalow_s3dualcoreRIDfirmware.bin"
)

# Check if esptool.py is available in PATH
if command -v esptool.py >/dev/null 2>&1; then
    echo "esptool.py is already installed system-wide."
    ESPTOOL_CMD="esptool.py"
else
    echo "esptool.py not found in PATH, will use local version."
    
    # Clone the esptool repository if it doesn't already exist
    if [ ! -d "$ESPTOOL_DIR" ]; then
        echo "Cloning esptool repository..."
        git clone "$ESPTOOL_REPO"
    else
        echo "Directory '$ESPTOOL_DIR' already exists. Skipping clone."
    fi

    # Verify esptool.py exists in the cloned directory
    if [ ! -f "$ESPTOOL_DIR/esptool.py" ]; then
        echo "Error: esptool.py not found in $ESPTOOL_DIR directory"
        exit 1
    fi

    ESPTOOL_CMD="$ESPTOOL_DIR/esptool.py"
fi

# Display firmware options
echo "Available firmware options:"
for key in "${!FIRMWARE_OPTIONS[@]}"; do
    echo "  $key) ${FIRMWARE_OPTIONS[$key]}"
done

# Get user input
read -p "Select firmware option (1-${#FIRMWARE_OPTIONS[@]}): " choice

# Validate input
if [[ ! "$choice" =~ ^[1-${#FIRMWARE_OPTIONS[@]}]$ ]]; then
    echo "Invalid selection. Exiting."
    exit 1
fi

# Set selected firmware
FIRMWARE_URL="${FIRMWARE_URLS[$choice]}"
FIRMWARE_FILE="${FIRMWARE_FILES[$choice]}"

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

# Flash the firmware using esptool
echo "Flashing firmware to the device..."
python3 "$ESPTOOL_CMD" \
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
