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


import configparser
import logging
import sys

logger = logging.getLogger(__name__)

def load_config(file_path: str) -> dict:
    """Load configurations from a file."""
    config = configparser.ConfigParser()
    config.read(file_path)
    config_dict = {}
    if 'SETTINGS' in config:
        config_dict.update(config['SETTINGS'])
    return config_dict

def validate_config(config: dict):
    """Validates the configuration parameters."""
    required_keys = ['zmq_host', 'zmq_port']
    for key in required_keys:
        if key not in config:
            logger.critical(f"Missing required configuration key: {key}")
            sys.exit(1)

    # Validate ZMQ port
    zmq_port = get_int(config.get('zmq_port'))
    if not (1 <= zmq_port <= 65535):
        logger.critical(f"Invalid ZMQ port: {zmq_port}. Must be between 1 and 65535.")
        sys.exit(1)

    # Validate TAK port if provided
    tak_port = get_int(config.get('tak_port'))
    if tak_port is not None and not (1 <= tak_port <= 65535):
        logger.critical(f"Invalid TAK port: {tak_port}. Must be between 1 and 65535.")
        sys.exit(1)

    # Validate TAK protocol
    tak_protocol = config.get('tak_protocol', 'TCP').upper()
    if tak_protocol not in ('TCP', 'UDP'):
        logger.critical(f"Invalid TAK protocol: {tak_protocol}. Must be either 'TCP' or 'UDP'.")
        sys.exit(1)
    config['tak_protocol'] = tak_protocol  # Normalize value

    # Validate multicast address if enable_multicast is True
    enable_multicast = get_bool(config.get('enable_multicast', False))
    if enable_multicast:
        multicast_address = config.get('tak_multicast_addr')
        multicast_port = get_int(config.get('tak_multicast_port'))
        if not multicast_address or not multicast_port:
            logger.critical("Multicast is enabled but multicast_address or multicast_port is missing.")
            sys.exit(1)

    # Additional Validations Based on TAK Protocol
    if config['tak_protocol'] == 'TCP':
        tak_tls_p12 = config.get('tak_tls_p12')
        tak_tls_p12_pass = config.get('tak_tls_p12_pass')
        if not tak_tls_p12 or not tak_tls_p12_pass:
            logger.critical("TAK protocol is set to TCP but tak_tls_p12 or tak_tls_p12_pass is missing.")
            sys.exit(1)
    elif config['tak_protocol'] == 'UDP':
        # For UDP, tak_tls_p12 and tak_tls_p12_pass should not be set
        if config.get('tak_tls_p12') or config.get('tak_tls_p12_pass'):
            logger.warning("TAK protocol is set to UDP. tak_tls_p12 and tak_tls_p12_pass will be ignored.")

def get_str(value):
    """Returns the stripped string if not empty, else None."""
    if value is not None:
        value = value.strip()
        if value:
            return value
    return None

def get_int(value, default=None):
    """Safely converts a value to an integer, returning default if conversion fails."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def get_float(value, default=None):
    """Safely converts a value to a float, returning default if conversion fails."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def get_bool(value, default=False):
    """Safely converts a value to a boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('true', 'yes', '1')
    return default
