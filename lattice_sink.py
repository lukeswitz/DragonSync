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

from __future__ import annotations

import logging
import time
from typing import Optional, Dict, Any
import datetime as dt
import os

# ────────────────────────────────────────────────────────────────────────────────
# Anduril SDK imports
# ────────────────────────────────────────────────────────────────────────────────
try:
    import anduril as _anduril_mod  # for __version__
    from anduril import Lattice
    from anduril import (
        Location,
        Position,
        MilView,
        Ontology,
        Provenance,
        Aliases,
        Classification,
        ClassificationInformation,
    )
    # Optional enum (names differ across SDKs; we only use it for AIR)
    try:
        from anduril.entities.types.mil_view import Environment as MilEnvironment  # type: ignore
    except Exception:
        MilEnvironment = None  # type: ignore

    # Optional: some SDK versions support per-request extra headers
    try:
        from anduril.core.request_options import RequestOptions  # type: ignore
    except Exception:
        RequestOptions = None  # type: ignore

except Exception as e:
    _IMPORT_ERROR = e
    Lattice = None  # type: ignore
    Location = Position = MilView = Ontology = Provenance = Aliases = None  # type: ignore
    Classification = ClassificationInformation = None  # type: ignore
    MilEnvironment = None  # type: ignore
    RequestOptions = None  # type: ignore
    _SDK_VERSION = "unknown"
else:
    _IMPORT_ERROR = None
    _SDK_VERSION = getattr(_anduril_mod, "__version__", "unknown")

_log = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────────
def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)

def _valid_latlon(lat: Optional[float], lon: Optional[float]) -> bool:
    try:
        if lat is None or lon is None:
            return False
        return -90.0 <= float(lat) <= 90.0 and -180.0 <= float(lon) <= 180.0
    except Exception:
        return False

def _air_env_value():
    """
    Return a value acceptable to MilView.environment for 'AIR'.
    Prefer enum if present; fall back to the proto string used in examples.
    """
    if MilEnvironment is not None:
        for attr in ("MIL_VIEW_ENVIRONMENT_AIR", "ENVIRONMENT_AIR"):
            if hasattr(MilEnvironment, attr):
                return getattr(MilEnvironment, attr)
    return "ENVIRONMENT_AIR"

# ────────────────────────────────────────────────────────────────────────────────
# LatticeSink
# ────────────────────────────────────────────────────────────────────────────────
class LatticeSink:
    """
    Minimal publisher for entities via the Anduril Lattice SDK.

    - Uses the *environment* token (Authorization) and optional *sandbox* token
      via 'anduril-sandbox-authorization: Bearer <token>'.
    - For WarDragon/pilot/home (ground), we avoid env/disp enum issues by not
      setting them (server defaults). Drones keep environment=AIR.
    """

    def __init__(
        self,
        *,
        token: str,
        base_url: Optional[str] = None,
        drone_hz: float = 1.0,
        wardragon_hz: float = 0.2,
        source_name: str = "DragonSync",
        sandbox_token: Optional[str] = None,
    ) -> None:
        if _IMPORT_ERROR is not None:
            raise RuntimeError(f"anduril SDK import failed: {_IMPORT_ERROR}") from _IMPORT_ERROR

        token = (token or "").strip()
        base_url = (base_url or "").strip() or None
        self._sandbox_token = (sandbox_token or "").strip() or None
        self.source_name = source_name

        headers = {"anduril-sandbox-authorization": f"Bearer {self._sandbox_token}"} if self._sandbox_token else None
        self._req_opts = None
        try:
            if base_url:
                self.client = Lattice(token=token, base_url=base_url, headers=headers)  # type: ignore
            else:
                self.client = Lattice(token=token, headers=headers)  # type: ignore
            _log.info("LatticeSink ACTIVE. file=%s", os.path.abspath(__file__))
            _log.info("anduril SDK version: %s", _SDK_VERSION)
            _log.info("Lattice client constructed with client-level headers=%s", bool(headers))
        except TypeError:
            if base_url:
                self.client = Lattice(token=token, base_url=base_url)  # type: ignore
            else:
                self.client = Lattice(token=token)  # type: ignore
            if self._sandbox_token and RequestOptions is not None:
                self._req_opts = RequestOptions(
                    additional_headers={"anduril-sandbox-authorization": f"Bearer {self._sandbox_token}"}
                )
            _log.info("LatticeSink ACTIVE. file=%s", os.path.abspath(__file__))
            _log.info("anduril SDK version: %s", _SDK_VERSION)
            _log.info(
                "Lattice client constructed with client-level headers=%s; per-request headers=%s",
                False,
                bool(self._req_opts),
            )

        self._periods = {
            "drone": 1.0 / max(drone_hz, 1e-6),
            "wd": 1.0 / max(wardragon_hz, 1e-6),
            "pilot": 1.0,
            "home": 1.0,
        }
        self._last_send = {k: 0.0 for k in self._periods.keys()}

    def _rate_ok(self, key: str) -> bool:
        now = time.time()
        if now - self._last_send.get(key, 0.0) >= self._periods.get(key, 0.0):
            self._last_send[key] = now
            return True
        return False

    # ───────────────────────────── WarDragon (ground sensor) ───────────────────────
    def publish_system(self, s: Dict[str, Any]) -> None:
        """
        Publish WarDragon ground-sensor status as a track.
        NOTE: omit environment; disposition kept NEUTRAL (works).
        """
        if not self._rate_ok("wd"):
            return

        serial = str(s.get("serial_number", "unknown")) or "unknown"
        gps = s.get("gps_data", {}) or {}
        lat = gps.get("latitude")
        lon = gps.get("longitude")
        hae = gps.get("altitude")
        if not _valid_latlon(lat, lon):
            return

        entity_id = f"wardragon-{serial}"
        alias_name = f"WarDragon {serial}"

        location = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
        try:
            if hae is not None:
                location.position.height_above_ellipsoid_meters = float(hae)  # type: ignore[attr-defined]
        except Exception:
            pass

        ontology = Ontology(template="TEMPLATE_TRACK", platform_type="Ground Sensor")
        mil_view = MilView(disposition="DISPOSITION_NEUTRAL")  # keep; accepted by your sandbox

        provenance = Provenance(
            data_type="telemetry",
            integration_name=self.source_name,
            source_update_time=_now_utc().isoformat(),
        )
        aliases = Aliases(name=alias_name)
        expiry_time = _now_utc() + dt.timedelta(minutes=10)

        try:
            self.client.entities.publish_entity(
                entity_id=entity_id,
                is_live=True,
                location=location,
                ontology=ontology,
                mil_view=mil_view,
                provenance=provenance,
                aliases=aliases,
                expiry_time=expiry_time,
                data_classification=Classification(
                    default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")
                ),
                request_options=self._req_opts,
            )
        except Exception as e:
            _log.warning("Lattice publish_system failed for %s: %s", entity_id, e)

    # ───────────────────────────────── Drone (air track) ───────────────────────────
    def publish_drone(self, d: Any) -> None:
        """
        Publish/refresh a drone entity. We DO set environment to AIR here.
        """
        if not self._rate_ok("drone"):
            return

        def g(key, default=None):
            if isinstance(d, dict):
                return d.get(key, default)
            return getattr(d, key, default)

        entity_id = str(g("id", "unknown")) or "unknown"
        lat = g("lat")
        lon = g("lon")
        hae = g("alt")
        if not _valid_latlon(lat, lon):
            return

        location = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
        try:
            if hae is not None:
                location.position.height_above_ellipsoid_meters = float(hae)  # type: ignore[attr-defined]
        except Exception:
            pass

        aliases = Aliases(name=entity_id)
        ontology = Ontology(template="TEMPLATE_TRACK", platform_type="Small UAS")

        mil_view = MilView(
            environment=_air_env_value(),
            disposition="DISPOSITION_NEUTRAL",
        )

        provenance = Provenance(
            data_type="drone-telemetry",
            integration_name=self.source_name,
            source_update_time=_now_utc().isoformat(),
        )
        expiry_time = _now_utc() + dt.timedelta(minutes=5)

        try:
            self.client.entities.publish_entity(
                entity_id=entity_id,
                is_live=True,
                location=location,
                ontology=ontology,
                mil_view=mil_view,
                provenance=provenance,
                aliases=aliases,
                expiry_time=expiry_time,
                data_classification=Classification(
                    default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")
                ),
                request_options=self._req_opts,
            )
        except Exception as e:
            _log.warning("Lattice publish_drone failed for %s: %s", entity_id, e)

    # ───────────────────────────── Pilot & Home (ground) ───────────────────────────
    def publish_pilot(self, entity_base_id: str, lat: float, lon: float, *args, **kwargs) -> None:
        """
        Publish/refresh the pilot entity.

        Compatible call forms:
            publish_pilot(id, lat, lon)
            publish_pilot(id, lat, lon, "Pilot Name")
            publish_pilot(id, lat, lon, 123.4)            # altitude (HAE m)
            publish_pilot(id, lat, lon, name="Pilot X")
            publish_pilot(id, lat, lon, display_name="Pilot X")
            publish_pilot(id, lat, lon, altitude=123.4)   # or hae=123.4
        """
        if not self._rate_ok("pilot"):
            return
        if not _valid_latlon(lat, lon):
            return

        display_name = kwargs.get("display_name") or kwargs.get("name")
        hae = kwargs.get("altitude", kwargs.get("hae"))

        if args:
            extra = args[0]
            if isinstance(extra, str) and not display_name:
                display_name = extra
            else:
                try:
                    if hae is None:
                        hae = float(extra)
                except Exception:
                    pass

        entity_id = f"{entity_base_id}-pilot"
        if not display_name:
            display_name = f"Pilot of {entity_base_id}"

        location = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
        try:
            if hae is not None:
                location.position.height_above_ellipsoid_meters = float(hae)  # type: ignore
        except Exception:
            pass

        ontology = Ontology(template="TEMPLATE_TRACK", platform_type="Operator")
        mil_view = MilView()  # <-- omit env & disposition to avoid enum underscore issues
        provenance = Provenance(
            data_type="pilot-position",
            integration_name=self.source_name,
            source_update_time=_now_utc().isoformat(),
        )
        expiry_time = _now_utc() + dt.timedelta(minutes=30)

        try:
            self.client.entities.publish_entity(
                entity_id=entity_id,
                is_live=True,
                location=location,
                ontology=ontology,
                mil_view=mil_view,
                provenance=provenance,
                aliases=Aliases(name=str(display_name)),
                expiry_time=expiry_time,
                data_classification=Classification(
                    default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")
                ),
                request_options=self._req_opts,
            )
        except Exception as e:
            _log.warning("Lattice publish_pilot failed for %s: %s", entity_id, e)

    def publish_home(self, entity_base_id: str, lat: float, lon: float, *args, **kwargs) -> None:
        """
        Publish/refresh the home point entity.

        Compatible call forms:
            publish_home(id, lat, lon)
            publish_home(id, lat, lon, "Home Label")
            publish_home(id, lat, lon, 123.4)             # altitude (HAE m)
            publish_home(id, lat, lon, name="Home of X")
            publish_home(id, lat, lon, display_name="Home of X")
            publish_home(id, lat, lon, altitude=123.4)    # or hae=123.4
        """
        if not self._rate_ok("home"):
            return
        if not _valid_latlon(lat, lon):
            return

        display_name = kwargs.get("display_name") or kwargs.get("name")
        hae = kwargs.get("altitude", kwargs.get("hae"))

        if args:
            extra = args[0]
            if isinstance(extra, str) and not display_name:
                display_name = extra
            else:
                try:
                    if hae is None:
                        hae = float(extra)
                except Exception:
                    pass

        entity_id = f"{entity_base_id}-home"
        if not display_name:
            display_name = f"Home of {entity_base_id}"

        location = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
        try:
            if hae is not None:
                location.position.height_above_ellipsoid_meters = float(hae)  # type: ignore
        except Exception:
            pass

        ontology = Ontology(template="TEMPLATE_TRACK", platform_type="Home Point")
        mil_view = MilView()  # <-- omit env & disposition to avoid enum underscore issues
        provenance = Provenance(
            data_type="home-position",
            integration_name=self.source_name,
            source_update_time=_now_utc().isoformat(),
        )
        expiry_time = _now_utc() + dt.timedelta(hours=4)

        try:
            self.client.entities.publish_entity(
                entity_id=entity_id,
                is_live=True,
                location=location,
                ontology=ontology,
                mil_view=mil_view,
                provenance=provenance,
                aliases=Aliases(name=str(display_name)),
                expiry_time=expiry_time,
                data_classification=Classification(
                    default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")
                ),
                request_options=self._req_opts,
            )
        except Exception as e:
            _log.warning("Lattice publish_home failed for %s: %s", entity_id, e)
