#!/usr/bin/env python3
"""
MIT License

Copyright (c) 2024 cemaxecuter

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import argparse
import json
import zmq
import time
import subprocess
import psutil
import signal
import sys
import uuid
import ssl
import socket
import datetime
import time
import tempfile
from collections import deque
from typing import Optional, Dict, Any
import struct
import atexit
import os
            print(f"Unexpected error retrieving serial number: {e}")
        if debug:
    except Exception as e:
            print(f"Error retrieving serial number: {e}")
        if debug:
    except subprocess.CalledProcessError as e:

            return serial_number
                print(f"Using serial number: {serial_number}")
            if debug:
        if serial_number and serial_number not in invalid_serials:

                break
                serial_number = line.split(':')[-1].strip()
            if 'Serial Number:' in line:
        for line in output.split('\n'):
        serial_number = None
        output = result.stdout
        )
            capture_output=True, text=True, check=True
            ['sudo', 'dmidecode', '-t', 'system'],
        result = subprocess.run(
    try:
    ]
        'Not Specified', 'Unknown', ''
        'N/A', 'Default string', 'To be filled by O.E.M.', 'None',
    invalid_serials = [
    """Retrieve the system's serial number or MAC address as a unique identifier."""
def get_serial_number(debug=False):
    return {'latitude': 'N/A', 'longitude': 'N/A', 'altitude': 'N/A', 'speed': 'N/A'}
            print(f"Error connecting to gpsd: {e}")
        if debug:
    except Exception as e:
            print("No GPS data available.")
        if debug:
    except StopIteration:
            print(f"Missing GPS data key: {e}")
        if debug:
    except KeyError as e:

        return gps_info
            print(f"Received GPS data: {gps_info}")
        if debug:
        }
            'speed': getattr(report, 'speed', 'N/A')
            'altitude': getattr(report, 'alt', 'N/A'),
            'longitude': getattr(report, 'lon', 'N/A'),
            'latitude': getattr(report, 'lat', 'N/A'),
        gps_info = {

            report = gpsd.next()
        while report['class'] != 'TPV':
        report = gpsd.next()

            print("Waiting for GPS data...")
        if debug:

        gpsd = gps(mode=WATCH_ENABLE | WATCH_NEWSTYLE)
    try:
    """Retrieve GPS data from gpsd."""
def get_gps_data(debug=False):
from gps import gps, WATCH_ENABLE, WATCH_NEWSTYLE

import zmq
from lxml import etree
import xml.sax.saxutils

try:
    import meshtastic
    import meshtastic.serial_interface
    HAVE_MESHTASTIC = True
except ImportError:
    HAVE_MESHTASTIC = False
    logger.warning("Meshtastic support not available - package not installed")

    # If serial number is invalid or not found, try to get MAC address
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives import serialization

from tak_client import TAKClient
from tak_udp_client import TAKUDPClient
from drone import Drone
from system_status import SystemStatus
from manager import DroneManager
from messaging import CotMessenger
from utils import load_config, validate_config, get_str, get_int, get_float, get_bool

# Setup logging
def setup_logging(debug: bool):
    """Set up logging configuration."""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if debug else logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    ch.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(ch)

logger = logging.getLogger(__name__)

def setup_tls_context(tak_tls_p12: str, tak_tls_p12_pass: Optional[str], tak_tls_skip_verify: bool) -> Optional[ssl.SSLContext]:
    """Sets up the TLS context using the provided PKCS#12 file."""
    if not tak_tls_p12:
        return None

    try:
    """Retrieve the CPU temperature using the 'sensors' command."""
def get_cpu_temperature(debug=False):

            return generated_uuid
                print(f"Generated and saved UUID: {generated_uuid}")
            if debug:
                f.write(generated_uuid)
            with open(uid_file, 'w') as f:
            generated_uuid = str(uuid.uuid4())
        else:
                return saved_uuid
                    print(f"Using saved UUID: {saved_uuid}")
                if debug:
                saved_uuid = f.read().strip()
            with open(uid_file, 'r') as f:
        if os.path.exists(uid_file):
        uid_file = '/var/tmp/system_uid.txt'
        # Generate UUID and store it
            print(f"Error retrieving MAC address: {e}")
        if debug:
    except Exception as e:
            return generated_uuid
                print(f"No serial number or MAC address found. Generated and saved UUID: {generated_uuid}")
            if debug:
                f.write(generated_uuid)
            with open(uid_file, 'w') as f:
            generated_uuid = str(uuid.uuid4())
        else:
                return saved_uuid
                    print(f"Using saved UUID: {saved_uuid}")
                if debug:
                saved_uuid = f.read().strip()
            with open(uid_file, 'r') as f:
        if os.path.exists(uid_file):
        uid_file = '/var/tmp/system_uid.txt'
        # If no MAC address found, generate UUID and store it
                            return mac_address
                                print(f"Using MAC address from interface {interface} as UID: {mac_address}")
                            if debug:
                        if mac_address and mac_address != '000000000000':
                        mac_address = addr.address.replace(':', '').lower()
                    if interface.startswith(('eth', 'en', 'wlan')):
                if addr.family == psutil.AF_LINK:
            for addr in addrs:
        for interface, addrs in psutil.net_if_addrs().items():
        mac_address = None
        with open(tak_tls_p12, 'rb') as p12_file:
            p12_data = p12_file.read()
    except OSError as err:
        logger.critical("Failed to read TAK server TLS PKCS#12 file: %s.", err)
        sys.exit(1)

    p12_pass = tak_tls_p12_pass.encode() if tak_tls_p12_pass else None

    try:
        key, cert, more_certs = pkcs12.load_key_and_certificates(p12_data, p12_pass)
    except Exception as err:
        logger.critical("Failed to load TAK server TLS PKCS#12: %s.", err)
        sys.exit(1)

    key_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption() if not p12_pass else serialization.BestAvailableEncryption(p12_pass)
    )
    cert_bytes = cert.public_bytes(serialization.Encoding.PEM)
    ca_bytes = b"".join(
        cert.public_bytes(serialization.Encoding.PEM) for cert in more_certs
    ) if more_certs else b""

    # Create temporary files and ensure they are deleted on exit
    key_temp = tempfile.NamedTemporaryFile(delete=False)
    cert_temp = tempfile.NamedTemporaryFile(delete=False)
    ca_temp = tempfile.NamedTemporaryFile(delete=False)

    key_temp.write(key_bytes)
    cert_temp.write(cert_bytes)
    ca_temp.write(ca_bytes)

    key_temp_path = key_temp.name
    cert_temp_path = cert_temp.name
    ca_temp_path = ca_temp.name

    key_temp.close()
    cert_temp.close()
    ca_temp.close()

    # Register cleanup
    socket = context.socket(zmq.PUB)
    context = zmq.Context()
    """Create and bind a ZMQ PUB socket."""
def create_zmq_context(host, port):
    return temps
            print(f"Unexpected error reading Pluto/Zynq temps: {e}")
        if debug:
    except Exception as e:
            print(f"AntSDR/Pluto Temps -> Pluto: {temps['pluto_temp']} °C, Zynq: {temps['zynq_temp']} °C")
        if debug:

        temps['zynq_temp']  = round(zynq_temp_c, 1)
        temps['pluto_temp'] = round(pluto_temp_c, 1)

        zynq_temp_c = (raw + offset) * scale / 1000.0

        scale  = float(subprocess.run(cmd_xadc_scale,  capture_output=True, text=True, check=True).stdout.strip().split()[-1])
        offset = float(subprocess.run(cmd_xadc_offset, capture_output=True, text=True, check=True).stdout.strip().split()[-1])
        raw    = float(subprocess.run(cmd_xadc_raw,    capture_output=True, text=True, check=True).stdout.strip().split()[-1])

        cmd_xadc_scale  = ['iio_attr', '-u', uri, '-c', 'xadc', 'temp0', 'scale']
        cmd_xadc_offset = ['iio_attr', '-u', uri, '-c', 'xadc', 'temp0', 'offset']
        cmd_xadc_raw    = ['iio_attr', '-u', uri, '-c', 'xadc', 'temp0', 'raw']

        pluto_temp_c = float(pluto_raw_str) / 1000.0
        pluto_raw_str = pluto_raw_out.stdout.strip().split()[-1]
        pluto_raw_out = subprocess.run(cmd_pluto, capture_output=True, text=True, check=True)
        cmd_pluto = ['iio_attr', '-u', uri, '-c', 'ad9361-phy', 'temp0', 'input']

                print("No USB device found, falling back to ip:192.168.2.1")
            if debug:
            uri = "ip:192.168.2.1"
        if not uri:

                break
                        break
                        uri = p.strip('[]')
                    if p.startswith('[') and p.endswith(']'):
                for p in parts:
                parts = line.split()
            if 'PLUTO' in line.upper():
        for line in result.stdout.strip().splitlines():
        result = subprocess.run(['iio_info', '-s'], capture_output=True, text=True, check=True)
        uri = None
    try:
        return temps
            print("iio_info or iio_attr not found. Can't retrieve Pluto temps.")
        if debug:
    if not (tool_exists('iio_info') and tool_exists('iio_attr')):
        return subprocess.run(['which', tool], capture_output=True).returncode == 0
    def tool_exists(tool):
    }
        'zynq_temp': 'N/A'
        'pluto_temp': 'N/A',
    temps = {
    """
    or 'N/A' values if not available.
      }
          "zynq_temp":  45.2   # in °C
          "pluto_temp": 48.7,  # in °C
      {
    Returns a dict like:

    using iio_attr (and iio_info) commands.
    Attempt to gather the Pluto (RF chip) and Zynq chip temperatures
    """
def get_pluto_temperatures(debug=False):
    }
        'uptime': time.time() - psutil.boot_time()
        'temperature': get_cpu_temperature(),
        'disk': psutil.disk_usage('/')._asdict(),
        'memory': psutil.virtual_memory()._asdict(),
        'cpu_usage': psutil.cpu_percent(),
    return {
    """Gather system statistics using psutil."""
def get_system_stats():

    return 'N/A'
            print(f"Error retrieving CPU temperature: {e}")
        if debug:
    except Exception as e:
                return float(temp_str)
                temp_str = line.split('+')[1].split('°')[0].strip()
            if 'Package id 0:' in line:
        for line in result.stdout.splitlines():
        result = subprocess.run(['sensors'], capture_output=True, text=True, check=True)
    atexit.register(os.unlink, key_temp_path)
    atexit.register(os.unlink, cert_temp_path)
    atexit.register(os.unlink, ca_temp_path)

    try:
        print(f"Error binding ZMQ socket: {e}")
    except zmq.ZMQError as e:
        socket.bind(f"tcp://{host}:{port}")
        tls_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        tls_context.load_cert_chain(certfile=cert_temp_path, keyfile=key_temp_path, password=p12_pass)
        if ca_bytes:
            tls_context.load_verify_locations(cafile=ca_temp_path)
        if tak_tls_skip_verify:
            tls_context.check_hostname = False
            tls_context.verify_mode = ssl.CERT_NONE
    except Exception as e:
        logger.critical(f"Failed to set up TLS context: {e}")
        sys.exit(1)
    return socket

    return tls_context

def zmq_to_cot(
    zmq_host: str,
    zmq_port: int,
    zmq_status_port: Optional[int],
    tak_host: Optional[str] = None,
    tak_port: Optional[int] = None,
    tak_tls_context: Optional[ssl.SSLContext] = None,
    tak_protocol: Optional[str] = 'TCP',
    multicast_address: Optional[str] = None,
    multicast_port: Optional[int] = None,
    enable_multicast: bool = False,
    rate_limit: float = 1.0,
    max_drones: int = 30,
    inactivity_timeout: float = 60.0,
    sys.exit(0)
    print("Exiting... Closing resources.")
    """Handle SIGINT/SIGTERM signals for graceful exit."""
def signal_handler(sig, frame):
):
    """Main function to convert ZMQ messages to CoT and send to TAK server."""
    context = zmq.Context()
    telemetry_socket = context.socket(zmq.SUB)
    telemetry_socket.connect(f"tcp://{zmq_host}:{zmq_port}")
    telemetry_socket.setsockopt_string(zmq.SUBSCRIBE, "")
    logger.debug(f"Connected to telemetry ZMQ socket at tcp://{zmq_host}:{zmq_port}")

    # Only create and connect the status_socket if zmq_status_port is provided
    if zmq_status_port:
        status_socket = context.socket(zmq.SUB)
        status_socket.connect(f"tcp://{zmq_host}:{zmq_status_port}")
        status_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        logger.debug(f"Connected to status ZMQ socket at tcp://{zmq_host}:{zmq_status_port}")
    else:
        status_socket = None
        logger.debug("No ZMQ status port provided. Skipping status socket setup.")

    # Initialize TAK clients based on protocol
    tak_client = None
    tak_udp_client = None

    if tak_host and tak_port:
        if tak_protocol == 'TCP':
            tak_client = TAKClient(tak_host, tak_port, tak_tls_context)
            tak_client.connect()
        elif tak_protocol == 'UDP':
            tak_udp_client = TAKUDPClient(tak_host, tak_port)
        else:
            logger.critical(f"Unsupported TAK protocol: {tak_protocol}. Must be 'TCP' or 'UDP'.")
            sys.exit(1)

    # Initialize CotMessenger
    cot_messenger = CotMessenger(
        tak_client=tak_client,
        tak_udp_client=tak_udp_client,
        multicast_address=multicast_address,
        multicast_port=multicast_port,
        enable_multicast=enable_multicast,
    """Main function to gather data and send it over ZMQ."""
def main(host, port, interval, debug):
    )

    # Initialize DroneManager with CotMessenger
    drone_manager = DroneManager(
        max_drones=max_drones,
        rate_limit=rate_limit,
        inactivity_timeout=inactivity_timeout,
        cot_messenger=cot_messenger
    )

    def signal_handler(sig, frame):
        """Handles signal interruptions for graceful shutdown."""
        logger.info("Interrupted by user")
        telemetry_socket.close()
        if status_socket:
            status_socket.close()
        if not context.closed:
            context.term()
        if tak_client:
            tak_client.close()
        if tak_udp_client:
            tak_udp_client.close()
        if cot_messenger:
            cot_messenger.close()
        logger.info("Cleaned up ZMQ resources")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    poller = zmq.Poller()
    poller.register(telemetry_socket, zmq.POLLIN)
    if status_socket:
        poller.register(status_socket, zmq.POLLIN)

    try:
        while True:
            socks = dict(poller.poll(timeout=1000))
            if telemetry_socket in socks and socks[telemetry_socket] == zmq.POLLIN:
                logger.debug("Received a message on the telemetry socket")
                message = telemetry_socket.recv_json()
                # logger.debug(f"Received telemetry JSON: {message}")

                drone_info = {}

                # Check if message is a list (original format) or dict (ESP32 format)
                if isinstance(message, list):
                    # Original format: list of dictionaries
                    for item in message:
                        if isinstance(item, dict):
                            # Process each item as a dictionary
                            if 'MAC' in item:
                                drone_info['mac'] = item['MAC']
                            if 'RSSI' in item:
                                drone_info['rssi'] = item['RSSI']

                            if 'Basic ID' in item:
                                id_type = item['Basic ID'].get('id_type')
                                drone_info['mac'] = item['Basic ID'].get('MAC')
                                drone_info['rssi'] = item['Basic ID'].get('RSSI')
                                if id_type == 'Serial Number (ANSI/CTA-2063-A)' and 'id' not in drone_info:
                                    drone_info['id'] = item['Basic ID'].get('id', 'unknown')
                                    logger.debug(f"Parsed Serial Number ID: {drone_info['id']}")
                                elif id_type == 'CAA Assigned Registration ID' and 'id' not in drone_info:
                                    drone_info['id'] = item['Basic ID'].get('id', 'unknown')
                                    logger.debug(f"Parsed CAA Assigned ID: {drone_info['id']}")

                            # Process location/vector messages
                            if 'Location/Vector Message' in item:
                                drone_info['lat'] = get_float(item['Location/Vector Message'].get('latitude', 0.0))
                                drone_info['lon'] = get_float(item['Location/Vector Message'].get('longitude', 0.0))
                                drone_info['speed'] = get_float(item['Location/Vector Message'].get('speed', 0.0))
                                drone_info['vspeed'] = get_float(item['Location/Vector Message'].get('vert_speed', 0.0))
                                drone_info['alt'] = get_float(item['Location/Vector Message'].get('geodetic_altitude', 0.0))
                                drone_info['height'] = get_float(item['Location/Vector Message'].get('height_agl', 0.0))

                            # Process Self-ID messages
                            if 'Self-ID Message' in item:
                                drone_info['description'] = item['Self-ID Message'].get('text', "")

                            # Process System messages
                            if 'System Message' in item:
                                drone_info['pilot_lat'] = get_float(item['System Message'].get('latitude', 0.0))
                                drone_info['pilot_lon'] = get_float(item['System Message'].get('longitude', 0.0))
                        else:
                            logger.error("Unexpected item type in message list; expected dict.")

                elif isinstance(message, dict):
                    if "AUX_ADV_IND" in message:
                        # Get RSSI from raw message
                        if "rssi" in message["AUX_ADV_IND"]:
                            drone_info['rssi'] = message["AUX_ADV_IND"]["rssi"]
                        # Get MAC from raw message
                        if "aext" in message and "AdvA" in message["aext"]:
                            mac = message["aext"]["AdvA"].split()[0]  # Extract MAC before " (Public)"
                            drone_info['mac'] = mac

                    # ESP32 format: single dictionary
                    if 'Basic ID' in message:
                        id_type = message['Basic ID'].get('id_type')
                        drone_info['mac'] = message['Basic ID'].get('MAC')
                        drone_info['rssi'] = message['Basic ID'].get('RSSI')
                        if id_type == 'Serial Number (ANSI/CTA-2063-A)' and 'id' not in drone_info:
                            drone_info['id'] = message['Basic ID'].get('id', 'unknown')
                            logger.debug(f"Parsed Serial Number ID: {drone_info['id']}")
                        elif id_type == 'CAA Assigned Registration ID' and 'id' not in drone_info:
                            drone_info['id'] = message['Basic ID'].get('id', 'unknown')
                            logger.debug(f"Parsed CAA Assigned ID: {drone_info['id']}")

                    # Process location/vector messages
                    if 'Location/Vector Message' in message:
                        drone_info['lat'] = get_float(message['Location/Vector Message'].get('latitude', 0.0))
                        drone_info['lon'] = get_float(message['Location/Vector Message'].get('longitude', 0.0))
                        drone_info['speed'] = get_float(message['Location/Vector Message'].get('speed', 0.0))
                        drone_info['vspeed'] = get_float(message['Location/Vector Message'].get('vert_speed', 0.0))
                        drone_info['alt'] = get_float(message['Location/Vector Message'].get('geodetic_altitude', 0.0))
                        drone_info['height'] = get_float(message['Location/Vector Message'].get('height_agl', 0.0))

                    # Process Self-ID messages
                    if 'Self-ID Message' in message:
                        drone_info['description'] = message['Self-ID Message'].get('text', "")

                    # Process System messages
                    if 'System Message' in message:
                        drone_info['pilot_lat'] = get_float(message['System Message'].get('latitude', 0.0))
                        drone_info['pilot_lon'] = get_float(message['System Message'].get('longitude', 0.0))

                else:
                    logger.error("Unexpected message format; expected dict or list.")
                    continue  # Skip this message

                # Enforce 'drone-' prefix once after parsing all IDs
                if 'id' in drone_info:
                    if not drone_info['id'].startswith('drone-'):
                        drone_info['id'] = f"drone-{drone_info['id']}"
                        logger.debug(f"Ensured drone id with prefix: {drone_info['id']}")
                    else:
                        logger.debug(f"Drone id already has prefix: {drone_info['id']}")

                    drone_id = drone_info['id']
                    if drone_id in drone_manager.drone_dict:
                        drone = drone_manager.drone_dict[drone_id]
                        drone.update(
                            mac=drone_info.get('mac', ""),
                            rssi=drone_info.get('rssi', 0.0),
                            lat=drone_info.get('lat', 0.0),
                            lon=drone_info.get('lon', 0.0),
                            speed=drone_info.get('speed', 0.0),
                            vspeed=drone_info.get('vspeed', 0.0),
                            alt=drone_info.get('alt', 0.0),
                            height=drone_info.get('height', 0.0),
                            pilot_lat=drone_info.get('pilot_lat', 0.0),
                            pilot_lon=drone_info.get('pilot_lon', 0.0),
                            description=drone_info.get('description', "")
                        )
                        logger.debug(f"Updated drone: {drone_id}")
                    else:
                        drone = Drone(
                            id=drone_info['id'],
                            lat=drone_info.get('lat', 0.0),
                            lon=drone_info.get('lon', 0.0),
                            speed=drone_info.get('speed', 0.0),
                            vspeed=drone_info.get('vspeed', 0.0),
                            alt=drone_info.get('alt', 0.0),
                            height=drone_info.get('height', 0.0),
                            pilot_lat=drone_info.get('pilot_lat', 0.0),
                            pilot_lon=drone_info.get('pilot_lon', 0.0),
                            description=drone_info.get('description', ""),
                            mac=drone_info.get('mac', ""),
                            rssi=drone_info.get('rssi', 0)
                        )
                        drone_manager.update_or_add_drone(drone_id, drone)
                        logger.debug(f"Added new drone: {drone_id}")
                else:
                    logger.warning("Drone ID not found in message. Skipping.")

            if status_socket and status_socket in socks and socks[status_socket] == zmq.POLLIN:
                logger.debug("Received a message on the status socket")
                status_message = status_socket.recv_json()
                # logger.debug(f"Received system status JSON: {status_message}")
                
                serial_number = status_message.get('serial_number', 'unknown')
                gps_data = status_message.get('gps_data', {})
                lat = get_float(gps_data.get('latitude', 0.0))
                lon = get_float(gps_data.get('longitude', 0.0))
                alt = get_float(gps_data.get('altitude', 0.0))

                system_stats = status_message.get('system_stats', {})
                ant_sdr_temps = status_message.get('ant_sdr_temps', {})
                pluto_temp = ant_sdr_temps.get('pluto_temp', 'N/A')
                zynq_temp  = ant_sdr_temps.get('zynq_temp',  'N/A')

                # Extract system statistics with defaults
                cpu_usage = get_float(system_stats.get('cpu_usage', 0.0))
                memory = system_stats.get('memory', {})
            time.sleep(5)
                print(f"Unexpected error: {e}")
            if debug:
        except Exception as e:

            time.sleep(5)
                print(f"ZMQ Error: {e}")
            if debug:
        except zmq.ZMQError as e:

            time.sleep(interval)

                socket.send_string(json_data)
            else:
                print(f"Debug Output:\n{json_data}")
            if debug:

            json_data = json.dumps(data, indent=4)
            }
                'ant_sdr_temps': get_pluto_temperatures(debug=debug)
                'system_stats': get_system_stats(),
                'serial_number': get_serial_number(debug=debug),
                'gps_data': get_gps_data(debug=debug),
                'timestamp': time.time(),
            data = {
        try:
    while True:

    socket = create_zmq_context(host, port) if not debug else None

    signal.signal(signal.SIGTERM, signal_handler)
                memory_available = get_float(memory.get('available', 0.0)) / (1024 * 1024)
                disk = system_stats.get('disk', {})
                disk_used = get_float(disk.get('used', 0.0)) / (1024 * 1024)
                temperature = get_float(system_stats.get('temperature', 0.0))
                uptime = get_float(system_stats.get('uptime', 0.0))

                if lat == 0.0 and lon == 0.0:
                    logger.warning(
                        "Latitude and longitude are missing or zero. "
                        "Proceeding with CoT message using [0.0, 0.0]."
                    )

                system_status = SystemStatus(
                    serial_number=serial_number,
                    lat=lat,
                    lon=lon,
                    alt=alt,
                    cpu_usage=cpu_usage,
                    memory_total=memory_total,
                    memory_available=memory_available,
                    disk_total=disk_total,
                    disk_used=disk_used,
                    temperature=temperature,
                    uptime=uptime,
                    pluto_temp=pluto_temp,
                    zynq_temp=zynq_temp 
                )

                cot_xml = system_status.to_cot_xml()

                # Sending CoT message via CotMessenger
                cot_messenger.send_cot(cot_xml)
                logger.info(f"Sent CoT message to TAK/multicast.")

            # Send drone updates via DroneManager
            drone_manager.send_updates()
    except Exception as e:
        logger.error(f"An error occurred in zmq_to_cot: {e}")
    except KeyboardInterrupt:
        signal_handler(None, None)

# Configuration and Execution
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ZMQ to CoT converter.")
    parser.add_argument("--config", type=str, help="Path to config file", default="config.ini")
    parser.add_argument("--zmq-host", help="ZMQ server host")
    parser.add_argument("--zmq-port", type=int, help="ZMQ server port for telemetry")
    parser.add_argument("--zmq-status-port", type=int, help="ZMQ server port for system status")
    parser.add_argument("--tak-host", type=str, help="TAK server hostname or IP address (optional)")
    parser.add_argument("--tak-port", type=int, help="TAK server port (optional)")
    parser.add_argument("--tak-protocol", type=str, choices=['TCP', 'UDP'], help="TAK server communication protocol (TCP or UDP)")
    parser.add_argument("--tak-tls-p12", type=str, help="Path to TAK server TLS PKCS#12 file (optional, for TCP)")
    parser.add_argument("--tak-tls-p12-pass", type=str, help="Password for TAK server TLS PKCS#12 file (optional, for TCP)")
    parser.add_argument("--tak-tls-skip-verify", action="store_true", help="(UNSAFE) Disable TLS server verification")
    parser.add_argument("--tak-multicast-addr", type=str, help="TAK multicast address (optional)")
    parser.add_argument("--tak-multicast-port", type=int, help="TAK multicast port (optional)")
    parser.add_argument("--enable-multicast", action="store_true", help="Enable sending to multicast address")
    parser.add_argument("--tak-multicast-interface", type=str, help="Multicast interface (IP or name) to use for sending multicast")
    parser.add_argument("--rate-limit", type=float, help="Rate limit for sending CoT messages (seconds)")
    parser.add_argument("--max-drones", type=int, help="Maximum number of drones to track simultaneously")
    parser.add_argument("--inactivity-timeout", type=float, help="Time in seconds before a drone is considered inactive")
    parser.add_argument("--enable-mesh", action="store_true", help="Enable Meshtastic mesh messaging")
    parser.add_argument("--mesh-device", type=str, help="Meshtastic device serial port or IP address")
    parser.add_argument("--mesh-channel", type=str, choices=['longfast', 'shortfast', 'longslow', 'shortslow'],
                       help="Meshtastic channel configuration")
    parser.add_argument("--mesh-psk", type=str, help="Pre-shared key for mesh encryption")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    # Add new Meshtastic arguments
    
    parser.add_argument('-d', '--debug', action='store_true', help='Print JSON to terminal for debugging')
    parser.add_argument('--interval', type=int, default=30, help='Update interval in seconds')
    parser.add_argument('--zmq_port', type=int, default=4225, help='ZMQ Port')
    parser.add_argument('--zmq_host', type=str, default='0.0.0.0', help='ZMQ Host')
    parser = argparse.ArgumentParser(description="WarDragon System Monitor")
    # Load config file if provided
    config_values = {}
    if args.config:
        config_values = load_config(args.config)

    setup_logging(args.debug)
    logger.info("Starting ZMQ to CoT converter with log level: %s", "DEBUG" if args.debug else "INFO")

    # Add to config dictionary
    config = {
        "zmq_host": args.zmq_host if args.zmq_host is not None else get_str(config_values.get("zmq_host", "127.0.0.1")),
        "zmq_port": args.zmq_port if args.zmq_port is not None else get_int(config_values.get("zmq_port"), 4224),
        "zmq_status_port": args.zmq_status_port if args.zmq_status_port is not None else get_int(config_values.get("zmq_status_port"), None),
        # Existing config items...
        "tak_tls_p12": args.tak_tls_p12 if args.tak_tls_p12 is not None else get_str(config_values.get("tak_tls_p12")),
        "tak_tls_p12_pass": args.tak_tls_p12_pass if args.tak_tls_p12_pass is not None else get_str(config_values.get("tak_tls_p12_pass")),
        "tak_tls_skip_verify": args.tak_tls_skip_verify if args.tak_tls_skip_verify else get_bool(config_values.get("tak_tls_skip_verify"), False),
        "tak_multicast_addr": args.tak_multicast_addr if args.tak_multicast_addr is not None else get_str(config_values.get("tak_multicast_addr")),
        "tak_multicast_port": args.tak_multicast_port if args.tak_multicast_port is not None else get_int(config_values.get("tak_multicast_port"), None),
        "enable_multicast": args.enable_multicast or get_bool(config_values.get("enable_multicast"), False),
        "rate_limit": args.rate_limit if args.rate_limit is not None else get_float(config_values.get("rate_limit", 1.0)),
        "max_drones": args.max_drones if args.max_drones is not None else get_int(config_values.get("max_drones", 30)),
        "inactivity_timeout": args.inactivity_timeout if args.inactivity_timeout is not None else get_float(config_values.get("inactivity_timeout", 60.0)),
        "enable_mesh": args.enable_mesh or get_bool(config_values.get("enable_mesh"), False),
        "mesh_device": args.mesh_device if args.mesh_device is not None else get_str(config_values.get("mesh_device")),
        "mesh_channel": args.mesh_channel if args.mesh_channel is not None else get_str(config_values.get("mesh_channel")),
        "mesh_psk": args.mesh_psk if args.mesh_psk is not None else get_str(config_values.get("mesh_psk")),
    }

    # Validate configuration
    try:
        validate_config(config)
    except ValueError as ve:
        logger.critical(f"Configuration Error: {ve}")
        sys.exit(1)

    # Setup TLS context only if tak_protocol is set (which implies tak_host and tak_port are provided)
    main(args.zmq_host, args.zmq_port, args.interval, args.debug)
    tak_tls_context = setup_tls_context(
        tak_tls_p12=config["tak_tls_p12"],
        tak_tls_p12_pass=config["tak_tls_p12_pass"],
        tak_tls_skip_verify=config["tak_tls_skip_verify"]
    ) if config["tak_protocol"] == 'TCP' and config["tak_tls_p12"] else None

    zmq_to_cot(
        zmq_host=config["zmq_host"],
        zmq_port=config["zmq_port"],
        zmq_status_port=config["zmq_status_port"],
        tak_host=config["tak_host"],
        tak_port=config["tak_port"],
        tak_tls_context=tak_tls_context,
        tak_protocol=config["tak_protocol"],
        multicast_address=config["tak_multicast_addr"],
        multicast_port=config["tak_multicast_port"],
        enable_multicast=config["enable_multicast"],
        rate_limit=config["rate_limit"],
        max_drones=config["max_drones"],
        inactivity_timeout=config["inactivity_timeout"],
