# main.py

import sys
import ssl
import socket
import signal
import logging
import argparse
import datetime
import time
import tempfile
import configparser
from collections import deque
from typing import Optional, Dict, Any
import struct
import atexit
import os

import zmq
from lxml import etree
import xml.sax.saxutils

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
    atexit.register(os.unlink, key_temp_path)
    atexit.register(os.unlink, cert_temp_path)
    atexit.register(os.unlink, ca_temp_path)

    try:
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

    return tls_context

def zmq_to_cot(zmq_host: str, zmq_port: int, zmq_status_port: Optional[int], tak_host: Optional[str] = None,
               tak_port: Optional[int] = None, tak_tls_context: Optional[ssl.SSLContext] = None,
               tak_protocol: Optional[str] = 'TCP', multicast_address: Optional[str] = None, multicast_port: Optional[int] = None,
               enable_multicast: bool = False, rate_limit: float = 1.0, max_drones: int = 30, inactivity_timeout: float = 60.0):
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
        enable_multicast=enable_multicast
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
                logger.debug(f"Received telemetry JSON: {message}")

                drone_info = {}
                for item in message:
                    if 'Basic ID' in item:
                        id_type = item['Basic ID'].get('id_type')
                        if id_type == 'Serial Number (ANSI/CTA-2063-A)' and 'id' not in drone_info:
                            drone_info['id'] = item['Basic ID'].get('id', 'unknown')
                            logger.debug(f"Parsed Serial Number ID: {drone_info['id']}")
                        elif id_type == 'CAA Assigned Registration ID' and 'id' not in drone_info:
                            drone_info['id'] = item['Basic ID'].get('id', 'unknown')
                            logger.debug(f"Parsed CAA Assigned ID: {drone_info['id']}")

                    if 'id' in drone_info:
                        if not drone_info['id'].startswith('drone-'):
                            drone_info['id'] = f"drone-{drone_info['id']}"
                        logger.debug(f"Ensured drone id with prefix: {drone_info['id']}")

                    if 'Location/Vector Message' in item:
                        drone_info['lat'] = get_float(item['Location/Vector Message'].get('latitude', 0.0))
                        drone_info['lon'] = get_float(item['Location/Vector Message'].get('longitude', 0.0))
                        drone_info['speed'] = get_float(item['Location/Vector Message'].get('speed', 0.0))
                        drone_info['vspeed'] = get_float(item['Location/Vector Message'].get('vert_speed', 0.0))
                        drone_info['alt'] = get_float(item['Location/Vector Message'].get('geodetic_altitude', 0.0))
                        drone_info['height'] = get_float(item['Location/Vector Message'].get('height_agl', 0.0))

                    if 'Self-ID Message' in item:
                        drone_info['description'] = item['Self-ID Message'].get('text', "")

                    if 'System Message' in item:
                        drone_info['pilot_lat'] = get_float(item['System Message'].get('latitude', 0.0))
                        drone_info['pilot_lon'] = get_float(item['System Message'].get('longitude', 0.0))

                if 'id' in drone_info:
                    drone_id = drone_info['id']
                    if drone_id in drone_manager.drone_dict:
                        drone = drone_manager.drone_dict[drone_id]
                        drone.update(
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
                            description=drone_info.get('description', "")
                        )
                        drone_manager.update_or_add_drone(drone_id, drone)
                        logger.debug(f"Added new drone: {drone_id}")

            if status_socket and status_socket in socks and socks[status_socket] == zmq.POLLIN:
                logger.debug("Received a message on the status socket")
                status_message = status_socket.recv_json()
                logger.debug(f"Received system status JSON: {status_message}")

                serial_number = status_message.get('serial_number', 'unknown')
                gps_data = status_message.get('gps_data', {})
                lat = get_float(gps_data.get('latitude', 0.0))
                lon = get_float(gps_data.get('longitude', 0.0))
                alt = get_float(gps_data.get('altitude', 0.0))

                system_stats = status_message.get('system_stats', {})

                # Extract system statistics with defaults
                cpu_usage = get_float(system_stats.get('cpu_usage', 0.0))
                memory = system_stats.get('memory', {})
                memory_total = get_float(memory.get('total', 0.0)) / (1024 * 1024)  # Convert bytes to MB
                memory_available = get_float(memory.get('available', 0.0)) / (1024 * 1024)
                disk = system_stats.get('disk', {})
                disk_total = get_float(disk.get('total', 0.0)) / (1024 * 1024)  # Convert bytes to MB
                disk_used = get_float(disk.get('used', 0.0)) / (1024 * 1024)
                temperature = get_float(system_stats.get('temperature', 0.0))
                uptime = get_float(system_stats.get('uptime', 0.0))

                if lat == 0.0 and lon == 0.0:
                    logger.warning("Latitude and longitude are missing or zero. Skipping CoT message.")
                    continue  # Skip this iteration

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
                    uptime=uptime
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
    parser.add_argument("--rate-limit", type=float, help="Rate limit for sending CoT messages (seconds)")
    parser.add_argument("--max-drones", type=int, help="Maximum number of drones to track simultaneously")
    parser.add_argument("--inactivity-timeout", type=float, help="Time in seconds before a drone is considered inactive")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    # Load config file if provided
    config_values = {}
    if args.config:
        config_values = load_config(args.config)

    setup_logging(args.debug)
    logger.info("Starting ZMQ to CoT converter with log level: %s", "DEBUG" if args.debug else "INFO")

    # Retrieve 'tak_host' and 'tak_port' with precedence
    tak_host = args.tak_host if args.tak_host is not None else get_str(config_values.get("tak_host"))
    tak_port = args.tak_port if args.tak_port is not None else get_int(config_values.get("tak_port"), None)

    if tak_host and tak_port:
        # Fetch the raw protocol value from command-line or config
        tak_protocol_raw = args.tak_protocol if args.tak_protocol is not None else config_values.get("tak_protocol")
        # Use get_str to sanitize the input, defaulting to "TCP" if necessary
        tak_protocol_sanitized = get_str(tak_protocol_raw, "TCP")
        # Convert to uppercase
        tak_protocol = tak_protocol_sanitized.upper()
    else:
        # If TAK host and port are not provided, set tak_protocol to None
        tak_protocol = None
        logger.info("TAK host and port not provided. 'tak_protocol' will be ignored.")

    # Assign configuration values, giving precedence to command-line arguments
    config = {
        "zmq_host": args.zmq_host if args.zmq_host is not None else get_str(config_values.get("zmq_host", "127.0.0.1")),
        "zmq_port": args.zmq_port if args.zmq_port is not None else get_int(config_values.get("zmq_port"), 4224),
        "zmq_status_port": args.zmq_status_port if args.zmq_status_port is not None else get_int(config_values.get("zmq_status_port"), None),
        "tak_host": tak_host,
        "tak_port": tak_port,
        "tak_protocol": tak_protocol,
        "tak_tls_p12": args.tak_tls_p12 if args.tak_tls_p12 is not None else get_str(config_values.get("tak_tls_p12")),
        "tak_tls_p12_pass": args.tak_tls_p12_pass if args.tak_tls_p12_pass is not None else get_str(config_values.get("tak_tls_p12_pass")),
        "tak_tls_skip_verify": args.tak_tls_skip_verify if args.tak_tls_skip_verify else get_bool(config_values.get("tak_tls_skip_verify"), False),
        "tak_multicast_addr": args.tak_multicast_addr if args.tak_multicast_addr is not None else get_str(config_values.get("tak_multicast_addr")),
        "tak_multicast_port": args.tak_multicast_port if args.tak_multicast_port is not None else get_int(config_values.get("tak_multicast_port"), None),
        "enable_multicast": args.enable_multicast or get_bool(config_values.get("enable_multicast"), False),
        "rate_limit": args.rate_limit if args.rate_limit is not None else get_float(config_values.get("rate_limit", 1.0)),
        "max_drones": args.max_drones if args.max_drones is not None else get_int(config_values.get("max_drones", 30)),
        "inactivity_timeout": args.inactivity_timeout if args.inactivity_timeout is not None else get_float(config_values.get("inactivity_timeout", 60.0)),
    }

    # Validate configuration
    try:
        validate_config(config)
    except ValueError as ve:
        logger.critical(f"Configuration Error: {ve}")
        sys.exit(1)

    # Setup TLS context only if tak_protocol is set (which implies tak_host and tak_port are provided)
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
        inactivity_timeout=config["inactivity_timeout"]
    )
