"""
MIT License

Copyright (c) 2025 cemaxecuter

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

# lattice_sink.py
# Optional sink for DragonSync: publishes drone tracks + WarDragon (ground sensor) status to Lattice.

import math
import time
import datetime as dt
from typing import Any, Dict, Optional

# --- Lattice client import (required) ---
try:
    # Install via: pip install anduril
    from anduril import Lattice
except Exception as e:
    raise ImportError("Lattice SDK not available. Install with `pip install anduril`.") from e

# --- Prefer concrete SDK models/enums when available; otherwise fallback to dicts ---
try:
    from anduril.types.mil_view import MilView
    from anduril.types.ontology import Ontology
    from anduril.types.aliases import Aliases
    from anduril.types.location import Location, LocationPosition, LocationKinematics
    from anduril.types.health import Health
    from anduril.types.provenance import Provenance
except Exception:
    MilView = Ontology = Aliases = Location = LocationPosition = LocationKinematics = Health = Provenance = None  # type: ignore

UTC = dt.timezone.utc

def _now() -> dt.datetime:
    return dt.datetime.now(UTC)

def _exp(minutes: float) -> dt.datetime:
    # expiry must be in the future and < 30 days; we refresh this each publish
    return _now() + dt.timedelta(minutes=minutes)

def _f(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

def _valid_latlon(lat: float, lon: float) -> bool:
    # Both present, finite, within range, and not (0,0)
    if lat is None or lon is None:
        return False
    try:
        lat = float(lat)
        lon = float(lon)
    except Exception:
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return False
    if lat == 0.0 and lon == 0.0:
        return False
    return True

class LatticeSink:
    """
    Publishes entities using the SDK call:
      client.entities.publish_entity(entity_id=..., is_live=..., expiry_time=...,
                                     aliases=..., ontology=..., mil_view=..., location=..., provenance=..., [health=...])

    - Uses SDK enums/classes if available; falls back to dicts otherwise.
    - Rate-limited so it won't flood the API.
    """

    def __init__(
        self,
        token: str,
        base_url: Optional[str] = None,   # e.g., "https://your.env.anduril.cloud"
        drone_hz: float = 1.0,
        wardragon_hz: float = 0.2,
        source_name: str = "DragonSync",
    ):
        self.client = Lattice(token=token, base_url=base_url) if base_url else Lattice(token=token)
        self.source_name = source_name
        self._drone_period = 1.0 / max(drone_hz, 1e-3)
        self._wd_period = 1.0 / max(wardragon_hz, 1e-3)
        self._next_drone = 0.0
        self._next_wd = 0.0

    # ---------------- internals ----------------
    def _rate_ok(self, kind: str) -> bool:
        t = time.time()
        if kind == "drone":
            if t >= self._next_drone:
                self._next_drone = t + self._drone_period
                return True
            return False
        else:
            if t >= self._next_wd:
                self._next_wd = t + self._wd_period
                return True
            return False

    def _base_entity(
        self,
        *,
        entity_id: str,
        lat: float,
        lon: float,
        hae_m: float,
        ontology_kind: str,
        environment: str,
        expiry_min: float
    ) -> Dict[str, Any]:
        """
        Build the minimal entity payload using SDK classes when available, else plain dicts.
        `environment` expects a MilView.Environment name like "ENVIRONMENT_AIR" or "ENVIRONMENT_GROUND".
        """
        prov_time = _now()
        if MilView and Ontology and Aliases and Location and LocationPosition and Provenance:
            env_value = getattr(MilView.Environment, environment, environment)
            return {
                "entity_id": entity_id,
                "is_live": True,
                "expiry_time": _exp(expiry_min),
                "aliases": Aliases(values=[entity_id]),
                "ontology": Ontology(kind=ontology_kind),
                "mil_view": MilView(environment=env_value),
                "location": Location(position=LocationPosition(
                    wgs84_lat_deg=lat, wgs84_lon_deg=lon, hae_m=hae_m
                )),
                "provenance": Provenance(source=self.source_name, source_update_time=prov_time),
            }
        else:
            return {
                "entity_id": entity_id,
                "is_live": True,
                "expiry_time": _exp(expiry_min),
                "aliases": {"values": [entity_id]},
                "ontology": {"kind": ontology_kind},
                "mil_view": {"environment": environment},  # e.g., "ENVIRONMENT_GROUND"
                "location": {
                    "position": {
                        "wgs84_lat_deg": lat,
                        "wgs84_lon_deg": lon,
                        "hae_m": hae_m
                    }
                },
                "provenance": {
                    "source": self.source_name,
                    "source_update_time": prov_time
                }
            }

    # ---------------- public API ----------------
    def publish_drone(self, d: Dict[str, Any]) -> None:
        """Publish airborne drone track. Expects: id, lat, lon, alt, speed, direction, vspeed (optional)."""
        if not self._rate_ok("drone"):
            return

        entity_id = str(d.get("id") or f"drone-{d.get('mac','unknown')}")
        lat = _f(d.get("lat")); lon = _f(d.get("lon")); hae = _f(d.get("alt"))
        if not _valid_latlon(lat, lon):
            return

        spd = _f(d.get("speed"))
        crs = _f(d.get("direction"))
        vs  = _f(d.get("vspeed"), 0.0)

        # Convert course/speed (m/s) to ENU velocity (east, north, up)
        v_e = spd * math.sin(math.radians(crs))
        v_n = spd * math.cos(math.radians(crs))
        v_u = -vs  # common feeds give positive "down"; up = -down

        payload = self._base_entity(
            entity_id=entity_id,
            lat=lat, lon=lon, hae_m=hae,
            ontology_kind="UAV",
            environment="ENVIRONMENT_AIR",
            expiry_min=10.0
        )

        # Attach kinematics using SDK types if available
        if Location and LocationKinematics and isinstance(payload.get("location"), Location):
            payload["location"].kinematics = LocationKinematics(  # type: ignore[attr-defined]
                velocity_e_mps=v_e, velocity_n_mps=v_n, velocity_u_mps=v_u
            )
        else:
            payload.setdefault("location", {}).setdefault("kinematics", {})
            payload["location"]["kinematics"].update({
                "velocity_e_mps": v_e,
                "velocity_n_mps": v_n,
                "velocity_u_mps": v_u
            })

        # Health (SDK type if available)
        if Health:
            payload["health"] = Health(state=Health.State.ONLINE, status="Nominal")  # type: ignore[attr-defined]
        else:
            payload["health"] = {"state": "ONLINE", "status": "Nominal"}

        self.client.entities.publish_entity(**payload)

    def publish_system(self, s: Dict[str, Any]) -> None:
        """Publish WarDragon (ground sensor) status. Needs s['serial_number'] and s['gps_data'] lat/lon/alt."""
        if not self._rate_ok("wd"):
            return

        entity_id = f"wardragon-{s.get('serial_number','unknown')}"
        gps = s.get("gps_data", {}) or {}
        lat = _f(gps.get("latitude")); lon = _f(gps.get("longitude")); hae = _f(gps.get("altitude"))
        if not _valid_latlon(lat, lon):
            return

        payload = self._base_entity(
            entity_id=entity_id,
            lat=lat, lon=lon, hae_m=hae,
            ontology_kind="SENSOR",             # ground sensor
            environment="ENVIRONMENT_GROUND",   # plotted on ground
            expiry_min=10.0
        )

        stats = s.get("system_stats", {}) or {}
        cpu = stats.get("cpu_usage", 0)
        temp = stats.get("temperature", 0)

        if Health:
            payload["health"] = Health(
                state=Health.State.ONLINE,  # type: ignore[attr-defined]
                status=f"CPU {cpu}%, Temp {temp}°C"
            )
        else:
            payload["health"] = {"state": "ONLINE", "status": f"CPU {cpu}%, Temp {temp}°C"}

        self.client.entities.publish_entity(**payload)

    def publish_pilot(self, pilot_id: str, lat: float, lon: float, hae: float = 0.0) -> None:
        """Publish operator position (ground)."""
        if not _valid_latlon(lat, lon):
            return

        payload = self._base_entity(
            entity_id=f"pilot-{pilot_id}",
            lat=lat, lon=lon, hae_m=hae,
            ontology_kind="PERSON",
            environment="ENVIRONMENT_GROUND",
            expiry_min=30.0
        )

        self.client.entities.publish_entity(**payload)

    def publish_home(self, drone_id: str, lat: float, lon: float, hae: float = 0.0) -> None:
        """Publish takeoff/home point (ground)."""
        if not _valid_latlon(lat, lon):
            return

        payload = self._base_entity(
            entity_id=f"home-{drone_id}",
            lat=lat, lon=lon, hae_m=hae,
            ontology_kind="POINT_OF_INTEREST",
            environment="ENVIRONMENT_GROUND",
            expiry_min=60.0 * 24  # 24h; keep well under 30 days
        )

        self.client.entities.publish_entity(**payload)

    def close(self) -> None:
        return
