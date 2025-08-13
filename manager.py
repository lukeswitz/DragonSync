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
from typing import Optional, List
import logging
import math
import json
try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

from drone import Drone
from messaging import CotMessenger

logger = logging.getLogger(__name__)

class DroneManager:
    """Manages a collection of drones and handles their updates."""

    def __init__(self, max_drones=30, rate_limit=1.0, inactivity_timeout=60.0,
                 cot_messenger: Optional[CotMessenger] = None,
                 mqtt_enabled=False, mqtt_host='127.0.0.1', mqtt_port=1883, mqtt_topic='wardragon/drones',
                 extra_sinks: Optional[List] = None):
        """
        Initializes the DroneManager.
        
        :param max_drones: Maximum number of drones to track.
        :param rate_limit: Minimum interval between sending updates (in seconds).
        :param inactivity_timeout: Time after which a drone is considered inactive (in seconds).
        :param cot_messenger: Instance of CotMessenger for sending CoT messages.
        """
        self.drones = deque(maxlen=max_drones)
        self.drone_dict = {}
        self.rate_limit = rate_limit          # Update frequency (in seconds)
        self.inactivity_timeout = inactivity_timeout  # Time before a drone is considered stale (in seconds)
        self.cot_messenger = cot_messenger
        self.mqtt_enabled = mqtt_enabled
        self.mqtt_topic = mqtt_topic
        self.mqtt_client = None
        self.extra_sinks = extra_sinks or []

        if self.mqtt_enabled:
            if mqtt is None:
                logger.critical("MQTT support requested, but paho-mqtt is not installed!")
                raise ImportError("paho-mqtt required for MQTT support")
            self.mqtt_client = mqtt.Client()
            try:
                self.mqtt_client.connect(mqtt_host, mqtt_port, 60)
                self.mqtt_client.loop_start()
            except Exception as e:
                logger.critical(f"Failed to connect to MQTT broker: {e}")
                self.mqtt_enabled = False

    def update_or_add_drone(self, drone_id: str, drone_data: Drone):
        """Updates an existing drone or adds a new one to the collection."""
        if drone_id not in self.drone_dict:
            if len(self.drones) >= self.drones.maxlen:
                oldest_drone_id = self.drones.popleft()
                del self.drone_dict[oldest_drone_id]
                logger.debug(f"Removed oldest drone: {oldest_drone_id}")
            self.drones.append(drone_id)
            self.drone_dict[drone_id] = drone_data
            drone_data.last_sent_time = 0.0  # Initialize last sent time for the new drone
            logger.debug(f"Added new drone: {drone_id}")
        else:
            self.drone_dict[drone_id].update(
                lat=drone_data.lat, lon=drone_data.lon, speed=drone_data.speed,
                vspeed=drone_data.vspeed, alt=drone_data.alt, height=drone_data.height,
                pilot_lat=drone_data.pilot_lat, pilot_lon=drone_data.pilot_lon,
                description=drone_data.description, mac=drone_data.mac, rssi=drone_data.rssi
            )
            logger.debug(f"Updated drone: {drone_id}")

    def send_updates(self):
        """Sends regular CoT updates to the TAK server or multicast address.
        
        If a drone stops sending updates, its stale timeout will cause ATAK to remove the event.
        """
        current_time = time.time()
        drones_to_remove = []

        for drone_id in list(self.drones):
            drone = self.drone_dict[drone_id]
            time_since_update = current_time - drone.last_update_time

            # Remove drones that have been inactive beyond the timeout.
            if time_since_update > self.inactivity_timeout:
                drones_to_remove.append(drone_id)
                logger.debug(f"Drone {drone_id} inactive for {time_since_update:.2f}s. Removing from tracking.")
                continue

            # Log the position change (for debugging) between updates.
            delta_lat = drone.lat - drone.last_sent_lat
            delta_lon = drone.lon - drone.last_sent_lon
            position_change = math.sqrt(delta_lat ** 2 + delta_lon ** 2)

            # Send a CoT update if the rate limit interval has passed.
            if current_time - drone.last_sent_time >= self.rate_limit:
                cot_xml = drone.to_cot_xml(
                    stale_offset=self.inactivity_timeout - time_since_update
                )
                if self.cot_messenger:
                    self.cot_messenger.send_cot(cot_xml)
                # MQTT: publish drone as JSON if enabled
                if self.mqtt_enabled and self.mqtt_client:
                    try:
                        # Use a method to convert drone to dict for serialization
                        self.mqtt_client.publish(self.mqtt_topic, json.dumps(vars(drone)))
                    except Exception as e:
                        logger.warning(f"Failed to publish to MQTT: {e}")
                drone.last_sent_lat = drone.lat
                drone.last_sent_lon = drone.lon
                drone.last_sent_time = current_time
                logger.debug(f"Sent CoT update for drone {drone_id} (position change: {position_change:.8f}).")

                # Publish a snapshot to any additional sinks.
                if self.extra_sinks:
                    snapshot = {
                        "id": drone_id,
                        "lat": drone.lat,
                        "lon": drone.lon,
                        "alt": getattr(drone, "alt", 0.0),
                        "speed": getattr(drone, "speed", 0.0),
                        "vspeed": getattr(drone, "vspeed", 0.0),
                        "direction": getattr(drone, "direction", 0.0),
                        "mac": getattr(drone, "mac", ""),
                        "rssi": getattr(drone, "rssi", None),
                        "pilot_lat": getattr(drone, "pilot_lat", 0.0),
                        "pilot_lon": getattr(drone, "pilot_lon", 0.0),
                        "home_lat": getattr(drone, "home_lat", 0.0),
                        "home_lon": getattr(drone, "home_lon", 0.0),
                    }
                    for s in self.extra_sinks:
                        try:
                            # main drone track
                            s.publish_drone(snapshot)
                            # optional pilot/home pins if the sink supports them
                            if (snapshot["pilot_lat"] or snapshot["pilot_lon"]) and hasattr(s, "publish_pilot"):
                                s.publish_pilot(drone_id, snapshot["pilot_lat"], snapshot["pilot_lon"], 0.0)
                            if (snapshot["home_lat"] or snapshot["home_lon"]) and hasattr(s, "publish_home"):
                                s.publish_home(drone_id, snapshot["home_lat"], snapshot["home_lon"], 0.0)
                        except Exception as e:
                            logger.warning(f"Extra sink publish failed for {drone_id}: {e}")

                # Send pilot CoT update (static) if valid coordinates are available.
                if drone.pilot_lat != 0.0 or drone.pilot_lon != 0.0:
                    pilot_xml = drone.to_pilot_cot_xml(
                        stale_offset=self.inactivity_timeout - time_since_update
                    )
                    if self.cot_messenger:
                        self.cot_messenger.send_cot(pilot_xml)
                    logger.debug(f"Sent pilot CoT update for drone {drone_id}.")

                # Send home CoT update (static) if valid coordinates are available.
                if drone.home_lat != 0.0 or drone.home_lon != 0.0:
                    home_xml = drone.to_home_cot_xml(
                        stale_offset=self.inactivity_timeout - time_since_update
                    )
                    if self.cot_messenger:
                        self.cot_messenger.send_cot(home_xml)
                    logger.debug(f"Sent home CoT update for drone {drone_id}.")

        # Remove inactive drones after processing updates.
        for drone_id in drones_to_remove:
            self.drones.remove(drone_id)
            del self.drone_dict[drone_id]
            logger.debug(f"Removed drone: {drone_id}")

    def close(self):
        if self.mqtt_enabled and self.mqtt_client:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except Exception as e:
                logger.warning(f"Error shutting down MQTT client: {e}")

