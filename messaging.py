# messaging.py

import socket
import struct
import logging
import time
from typing import Optional
from tak_client import TAKClient
from tak_udp_client import TAKUDPClient

logger = logging.getLogger(__name__)

def send_to_tak_udp_multicast(cot_xml: bytes, multicast_address: str, multicast_port: int):
    """Sends a CoT XML message to a multicast address via UDP."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.2)
        ttl = struct.pack('b', 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
        sock.sendto(cot_xml, (multicast_address, multicast_port))
        sock.close()
        logger.debug(f"Sent CoT message via multicast to {multicast_address}:{multicast_port}")
    except Exception as e:
        logger.error(f"Error sending CoT message via multicast: {e}")

class CotMessenger:
    """Handles sending CoT messages to TAK servers and multicast addresses."""
    
    def __init__(self, tak_client: Optional[TAKClient] = None, tak_udp_client: Optional[TAKUDPClient] = None,
                 multicast_address: Optional[str] = None, multicast_port: Optional[int] = None,
                 enable_multicast: bool = False):
        """
        Initializes the CotMessenger.
        
        :param tak_client: Instance of TAKClient for TCP/TLS communication.
        :param tak_udp_client: Instance of TAKUDPClient for UDP communication.
        :param multicast_address: Multicast address to send CoT messages.
        :param multicast_port: Multicast port to send CoT messages.
        :param enable_multicast: Flag to enable multicast sending.
        """
        self.tak_client = tak_client
        self.tak_udp_client = tak_udp_client
        self.multicast_address = multicast_address
        self.multicast_port = multicast_port
        self.enable_multicast = enable_multicast
        self.multicast_socket = None

        if self.enable_multicast and self.multicast_address and self.multicast_port:
            try:
                self.multicast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                ttl = struct.pack('b', 1)
                self.multicast_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
                logger.debug(f"Initialized persistent multicast socket for {self.multicast_address}:{self.multicast_port}")
            except Exception as e:
                logger.error(f"Failed to initialize multicast socket: {e}")

    def send_cot(self, cot_xml: bytes, retry_count: int = 3, retry_delay: float = 1.0):
        """
        Sends a CoT message to TAK servers and multicast addresses with retry logic.
        
        :param cot_xml: The CoT XML message in bytes.
        :param retry_count: Number of retry attempts for sending.
        :param retry_delay: Delay between retries in seconds.
        """
        # Sending to TAK server via TCP/TLS
        if self.tak_client:
            for attempt in range(1, retry_count + 1):
                try:
                    self.tak_client.send(cot_xml)
                    logger.info(f"Sent CoT message to TAK server via TCP/TLS at {self.tak_client.host}:{self.tak_client.port}")
                    break
                except Exception as e:
                    logger.error(f"Attempt {attempt}: Failed to send CoT message via TCP/TLS: {e}")
                    if attempt < retry_count:
                        time.sleep(retry_delay)
                    else:
                        logger.critical("Exceeded maximum retries for sending CoT message via TCP/TLS.")

        elif self.tak_udp_client:
            for attempt in range(1, retry_count + 1):
                try:
                    self.tak_udp_client.send(cot_xml)
                    logger.info(f"Sent CoT message to TAK server via UDP at {self.tak_udp_client.host}:{self.tak_udp_client.port}")
                    break
                except Exception as e:
                    logger.error(f"Attempt {attempt}: Failed to send CoT message via UDP: {e}")
                    if attempt < retry_count:
                        time.sleep(retry_delay)
                    else:
                        logger.critical("Exceeded maximum retries for sending CoT message via UDP.")
        else:
            logger.debug("No TAK client configured. Skipping sending CoT message to TAK server.")

        # Sending to multicast address
        if self.enable_multicast and self.multicast_socket:
            for attempt in range(1, retry_count + 1):
                try:
                    self.multicast_socket.sendto(cot_xml, (self.multicast_address, self.multicast_port))
                    logger.info(f"Sent CoT message to multicast address {self.multicast_address}:{self.multicast_port}")
                    break
                except Exception as e:
                    logger.error(f"Attempt {attempt}: Failed to send CoT message via multicast: {e}")
                    if attempt < retry_count:
                        time.sleep(retry_delay)
                    else:
                        logger.critical("Exceeded maximum retries for sending CoT message via multicast.")
        else:
            logger.debug("Multicast is not enabled or multicast socket not initialized. Skipping sending CoT message to multicast.")

    def close(self):
        """Closes persistent multicast sockets if initialized."""
        if self.multicast_socket:
            try:
                self.multicast_socket.close()
                logger.debug("Closed multicast socket.")
            except Exception as e:
                logger.error(f"Error closing multicast socket: {e}")
