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


import time
from collections import deque
from typing import Optional
import logging
import struct

from drone import Drone
from tak_client import TAKClient
from tak_udp_client import TAKUDPClient
import socket

logger = logging.getLogger(__name__)

def send_to_tak_udp_multicast(cot_xml: bytes, multicast_address: str, multicast_port: int):
    """Sends a CoT XML message to a multicast address via UDP."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        ttl = struct.pack('b', 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
        sock.sendto(cot_xml, (multicast_address, multicast_port))
        sock.close()
        logger.debug(f"Sent CoT message via multicast to {multicast_address}:{multicast_port}")
    except Exception as e:
        logger.error(f"Error sending CoT message via multicast: {e}")

class DroneManager:
    """Manages a collection of drones and handles their updates."""

    def __init__(self, max_drones=30, rate_limit=1.0, inactivity_timeout=60.0):
        self.drones = deque(maxlen=max_drones)
        self.drone_dict = {}
        self.rate_limit = rate_limit
        self.inactivity_timeout = inactivity_timeout
        self.last_sent_time = 0.0

    def update_or_add_drone(self, drone_id: str, drone_data: Drone):
        """Updates an existing drone or adds a new one to the collection."""
        if drone_id not in self.drone_dict:
            if len(self.drones) >= self.drones.maxlen:
                oldest_drone_id = self.drones.popleft()
                del self.drone_dict[oldest_drone_id]
                logger.debug(f"Removed oldest drone: {oldest_drone_id}")
            self.drones.append(drone_id)
            self.drone_dict[drone_id] = drone_data
            logger.debug(f"Added new drone: {drone_id}")
        else:
            self.drone_dict[drone_id] = drone_data
            logger.debug(f"Updated drone: {drone_id}")

    def send_updates(self, tak_client: Optional[TAKClient], tak_udp_client: Optional[TAKUDPClient],
                     tak_host: Optional[str], tak_port: Optional[int],
                     enable_multicast: bool, multicast_address: Optional[str], multicast_port: Optional[int]):
        """Sends updates to the TAK server or multicast address."""
        current_time = time.time()
        if current_time - self.last_sent_time >= self.rate_limit:
            drones_to_remove = []
            for drone_id in list(self.drones):
                drone = self.drone_dict[drone_id]
                time_since_update = current_time - drone.last_update_time
                if time_since_update > self.inactivity_timeout:
                    # Drone is inactive, send a final CoT message with stale time set to now
                    cot_xml = drone.to_cot_xml(stale_offset=0)  # Set stale time to current time
                    self.send_cot_message(cot_xml, tak_client, tak_udp_client, tak_host, tak_port, enable_multicast, multicast_address, multicast_port)
                    drones_to_remove.append(drone_id)
                    logger.debug(f"Drone {drone_id} is inactive for {time_since_update:.2f} seconds. Sent final CoT message and removing from tracking.")
                    continue  # Skip sending regular CoT message for inactive drones

                # Update the 'stale' time in CoT message to reflect inactivity timeout
                cot_xml = drone.to_cot_xml(stale_offset=self.inactivity_timeout - time_since_update)
                self.send_cot_message(cot_xml, tak_client, tak_udp_client, tak_host, tak_port, enable_multicast, multicast_address, multicast_port)

            # Remove inactive drones
            for drone_id in drones_to_remove:
                self.drones.remove(drone_id)
                del self.drone_dict[drone_id]
                logger.debug(f"Removed drone: {drone_id}")

            self.last_sent_time = current_time

    def send_cot_message(self, cot_xml: bytes, tak_client: Optional[TAKClient], tak_udp_client: Optional[TAKUDPClient],
                        tak_host: Optional[str], tak_port: Optional[int],
                        enable_multicast: bool, multicast_address: Optional[str], multicast_port: Optional[int]):
        """Helper method to send CoT messages to TAK client or multicast address."""
        # Sending to TAK server via TCP/TLS
        if tak_client:
            tak_client.send(cot_xml)
            logger.info(f"Sent CoT message to TAK server via TCP/TLS at {tak_host}:{tak_port}")
        elif tak_udp_client:
            tak_udp_client.send(cot_xml)
            logger.info(f"Sent CoT message to TAK server via UDP at {tak_host}:{tak_port}")
        else:
            logger.debug("No TAK client configured. Skipping sending CoT message to TAK server.")

        # Sending to multicast address
        if enable_multicast and multicast_address and multicast_port:
            send_to_tak_udp_multicast(cot_xml, multicast_address, multicast_port)
            logger.info(f"Sent CoT message to multicast address {multicast_address}:{multicast_port}")
        else:
            logger.debug("Multicast is not enabled or multicast address/port provided. Skipping sending CoT message to multicast.")
