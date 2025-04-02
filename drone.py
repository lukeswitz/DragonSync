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

import datetime
import xml.sax.saxutils
from lxml import etree
from typing import Optional
import time
import logging

logger = logging.getLogger(__name__)

class Drone:
    """Represents a drone and its telemetry data."""

    def __init__(self, id: str, lat: float, lon: float, speed: float, vspeed: float,
                 alt: float, height: float, pilot_lat: float, pilot_lon: float, description: str,
                 mac: str, rssi: int, home_lat: float = 0.0, home_lon: float = 0.0, id_type: str = "",
                 index: int = 0, runtime: int = 0, caa_id: str = ""):
        self.id = id
        self.id_type = id_type
        self.index = index
        self.runtime = runtime
        self.mac = mac
        self.rssi = rssi
        self.lat = lat
        self.lon = lon
        self.speed = speed
        self.vspeed = vspeed
        self.alt = alt
        self.height = height
        self.pilot_lat = pilot_lat
        self.pilot_lon = pilot_lon
        self.home_lat = home_lat
        self.home_lon = home_lon    
        self.description = description
        self.last_update_time = time.time()
        self.last_sent_time = 0.0  # Track last time an update was sent
        # Track last sent position for flight updates
        self.last_sent_lat = lat
        self.last_sent_lon = lon
        # Counter for consecutive movement updates above threshold
        self.consecutive_move_count = 0
        # Store additional CAA info if provided
        self.caa_id = caa_id
        # Track the last time a keep-alive message was generated
        self.last_keepalive_time = 0.0

    def update(self, lat: float, lon: float, speed: float, vspeed: float, alt: float,
               height: float, pilot_lat: float, pilot_lon: float, description: str, mac: str, rssi: int,
               home_lat: float = 0.0, home_lon: float = 0.0, id_type: str = "", index: int = 0,
               runtime: int = 0, caa_id: str = ""):
        """Updates the drone's telemetry data."""
        self.lat = lat
        self.lon = lon
        self.id_type = id_type
        self.speed = speed
        self.vspeed = vspeed
        self.alt = alt
        self.height = height
        self.pilot_lat = pilot_lat
        self.pilot_lon = pilot_lon
        self.home_lat = home_lat
        self.home_lon = home_lon
        self.description = description
        self.last_update_time = time.time()
        self.mac = mac
        self.rssi = rssi
        self.index = index
        self.runtime = runtime
        # If a CAA ID is provided, update our stored value.
        if caa_id:
            self.caa_id = caa_id

    def to_cot_xml(self, stale_offset: Optional[float] = None, unique: bool = True) -> bytes:
        """Converts the drone's telemetry data to a Cursor-on-Target (CoT) XML message.
        
        :param stale_offset: Seconds to add to the current time to determine the stale time.
        :param unique: If True, generate a unique UID (for moving drones forming a flight path); 
                       if False, use a static UID (for hovering drones).
        """
        current_time = datetime.datetime.utcnow()
        if stale_offset is not None:
            stale_time = current_time + datetime.timedelta(seconds=stale_offset)
        else:
            stale_time = current_time + datetime.timedelta(minutes=10)

        # For non-unique (keep-alive) updates, update the last_keepalive_time.
        if not unique:
            self.last_keepalive_time = time.time()

        if unique:
            unique_suffix = current_time.strftime("%Y%m%dT%H%M%S%fZ")
            uid = f"{self.id}-{unique_suffix}"
        else:
            uid = self.id

        event = etree.Element(
            'event',
            version='2.0',
            uid=uid,
            type='b-m-p-s-m',
            time=current_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            start=current_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            stale=stale_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            how='m-g'
        )

        point = etree.SubElement(
            event,
            'point',
            lat=str(self.lat),
            lon=str(self.lon),
            hae=str(self.alt),
            ce='35.0',
            le='999999'
        )

        detail = etree.SubElement(event, 'detail')
        # Use static drone ID for display purposes
        etree.SubElement(detail, 'contact', endpoint='', phone='', callsign=self.id)
        etree.SubElement(detail, 'precisionlocation', geopointsrc='gps', altsrc='gps')

        remarks_text = (
            f"MAC: {self.mac}, RSSI: {self.rssi}dBm, "
            f"ID Type: {self.id_type}, "  
            f"Self-ID: {self.description}, "
            f"Location/Vector: [Speed: {self.speed} m/s, Vert Speed: {self.vspeed} m/s, "
            f"Geodetic Altitude: {self.alt} m, Height AGL: {self.height} m], "
            f"System: [Operator Lat: {self.pilot_lat}, Operator Lon: {self.pilot_lon}, "
            f"Home Lat: {self.home_lat}, Home Lon: {self.home_lon}, Index: {self.index}, Runtime: {self.runtime}]"
        )
        etree.SubElement(detail, 'remarks').text = xml.sax.saxutils.escape(remarks_text)
        etree.SubElement(detail, 'color', argb='-256')
        etree.SubElement(
            detail,
            'usericon',
            iconsetpath='34ae1613-9645-4222-a9d2-e5f243dea2865/Military/UAV_quad.png'
        )

        cot_xml = etree.tostring(event, pretty_print=True, xml_declaration=True, encoding='UTF-8')
        logger.debug("CoT XML for drone '%s':\n%s", self.id, cot_xml.decode('utf-8'))
        return cot_xml

    def to_pilot_cot_xml(self, stale_offset: Optional[float] = None) -> bytes:
        """Generates a CoT XML message for the pilot location using a static UID."""
        current_time = datetime.datetime.utcnow()
        if stale_offset is not None:
            stale_time = current_time + datetime.timedelta(seconds=stale_offset)
        else:
            stale_time = current_time + datetime.timedelta(minutes=10)

        base_id = self.id
        if base_id.startswith("drone-"):
            base_id = base_id[len("drone-"):]
        uid = f"pilot-{base_id}"  # Static UID for pilot location

        event = etree.Element(
            'event',
            version='2.0',
            uid=uid,
            type='b-m-p-s-m',
            time=current_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            start=current_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            stale=stale_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            how='m-g'
        )

        point = etree.SubElement(
            event,
            'point',
            lat=str(self.pilot_lat),
            lon=str(self.pilot_lon),
            hae=str(self.alt),
            ce='35.0',
            le='999999'
        )

        detail = etree.SubElement(event, 'detail')
        static_callsign = f"pilot-{base_id}"
        etree.SubElement(detail, 'contact', endpoint='', phone='', callsign=static_callsign)
        etree.SubElement(detail, 'precisionlocation', geopointsrc='gps', altsrc='gps')
        remarks_text = f"Pilot location for drone {self.id}"
        etree.SubElement(detail, 'remarks').text = xml.sax.saxutils.escape(remarks_text)
        etree.SubElement(
            detail,
            'usericon',
            iconsetpath='34ae1613-9645-4222-a9d2-e5f243dea2865/Military/Soldier.png'
        )

        cot_xml = etree.tostring(event, pretty_print=True, xml_declaration=True, encoding='UTF-8')
        logger.debug("CoT XML for pilot of drone '%s':\n%s", self.id, cot_xml.decode('utf-8'))
        return cot_xml

    def to_home_cot_xml(self, stale_offset: Optional[float] = None) -> bytes:
        """Generates a CoT XML message for the home location using a static UID."""
        current_time = datetime.datetime.utcnow()
        if stale_offset is not None:
            stale_time = current_time + datetime.timedelta(seconds=stale_offset)
        else:
            stale_time = current_time + datetime.timedelta(minutes=10)

        base_id = self.id
        if base_id.startswith("drone-"):
            base_id = base_id[len("drone-"):]
        uid = f"home-{base_id}"  # Static UID for home location

        event = etree.Element(
            'event',
            version='2.0',
            uid=uid,
            type='b-m-p-s-m',
            time=current_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            start=current_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            stale=stale_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            how='m-g'
        )

        point = etree.SubElement(
            event,
            'point',
            lat=str(self.home_lat),
            lon=str(self.home_lon),
            hae=str(self.alt),
            ce='35.0',
            le='999999'
        )

        detail = etree.SubElement(event, 'detail')
        static_callsign = f"home-{base_id}"
        etree.SubElement(detail, 'contact', endpoint='', phone='', callsign=static_callsign)
        etree.SubElement(detail, 'precisionlocation', geopointsrc='gps', altsrc='gps')
        remarks_text = f"Home location for drone {self.id}"
        etree.SubElement(detail, 'remarks').text = xml.sax.saxutils.escape(remarks_text)
        etree.SubElement(
            detail,
            'usericon',
            iconsetpath='34ae1613-9645-4222-a9d2-e5f243dea2865/Military/House.png'
        )

        cot_xml = etree.tostring(event, pretty_print=True, xml_declaration=True, encoding='UTF-8')
        logger.debug("CoT XML for home of drone '%s':\n%s", self.id, cot_xml.decode('utf-8'))
        return cot_xml
