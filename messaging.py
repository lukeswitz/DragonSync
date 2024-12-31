"""
MIT License

Copyright (c) 2024 cemaxecuter

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import socket
import struct
import logging
import time
from typing import Optional
from tak_client import TAKClient
from tak_udp_client import TAKUDPClient

logger = logging.getLogger(__name__)

try:
    import netifaces
except ImportError:
    logger.warning(
        "`netifaces` module not found. Interface name resolution may not be available."
    )
    netifaces = None


def resolve_interface_to_ip(interface: str) -> Optional[str]:
    """
    Attempts to resolve a given string to an IP address.
    If it's already an IP, returns it.
    If it's an interface name and we can get its IP, return that.
    Otherwise, return None.
    """
    # First, try if the interface string is a valid IP address
    try:
        socket.inet_pton(socket.AF_INET, interface)
        return interface  # It's a valid IP address
    except OSError:
        pass  # Not a valid IP, try resolving as interface name

    if netifaces:
        # Attempt to get the IP of the interface by name
        if interface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(interface)
            # We look for IPv4 addresses under netifaces.AF_INET
            if netifaces.AF_INET in addrs:
                for addr_info in addrs[netifaces.AF_INET]:
                    ip_addr = addr_info.get("addr")
                    if ip_addr:
                        return ip_addr
        logger.error(f"Interface '{interface}' not found or has no IPv4 address.")
    else:
        logger.error(
            "Cannot resolve interface name to IP without `netifaces`. "
            "Please provide an IP address directly or install netifaces."
        )

    return None


class CotMessenger:
    """Handles sending CoT messages to TAK servers and multicast addresses."""

    def __init__(
        self,
        tak_client: Optional[TAKClient] = None,
        tak_udp_client: Optional[TAKUDPClient] = None,
        multicast_address: Optional[str] = None,
        multicast_port: Optional[int] = None,
        enable_multicast: bool = False,
        multicast_interface: Optional[str] = None,
    ):
        """
        Initializes the CotMessenger.

        :param tak_client: Instance of TAKClient for TCP/TLS communication.
        :param tak_udp_client: Instance of TAKUDPClient for UDP communication.
        :param multicast_address: Multicast address to send CoT messages.
        :param multicast_port: Multicast port to send CoT messages.
        :param enable_multicast: Flag to enable multicast sending.
        :param multicast_interface: The network interface (IP or name) to use for sending multicast traffic.
        """
        self.tak_client = tak_client
        self.tak_udp_client = tak_udp_client
        self.multicast_address = multicast_address
        self.multicast_port = multicast_port
        self.enable_multicast = enable_multicast
        self.multicast_interface = multicast_interface
        self.multicast_socket = None

        if self.enable_multicast and self.multicast_address and self.multicast_port:
            try:
                self.multicast_socket = socket.socket(
                    socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
                )
                ttl = struct.pack("b", 1)
                self.multicast_socket.setsockopt(
                    socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl
                )

                if self.multicast_interface:
                    interface_ip = resolve_interface_to_ip(self.multicast_interface)
                    if interface_ip:
                        try:
                            packed_if = socket.inet_pton(socket.AF_INET, interface_ip)
                            self.multicast_socket.setsockopt(
                                socket.IPPROTO_IP, socket.IP_MULTICAST_IF, packed_if
                            )
                            logger.debug(
                                f"Set multicast interface to {interface_ip}"
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to set multicast interface '{self.multicast_interface}': {e}"
                            )
                    else:
                        logger.error(
                            f"Could not resolve '{self.multicast_interface}' to a valid IP."
                        )
                logger.debug(
                    f"Initialized persistent multicast socket for {self.multicast_address}:{self.multicast_port}"
                )
            except Exception as e:
                logger.error(f"Failed to initialize multicast socket: {e}")
        else:
            if self.enable_multicast:
                logger.error(
                    "Multicast address or port not provided. Multicast will not be enabled."
                )
            else:
                logger.debug(
                    "Multicast is not enabled. Skipping multicast socket initialization."
                )

    def send_cot(
        self, cot_xml: bytes, retry_count: int = 3, retry_delay: float = 1.0
    ):
        """
        Sends a CoT message to TAK servers and multicast addresses with retry logic.

        :param cot_xml: The CoT XML message in bytes.
        :param retry_count: Number of retry attempts for sending.
        :param retry_delay: Delay between retries in seconds.
        """
        logger.debug("send_cot method called.")
        logger.debug(
            f"Multicast Enabled: {self.enable_multicast}, Multicast Socket: {'Initialized' if self.multicast_socket else 'Not Initialized'}"
        )

        # Sending to TAK server via TCP/TLS
        if self.tak_client:
            for attempt in range(1, retry_count + 1):
                try:
                    self.tak_client.send(cot_xml)
                    logger.info(
                        f"Sent CoT message to TAK server via TCP/TLS at {self.tak_client.host}:{self.tak_client.port}"
                    )
                    break
                except Exception as e:
                    logger.error(
                        f"Attempt {attempt}: Failed to send CoT message via TCP/TLS: {e}"
                    )
                    if attempt < retry_count:
                        time.sleep(retry_delay)
                    else:
                        logger.critical(
                            "Exceeded maximum retries for sending CoT message via TCP/TLS."
                        )
        elif self.tak_udp_client:
            for attempt in range(1, retry_count + 1):
                try:
                    self.tak_udp_client.send(cot_xml)
                    logger.info(
                        f"Sent CoT message to TAK server via UDP at {self.tak_udp_client.host}:{self.tak_udp_client.port}"
                    )
                    break
                except Exception as e:
                    logger.error(
                        f"Attempt {attempt}: Failed to send CoT message via UDP: {e}"
                    )
                    if attempt < retry_count:
                        time.sleep(retry_delay)
                    else:
                        logger.critical(
                            "Exceeded maximum retries for sending CoT message via UDP."
                        )
        else:
            logger.debug(
                "No TAK client configured. Skipping sending CoT message to TAK server."
            )

        # Sending to multicast address
        if self.enable_multicast and self.multicast_socket:
            logger.debug(
                f"Attempting to send CoT message via multicast to {self.multicast_address}:{self.multicast_port}"
            )
            for attempt in range(1, retry_count + 1):
                try:
                    self.multicast_socket.sendto(
                        cot_xml, (self.multicast_address, self.multicast_port)
                    )
                    logger.info(
                        f"Sent CoT message to multicast address {self.multicast_address}:{self.multicast_port} using interface '{self.multicast_interface}'."
                    )
                    break
                except Exception as e:
                    logger.error(
                        f"Attempt {attempt}: Failed to send CoT message via multicast: {e}"
                    )
                    if attempt < retry_count:
                        time.sleep(retry_delay)
                    else:
                        logger.critical(
                            "Exceeded maximum retries for sending CoT message via multicast."
                        )
        else:
            logger.debug(
                "Multicast is not enabled or multicast socket not initialized. Skipping sending CoT message to multicast."
            )

    def close(self):
        """Closes persistent multicast sockets and TAK clients if initialized."""
        if self.multicast_socket:
            try:
                self.multicast_socket.close()
                logger.debug("Closed multicast socket.")
            except Exception as e:
                logger.error(f"Error closing multicast socket: {e}")

        # Close TAK clients if they exist
        if self.tak_client:
            try:
                self.tak_client.close()
                logger.debug("Closed TAK TCP/TLS client.")
            except Exception as e:
                logger.error(f"Error closing TAK TCP/TLS client: {e}")

        if self.tak_udp_client:
            try:
                self.tak_udp_client.close()
                logger.debug("Closed TAK UDP client.")
            except Exception as e:
                logger.error(f"Error closing TAK UDP client: {e}")
