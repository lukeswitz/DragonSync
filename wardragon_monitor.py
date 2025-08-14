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
import psutil
import subprocess
import time
import zmq
import signal
import sys
import uuid
import os
import configparser  # gps.ini support

# --- gpsd import (optional) ---------------------------------------------------
# Allow running without gpsd if using static GPS from gps.ini or CLI.
try:
    from gps import gps as gpsd_class, WATCH_ENABLE, WATCH_NEWSTYLE
    GPSD_AVAILABLE = True
except Exception:
    gpsd_class = None
    WATCH_ENABLE = 0
    WATCH_NEWSTYLE = 0
    GPSD_AVAILABLE = False
# ------------------------------------------------------------------------------

STATIC_GPS = {'lat': None, 'lon': None, 'alt': None}

def load_gps_ini(path: str | None = None, debug: bool = False):
    """Read static GPS settings from a gps.ini if present and enabled.

    Search order:
      1) Explicit --gps-ini path (if provided)
      2) /etc/gps.ini
      3) ./gps.ini (next to this script)

    Returns dict {'lat': float, 'lon': float, 'alt': float|None} or None.
    """
    candidates = []
    if path:
        candidates.append(path)
    candidates.append('/etc/gps.ini')
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gps.ini'))

    gps_ini = next((p for p in candidates if os.path.isfile(p)), None)
    if not gps_ini:
        if debug:
            print("[gps.ini] No gps.ini file found in provided path, /etc, or script directory.")
        return None

    if debug:
        print(f"[gps.ini] Using file: {gps_ini}")

    config = configparser.ConfigParser()
    try:
        with open(gps_ini, 'r') as f:
            config.read_file(f)
    except Exception as e:
        if debug:
            print(f"[gps.ini] Failed to read {gps_ini}: {e}")
        return None

    section = 'gps'
    if section not in config:
        if debug:
            print(f"[gps.ini] Missing section [{section}] in {gps_ini}")
        return None

    try:
        use_static = config.get(section, 'use_static_gps', fallback='false').strip().lower() == 'true'
        if not use_static:
            if debug:
                print("[gps.ini] use_static_gps is not true; ignoring static GPS.")
            return None

        lat = config.getfloat(section, 'static_lat', fallback=None)
        lon = config.getfloat(section, 'static_lon', fallback=None)
        alt = config.getfloat(section, 'static_alt', fallback=None)

        if lat is None or lon is None:
            if debug:
                print("[gps.ini] static_lat/static_lon missing; cannot use static GPS.")
            return None

        if debug:
            print(f"[gps.ini] Loaded static GPS: lat={lat}, lon={lon}, alt={alt}")
        return {'lat': lat, 'lon': lon, 'alt': alt}
    except Exception as e:
        if debug:
            print(f"[gps.ini] Error parsing values: {e}")
        return None


def get_gps_data(debug=False):
    """Retrieve GPS data from gpsd or use static values if provided."""
    if STATIC_GPS['lat'] is not None and STATIC_GPS['lon'] is not None:
        if debug:
            print(f"[gps] Using static GPS: {STATIC_GPS}")
        return {
            'latitude': STATIC_GPS['lat'],
            'longitude': STATIC_GPS['lon'],
            'altitude': STATIC_GPS['alt'] if STATIC_GPS['alt'] is not None else 'N/A',
            'speed': 'N/A',
            'track': 'N/A'
        }

    if not GPSD_AVAILABLE:
        if debug:
            print("[gps] gpsd module not available and no static GPS set.")
        return {'latitude': 'N/A', 'longitude': 'N/A', 'altitude': 'N/A', 'speed': 'N/A', 'track': 'N/A'}

    try:
        gpsd = gpsd_class(mode=WATCH_ENABLE | WATCH_NEWSTYLE)

        if debug:
            print("[gps] Waiting for GPS data...")

        report = gpsd.next()
        while report.get('class') != 'TPV':
            report = gpsd.next()

        gps_info = {
            'latitude': getattr(report, 'lat', 'N/A'),
            'longitude': getattr(report, 'lon', 'N/A'),
            'altitude': getattr(report, 'alt', 'N/A'),
            'speed': getattr(report, 'speed', 'N/A'),
            'track': getattr(report, 'track', 'N/A')
        }
        if debug:
            print(f"[gps] Received GPS data: {gps_info}")
        return gps_info

    except KeyError as e:
        if debug:
            print(f"[gps] Missing GPS data key: {e}")
    except StopIteration:
        if debug:
            print("[gps] No GPS data available.")
    except Exception as e:
        if debug:
            print(f"[gps] Error connecting to gpsd: {e}")

    return {'latitude': 'N/A', 'longitude': 'N/A', 'altitude': 'N/A', 'speed': 'N/A', 'track': 'N/A'}


def get_serial_number(debug=False):
    """Retrieve the system's serial number or MAC address as a unique identifier."""
    invalid_serials = [
        'N/A', 'Default string', 'To be filled by O.E.M.', 'None',
        'Not Specified', 'Unknown', ''
    ]
    try:
        result = subprocess.run(
            ['sudo', 'dmidecode', '-t', 'system'],
            capture_output=True, text=True, check=True
        )
        output = result.stdout
        serial_number = None
        for line in output.split('\n'):
            if 'Serial Number:' in line:
                serial_number = line.split(':')[-1].strip()
                break

        if serial_number and serial_number not in invalid_serials:
            if debug:
                print(f"[uid] Using serial number: {serial_number}")
            return serial_number

    except subprocess.CalledProcessError as e:
        if debug:
            print(f"[uid] Error retrieving serial number: {e}")
    except Exception as e:
        if debug:
            print(f"[uid] Unexpected error retrieving serial number: {e}")

    # If serial number is invalid or not found, try to get MAC address
    try:
        mac_address = None
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                # psutil.AF_LINK on BSD/Darwin, socket.AF_PACKET on Linux; this keeps your original behavior
                if getattr(psutil, "AF_LINK", None) and addr.family == psutil.AF_LINK:
                    if interface.startswith(('eth', 'en', 'wlan')):
                        mac_address = addr.address.replace(':', '').lower()
                        if mac_address and mac_address != '000000000000':
                            if debug:
                                print(f"[uid] Using MAC from {interface} as UID: {mac_address}")
                            return mac_address
        # If no MAC address found, generate UUID and store it
        uid_file = '/var/tmp/system_uid.txt'
        if os.path.exists(uid_file):
            with open(uid_file, 'r') as f:
                saved_uuid = f.read().strip()
                if debug:
                    print(f"[uid] Using saved UUID: {saved_uuid}")
                return saved_uuid
        else:
            generated_uuid = str(uuid.uuid4())
            with open(uid_file, 'w') as f:
                f.write(generated_uuid)
            if debug:
                print(f"[uid] No serial or MAC. Generated & saved UUID: {generated_uuid}")
            return generated_uuid
    except Exception as e:
        if debug:
            print(f"[uid] Error retrieving MAC address: {e}")
        # Generate UUID and store it
        uid_file = '/var/tmp/system_uid.txt'
        if os.path.exists(uid_file):
            with open(uid_file, 'r') as f:
                saved_uuid = f.read().strip()
                if debug:
                    print(f"[uid] Using saved UUID: {saved_uuid}")
                return saved_uuid
        else:
            generated_uuid = str(uuid.uuid4())
            with open(uid_file, 'w') as f:
                f.write(generated_uuid)
            if debug:
                print(f"[uid] Generated and saved UUID: {generated_uuid}")
            return generated_uuid


def get_cpu_temperature(debug=False):
    """Retrieve the CPU temperature using the 'sensors' command."""
    try:
        result = subprocess.run(['sensors'], capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if 'Package id 0:' in line:
                temp_str = line.split('+')[1].split('°')[0].strip()
                return float(temp_str)
    except Exception as e:
        if debug:
            print(f"[temp] Error retrieving CPU temperature: {e}")
    return 'N/A'


def get_system_stats():
    """Gather system statistics using psutil."""
    return {
        'cpu_usage': psutil.cpu_percent(),
        'memory': psutil.virtual_memory()._asdict(),
        'disk': psutil.disk_usage('/')._asdict(),
        'temperature': get_cpu_temperature(),
        'uptime': time.time() - psutil.boot_time()
    }


# ------------------------------------------------------------------------
# Retrieve AntSDR (Pluto) temperatures using iio_attr (optional)
# Inspired by and code used from https://github.com/analogdevicesinc/plutosdr_scripts/blob/master/pluto_temp.sh
# ------------------------------------------------------------------------
def get_pluto_temperatures(debug=False):
    """
    Attempt to gather the Pluto (RF chip) and Zynq chip temperatures
    using iio_attr (and iio_info) commands.

    Returns:
      { "pluto_temp": <float|'N/A'>, "zynq_temp": <float|'N/A'> }
    """
    temps = {
        'pluto_temp': 'N/A',
        'zynq_temp': 'N/A'
    }

    def tool_exists(tool):
        return subprocess.run(['which', tool], capture_output=True).returncode == 0

    if not (tool_exists('iio_info') and tool_exists('iio_attr')):
        if debug:
            print("[pluto] iio_info or iio_attr not found. Can't retrieve Pluto temps.")
        return temps

    try:
        uri = None
        result = subprocess.run(['iio_info', '-s'], capture_output=True, text=True, check=True)
        for line in result.stdout.strip().splitlines():
            if 'PLUTO' in line.upper():
                parts = line.split()
                for p in parts:
                    if p.startswith('[') and p.endswith(']'):
                        uri = p.strip('[]')
                        break
                break

        if not uri:
            uri = "ip:192.168.2.1"
            if debug:
                print("[pluto] No USB device found, falling back to ip:192.168.2.1")

        cmd_pluto = ['iio_attr', '-u', uri, '-c', 'ad9361-phy', 'temp0', 'input']
        pluto_raw_out = subprocess.run(cmd_pluto, capture_output=True, text=True, check=True)
        pluto_raw_str = pluto_raw_out.stdout.strip().split()[-1]
        pluto_temp_c = float(pluto_raw_str) / 1000.0

        cmd_xadc_raw    = ['iio_attr', '-u', uri, '-c', 'xadc', 'temp0', 'raw']
        cmd_xadc_offset = ['iio_attr', '-u', uri, '-c', 'xadc', 'temp0', 'offset']
        cmd_xadc_scale  = ['iio_attr', '-u', uri, '-c', 'xadc', 'temp0', 'scale']

        raw    = float(subprocess.run(cmd_xadc_raw,    capture_output=True, text=True, check=True).stdout.strip().split()[-1])
        offset = float(subprocess.run(cmd_xadc_offset, capture_output=True, text=True, check=True).stdout.strip().split()[-1])
        scale  = float(subprocess.run(cmd_xadc_scale,  capture_output=True, text=True, check=True).stdout.strip().split()[-1])

        zynq_temp_c = (raw + offset) * scale / 1000.0

        temps['pluto_temp'] = round(pluto_temp_c, 1)
        temps['zynq_temp']  = round(zynq_temp_c, 1)

        if debug:
            print(f"[pluto] Temps -> Pluto: {temps['pluto_temp']} °C, Zynq: {temps['zynq_temp']} °C")

    except subprocess.CalledProcessError as e:
        if debug:
            print(f"[pluto] iio_* returned non-zero exit code: {e}")
    except Exception as e:
        if debug:
            print(f"[pluto] Unexpected error: {e}")

    return temps


def create_zmq_context(host, port):
    """Create and bind a ZMQ PUB socket."""
    context = zmq.Context()
    sock = context.socket(zmq.PUB)
    try:
        sock.bind(f"tcp://{host}:{port}")
    except zmq.ZMQError as e:
        print(f"Error binding ZMQ socket: {e}")
        sys.exit(1)
    return sock


def signal_handler(sig, frame):
    """Handle SIGINT/SIGTERM signals for graceful exit."""
    print("Exiting... Closing resources.")
    sys.exit(0)


def main(host, port, interval, debug, static_lat=None, static_lon=None, static_alt=None, gps_ini_path: str | None = None):
    """Main function to gather data and send it over ZMQ."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Determine static GPS settings
    # Priority: CLI flags > gps.ini > none
    global STATIC_GPS
    if static_lat is not None and static_lon is not None:
        STATIC_GPS['lat'] = static_lat
        STATIC_GPS['lon'] = static_lon
        STATIC_GPS['alt'] = static_alt
        if debug:
            print(f"[gps] Static coords from CLI: {STATIC_GPS}")
    else:
        ini_vals = load_gps_ini(gps_ini_path, debug=debug)
        if ini_vals and ini_vals['lat'] is not None and ini_vals['lon'] is not None:
            STATIC_GPS['lat'] = ini_vals['lat']
            STATIC_GPS['lon'] = ini_vals['lon']
            STATIC_GPS['alt'] = ini_vals.get('alt')
        elif debug:
            print("[gps] No static GPS from CLI or gps.ini; falling back to gpsd/NMEA if available.")

    sock = create_zmq_context(host, port) if not debug else None

    while True:
        try:
            data = {
                'timestamp': time.time(),
                'gps_data': get_gps_data(debug=debug),
                'serial_number': get_serial_number(debug=debug),
                'system_stats': get_system_stats(),
                'ant_sdr_temps': get_pluto_temperatures(debug=debug)
            }
            json_data = json.dumps(data, indent=4)

            if debug:
                print(f"Debug Output:\n{json_data}")
            else:
                # Publish over ZMQ
                sock.send_string(json_data)

            time.sleep(interval)

        except zmq.ZMQError as e:
            if debug:
                print(f"ZMQ Error: {e}")
            time.sleep(5)  # Backoff before retrying

        except Exception as e:
            if debug:
                print(f"Unexpected error: {e}")
            time.sleep(5)  # Backoff before retrying


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WarDragon System Monitor")
    parser.add_argument('--zmq_host', type=str, default='0.0.0.0', help='ZMQ Host')
    parser.add_argument('--zmq_port', type=int, default=4225, help='ZMQ Port')
    parser.add_argument('--interval', type=int, default=30, help='Update interval in seconds')
    parser.add_argument('-d', '--debug', action='store_true', help='Print JSON to terminal for debugging')
    parser.add_argument('--static-lat', type=float, help='Static latitude for fixed position (overrides GPS)')
    parser.add_argument('--static-lon', type=float, help='Static longitude for fixed position (overrides GPS)')
    parser.add_argument('--static-alt', type=float, help='Static altitude for fixed position (optional)')
    parser.add_argument('--gps-ini', type=str, help='Path to gps.ini (optional). If omitted, searches /etc and script dir.')

    args = parser.parse_args()
    main(
        args.zmq_host,
        args.zmq_port,
        args.interval,
        args.debug,
        static_lat=args.static_lat,
        static_lon=args.static_lon,
        static_alt=args.static_alt,
        gps_ini_path=args.gps_ini
    )
