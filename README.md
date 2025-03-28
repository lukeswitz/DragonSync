
# DragonSync  

## Overview  

DragonSync is a powerful tool for monitoring Remote ID and DroneID-compliant drones and system status, generating Cursor on Target (CoT) messages in real-time. It integrates with ATAK or other TAK clients and leverages ZeroMQ (ZMQ) for seamless data flow. Everything is pre-configured for use on the **WarDragon**, but installation on other systems is also supported with additional dependencies.

---

## Features  

- **Remote ID Drone Detection:**  
   Uses [DroneID](https://github.com/alphafox02/DroneID]) to detect Bluetooth Remote ID signals. Thanks to @bkerler for this fantastic tool. WiFi Remote ID is currently handled by an esp32.
- **DJI DroneID Detection:**
   Uses [Antsdr_DJI](https://github.com/alphafox02/antsdr_dji_droneid]) to detect DJI DroneID signals.  
- **System Status Monitoring:**  
   `wardragon_monitor.py` gathers hardware status (via `lm-sensors`), GPS location, and serial number.  
- **CoT Generation:**  
   Converts system and drone data into CoT messages.  
- **ZMQ Support:**  
   Uses ZMQ for communication between components.  
- **TAK/ATAK Integration:**  
   Supports multicast for ATAK or direct TAK server connections.  

---

## Requirements  

### **Pre-installed on WarDragon Pro: (Skip to step 5)**  
If running DragonSync on the WarDragon Pro kit, all dependencies are pre-configured, including hardware-specific sensors and GPS modules.

### **For Other Systems:**  
If you install DragonSync elsewhere, ensure the following:  

- **Python 3.x**  
- **lm-sensors**: Install via:  
   ```bash
   sudo apt update && sudo apt install lm-sensors
   ```  
- **gpsd** (GPS Daemon):  
   ```bash
   sudo apt install gpsd gpsd-clients
   ```  
- **USB GPS Module**: Ensure a working GPS connected to the system.  
- Other necessary Python packages (listed in the `requirements.txt` or as dependencies).  

---

## Setup and Usage 

### 1. Clone the Repositories  

Clone the **DroneID** repository:  
```bash
git clone https://github.com/alphafox02/DroneID
cd DroneID
git submodule init
git submodule update
```

Clone the **DragonSync** repository:  
```bash
git clone https://github.com/alphafox02/DragonSync/
```

### 2. Start the Sniffle Receiver  

This command configures the dongle to capture Bluetooth 5 long-range extended packets and sends the data via ZMQ:  

```bash
python3 sniffle/python_cli/sniff_receiver.py -l -e -a -z
```

### 3. Run the ZMQ Decoder  

Open another terminal and run the decoder to process the captured packets and serve the decoded results on **port 4224**:  

```bash
cd DroneID
python3 zmq_decoder.py -z
```

### 4. Start the WarDragon Monitor  

In a new terminal, start the `wardragon_monitor.py` script to collect system info and GPS data, serving it on **port 4225**:  

```bash
cd DragonSync
python3 wardragon_monitor.py --zmq_host 127.0.0.1 --zmq_port 4225 --interval 30
```

### 5. Launch DragonSync  

#### **Without TAK Server (Multicast Only)**  

```bash
python3 dragonsync.py --zmq-host 0.0.0.0 --zmq-port 4224 --zmq-status-port 4225
```

#### **With TAK Server Integration**  

```bash
python3 dragonsync.py --zmq-host 0.0.0.0 --zmq-port 4224 --zmq-status-port 4225 --tak-host <tak_host> --tak-port <tak_port>
```

Replace `<tak_host>` and `<tak_port>` with your TAK server’s IP address and port.  

---

## How It Works  

1. **Sniffle Receiver:**  
   Captures Bluetooth Remote ID packets and forwards them via ZMQ.  

2. **ZMQ Decoder:**  
   Listens for the captured packets, decodes the data, and transmits it on **port 4224**.  

3. **WarDragon Monitor:**  
   Collects system status, GPS location, and the serial number, serving this data on **port 4225**.  

4. **DragonSync:**  
   - Subscribes to ZMQ feeds on **ports 4224** and **4225**.  
   - Converts incoming data into **CoT messages**.  
   - Sends CoT messages to a TAK server or multicasts them to the network for ATAK clients.  

---

## Example Command  

To start DragonSync using ZMQ on ports 4224 and 4225:  

```bash
python3 dragonsync.py --zmq-host 127.0.0.1 --zmq-port 4224 --zmq-status-port 4225
```

---

## Troubleshooting  

### **No Data on ATAK?**  
- Ensure ATAK and DragonSync are on the **same network**.  
- Verify **multicast traffic** is enabled on your network.  
- Confirm that the correct **ZMQ host and port** are specified.  

### **Debugging Tips:**  
- Use the `-d` flag with DragonSync for **debug logging**.  
- Use **Wireshark** to verify multicast traffic.  

---

## License  

```text
MIT License  

© 2024 cemaxecuter  

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:  

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.  

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```
