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

class Drone:
    """Represents a drone and its telemetry data."""

    def __init__(self, id: str, lat: float, lon: float, speed: float, vspeed: float,
                 alt: float, height: float, pilot_lat: float, pilot_lon: float, description: str):
        self.id = id
        self.lat = lat
        self.lon = lon
        self.speed = speed
        self.vspeed = vspeed
        self.alt = alt
        self.height = height
        self.pilot_lat = pilot_lat
        self.pilot_lon = pilot_lon
        self.description = description
        self.last_update_time = time.time()
        self.first_seen = True  # Initialize as True for new drones

    def update(self, lat: float, lon: float, speed: float, vspeed: float, alt: float,
               height: float, pilot_lat: float, pilot_lon: float, description: str):
        """Updates the drone's telemetry data."""
        self.lat = lat
        self.lon = lon
        self.speed = speed
        self.vspeed = vspeed
        self.alt = alt
        self.height = height
        self.pilot_lat = pilot_lat
        self.pilot_lon = pilot_lon
        self.description = description
        self.last_update_time = time.time()
        self.first_seen = False  # Set to False after the first update

    def to_cot_xml(self, stale_offset: Optional[float] = None) -> bytes:
        """Converts the drone's telemetry data to a Cursor-on-Target (CoT) XML message."""
        current_time = datetime.datetime.utcnow()
        if stale_offset is not None:
            stale_time = current_time + datetime.timedelta(seconds=stale_offset)
        else:
            stale_time = current_time + datetime.timedelta(minutes=10)

        # Adjust the event type based on whether it's the first time the drone is seen
        if self.first_seen:
            event_type = 'a-f-G-U-C'  # Generic alert event type to trigger an alert in ATAK
        else:
            event_type = 'b-m-p-s-m'  # Regular military type

        # Create the root 'event' element with necessary attributes
        event = etree.Element(
            'event',
            version='2.0',
            uid=self.id,
            type=event_type,
            time=current_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            start=current_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            stale=stale_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
            how='m-g'
        )

        # Create 'point' element with the drone's position and altitude
        point = etree.SubElement(
            event,
            'point',
            lat=str(self.lat),
            lon=str(self.lon),
            hae=str(self.alt),
            ce='35.0',     # Circular Error - positional accuracy in meters
            le='999999'    # Linear Error - vertical accuracy in meters
        )

        # Create 'detail' element to hold additional information
        detail = etree.SubElement(event, 'detail')

        # Add 'contact' element with the drone's ID as the callsign
        etree.SubElement(detail, 'contact', endpoint='', phone='', callsign=self.id)

        # Add 'precisionlocation' element indicating GPS sources
        etree.SubElement(detail, 'precisionlocation', geopointsrc='gps', altsrc='gps')

        # Add a 'status' element to trigger alert in ATAK if it's the first time seen
        if self.first_seen:
            status = etree.SubElement(detail, 'status')
            status.set('readiness', 'alert')
            status.set('battery', '100')  # Optional attribute

        # Create a 'remarks' element with escaped text containing drone details
        remarks_text = (
            f"Description: {self.description}, Speed: {self.speed} m/s, "
            f"VSpeed: {self.vspeed} m/s, Altitude: {self.alt} m, "
            f"Height: {self.height} m, Pilot Lat: {self.pilot_lat}, "
            f"Pilot Lon: {self.pilot_lon}"
        )
        remarks_text = xml.sax.saxutils.escape(remarks_text)
        etree.SubElement(detail, 'remarks').text = remarks_text

        # Add a 'color' element to set the display color in ATAK
        etree.SubElement(detail, 'color', argb='-256')

        # Add a 'usericon' element to specify the icon used in ATAK
        etree.SubElement(
            detail,
            'usericon',
            iconsetpath='34ae1613-9645-4222-a9d2-e5f243dea2865/Military/UAV_quad.png'
        )

        # Convert the XML tree to a byte string
        return etree.tostring(event, pretty_print=True, xml_declaration=True, encoding='UTF-8')
