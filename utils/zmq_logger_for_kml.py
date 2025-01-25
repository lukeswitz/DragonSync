#!/usr/bin/env python3
import argparse
import logging
import time
import zmq
import csv
from datetime import datetime

def get_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def parse_drone_message(message, logger):
    """
    Given a single parsed JSON message (dict or list), extract:
      - drone_id
      - lat, lon, alt, speed
      - RSSI, mac, description
      - pilot lat/lon (optional)
    Returns a dict with these fields or None if missing critical info.
    """
    drone_info = {}

    # -----------------------
    # Handle "list" format
    # -----------------------
    if isinstance(message, list):
        for item in message:
            if not isinstance(item, dict):
                logger.error("Unexpected item type in message list; expected dict. Skipping.")
                continue
            
            if 'MAC' in item:
                drone_info['mac'] = item['MAC']
            if 'RSSI' in item:
                drone_info['rssi'] = item['RSSI']

            if 'Basic ID' in item:
                id_type = item['Basic ID'].get('id_type')
                drone_info['mac'] = item['Basic ID'].get('MAC', drone_info.get('mac', ''))
                drone_info['rssi'] = item['Basic ID'].get('RSSI', drone_info.get('rssi', 0.0))
                if id_type == 'Serial Number (ANSI/CTA-2063-A)' and 'id' not in drone_info:
                    drone_info['id'] = item['Basic ID'].get('id', 'unknown')
                elif id_type == 'CAA Assigned Registration ID' and 'id' not in drone_info:
                    drone_info['id'] = item['Basic ID'].get('id', 'unknown')

            if 'Location/Vector Message' in item:
                drone_info['lat']    = get_float(item['Location/Vector Message'].get('latitude', 0.0))
                drone_info['lon']    = get_float(item['Location/Vector Message'].get('longitude', 0.0))
                drone_info['speed']  = get_float(item['Location/Vector Message'].get('speed', 0.0))
                drone_info['vspeed'] = get_float(item['Location/Vector Message'].get('vert_speed', 0.0))
                drone_info['alt']    = get_float(item['Location/Vector Message'].get('geodetic_altitude', 0.0))
                drone_info['height'] = get_float(item['Location/Vector Message'].get('height_agl', 0.0))

            if 'Self-ID Message' in item:
                drone_info['description'] = item['Self-ID Message'].get('text', "")

            if 'System Message' in item:
                drone_info['pilot_lat'] = get_float(item['System Message'].get('latitude', 0.0))
                drone_info['pilot_lon'] = get_float(item['System Message'].get('longitude', 0.0))

    # -----------------------
    # Handle "dict" format
    # -----------------------
    elif isinstance(message, dict):
        # Example of raw fields that might appear
        if "AUX_ADV_IND" in message:
            if "rssi" in message["AUX_ADV_IND"]:
                drone_info['rssi'] = message["AUX_ADV_IND"]["rssi"]
            if "aext" in message and "AdvA" in message["aext"]:
                mac = message["aext"]["AdvA"].split()[0]  # Extract MAC before " (Public)" if it exists
                drone_info['mac'] = mac

        if 'Basic ID' in message:
            id_type = message['Basic ID'].get('id_type')
            drone_info['mac'] = message['Basic ID'].get('MAC', drone_info.get('mac', ''))
            drone_info['rssi'] = message['Basic ID'].get('RSSI', drone_info.get('rssi', 0.0))
            if id_type == 'Serial Number (ANSI/CTA-2063-A)' and 'id' not in drone_info:
                drone_info['id'] = message['Basic ID'].get('id', 'unknown')
            elif id_type == 'CAA Assigned Registration ID' and 'id' not in drone_info:
                drone_info['id'] = message['Basic ID'].get('id', 'unknown')

        if 'Location/Vector Message' in message:
            drone_info['lat']    = get_float(message['Location/Vector Message'].get('latitude', 0.0))
            drone_info['lon']    = get_float(message['Location/Vector Message'].get('longitude', 0.0))
            drone_info['speed']  = get_float(message['Location/Vector Message'].get('speed', 0.0))
            drone_info['vspeed'] = get_float(message['Location/Vector Message'].get('vert_speed', 0.0))
            drone_info['alt']    = get_float(message['Location/Vector Message'].get('geodetic_altitude', 0.0))
            drone_info['height'] = get_float(message['Location/Vector Message'].get('height_agl', 0.0))

        if 'Self-ID Message' in message:
            drone_info['description'] = message['Self-ID Message'].get('text', "")

        if 'System Message' in message:
            drone_info['pilot_lat'] = get_float(message['System Message'].get('latitude', 0.0))
            drone_info['pilot_lon'] = get_float(message['System Message'].get('longitude', 0.0))

    else:
        logger.error("Unexpected message format; expected dict or list.")
        return None  # Cannot parse

    # -----------
    # Final fix-ups
    # -----------
    # Enforce 'drone-' prefix on the ID
    if 'id' not in drone_info:
        # If there's absolutely no ID, it's up to you if you skip it or store it with a placeholder
        logger.warning("No drone ID found in message. Skipping.")
        return None

    if not drone_info['id'].startswith('drone-'):
        drone_info['id'] = f"drone-{drone_info['id']}"

    # Provide default values
    drone_info.setdefault('lat', 0.0)
    drone_info.setdefault('lon', 0.0)
    drone_info.setdefault('alt', 0.0)
    drone_info.setdefault('speed', 0.0)
    drone_info.setdefault('rssi', 0.0)
    drone_info.setdefault('description', "")
    drone_info.setdefault('pilot_lat', 0.0)
    drone_info.setdefault('pilot_lon', 0.0)
    drone_info.setdefault('mac', "")

    return drone_info


def main():
    parser = argparse.ArgumentParser(description="ZMQ logger to record drone data for future KML generation.")
    parser.add_argument("--zmq-host", default="127.0.0.1", help="ZMQ server host")
    parser.add_argument("--zmq-port", type=int, default=4224, help="ZMQ server port")
    parser.add_argument("--output-csv", default="drone_log.csv", 
                        help="Path to CSV file where parsed drone data is appended")
    parser.add_argument("--flush-interval", type=float, default=5.0, 
                        help="Flush CSV buffer every X seconds")
    parser.add_argument("--debug", action="store_true", help="Enable debug-level logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    logger.info(f"Connecting to ZMQ at tcp://{args.zmq_host}:{args.zmq_port}")

    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://{args.zmq_host}:{args.zmq_port}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")  # Subscribe to all messages

    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)

    # Prepare CSV
    csv_file = open(args.output_csv, 'a', newline='')
    csv_writer = csv.writer(csv_file)
    # If the file is empty, write a header row
    if csv_file.tell() == 0:
        csv_writer.writerow([
            "timestamp",
            "drone_id",
            "lat",
            "lon",
            "alt",
            "speed",
            "rssi",
            "mac",
            "description",
            "pilot_lat",
            "pilot_lon"
        ])

    message_buffer = []
    last_flush_time = time.time()

    try:
        while True:
            socks = dict(poller.poll(timeout=1000))
            if socket in socks and socks[socket] == zmq.POLLIN:
                raw = socket.recv_json()
                parsed = parse_drone_message(raw, logger)
                if parsed is not None:
                    # Build a row for CSV
                    row = [
                        datetime.utcnow().isoformat(),
                        parsed["id"],
                        parsed["lat"],
                        parsed["lon"],
                        parsed["alt"],
                        parsed["speed"],
                        parsed["rssi"],
                        parsed["mac"],
                        parsed["description"],
                        parsed["pilot_lat"],
                        parsed["pilot_lon"]
                    ]
                    message_buffer.append(row)

            # Flush buffer every X seconds
            now = time.time()
            if (now - last_flush_time) >= args.flush_interval and message_buffer:
                logger.debug(f"Flushing {len(message_buffer)} messages to CSV.")
                csv_writer.writerows(message_buffer)
                csv_file.flush()
                message_buffer.clear()
                last_flush_time = now

    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        # Final flush
        if message_buffer:
            csv_writer.writerows(message_buffer)
        csv_file.flush()
        csv_file.close()

        socket.close()
        context.term()

if __name__ == "__main__":
    main()
