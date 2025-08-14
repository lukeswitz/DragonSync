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

import logging
import time
from typing import Optional, Dict, Any

import datetime as dt

try:
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
    # Prefer the actual enum from the SDK if available
    try:
        from anduril.entities.types.mil_view import Environment as MilEnvironment  # type: ignore
    except Exception:
        MilEnvironment = None  # type: ignore

    # Optional: used if we need per-request headers
    try:
        from anduril.core.request_options import RequestOptions
    except Exception:
        RequestOptions = None  # type: ignore
except Exception as e:
    # Defer import failure until someone actually tries to construct the sink.
    Lattice = None  # type: ignore
    Location = Position = MilView = Ontology = Provenance = Aliases = None  # type: ignore
    Classification = ClassificationInformation = None  # type: ignore
    RequestOptions = None  # type: ignore
    MilEnvironment = None  # type: ignore
    _IMPORT_ERROR = e
else:
    _IMPORT_ERROR = None


_log = logging.getLogger(__name__)


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _valid_latlon(lat: Optional[float], lon: Optional[float]) -> bool:
    try:
        if lat is None or lon is None:
            return False
        return -90.0 <= float(lat) <= 90.0 and -180.0 <= float(lon) <= 180.0
    except Exception:
        return False


def _env(value: str):
    """
    Map loose strings like 'ground', 'AIR' to the proper Lattice enum when available,
    otherwise return the exact string constant expected by the API as a safe fallback.
    """
    v = (value or "").strip().upper().replace("-", "_")
    if MilEnvironment is not None:
        if v in ("GROUND", "ENVIRONMENT_GROUND"):
            return MilEnvironment.ENVIRONMENT_GROUND
        if v in ("AIR", "ENVIRONMENT_AIR"):
            return MilEnvironment.ENVIRONMENT_AIR
        if v in ("SURFACE", "SEA", "ENVIRONMENT_SURFACE"):
            return MilEnvironment.ENVIRONMENT_SURFACE
        if v in ("SUBSURFACE", "UNDERSEA", "ENVIRONMENT_SUBSURFACE"):
            return MilEnvironment.ENVIRONMENT_SUBSURFACE
        if v in ("SPACE", "ENVIRONMENT_SPACE"):
            return MilEnvironment.ENVIRONMENT_SPACE
    # String fallback (exact wire values)
    if v in ("GROUND", "ENVIRONMENT_GROUND"):
        return "ENVIRONMENT_GROUND"
    if v in ("AIR", "ENVIRONMENT_AIR"):
        return "ENVIRONMENT_AIR"
    if v in ("SURFACE", "SEA", "ENVIRONMENT_SURFACE"):
        return "ENVIRONMENT_SURFACE"
    if v in ("SUBSURFACE", "UNDERSEA", "ENVIRONMENT_SUBSURFACE"):
        return "ENVIRONMENT_SUBSURFACE"
    if v in ("SPACE", "ENVIRONMENT_SPACE"):
        return "ENVIRONMENT_SPACE"
    raise ValueError(f"Unknown environment value: {value!r}")


class LatticeSink:
    """Minimal pub helper for entities via the Anduril Lattice SDK.

    - Supports *environment* token (Authorization header) and optional *sandbox* token
      through the custom header `anduril-sandbox-authorization: Bearer <token>`.
    - Mirrors the example app behavior (client-level header), with a safe fallback
      to per-request headers if this SDK build doesn't accept `headers=` on init.

    Args:
        token: Environment token (a.k.a. LATTICE_TOKEN / ENVIRONMENT_TOKEN).
        base_url: Full base URL, e.g. "https://your-sandbox.anduril.cloud".
        drone_hz: Max drone publish frequency (Hz).
        wardragon_hz: Max WarDragon status publish frequency (Hz).
        source_name: Provenance integration name (e.g. "DragonSync").
        sandbox_token: Optional Sandboxes token to route into a specific sandbox.
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

        # Build client with client-level headers if supported; otherwise fall back
        headers = {"anduril-sandbox-authorization": f"Bearer {self._sandbox_token}"} if self._sandbox_token else None
        self._req_opts = None
        try:
            # primary path (matches example app)
            if base_url:
                self.client = Lattice(token=token, base_url=base_url, headers=headers)  # type: ignore
            else:
                self.client = Lattice(token=token, headers=headers)  # type: ignore
        except TypeError:
            # fallback path: older SDKs without headers= on constructor
            if base_url:
                self.client = Lattice(token=token, base_url=base_url)  # type: ignore
            else:
                self.client = Lattice(token=token)  # type: ignore

            if self._sandbox_token and RequestOptions is not None:
                self._req_opts = RequestOptions(
                    additional_headers={"anduril-sandbox-authorization": f"Bearer {self._sandbox_token}"}
                )

        # simple rate limiters
        self._periods = {
            "drone": 1.0 / max(drone_hz, 1e-6),
            "wd": 1.0 / max(wardragon_hz, 1e-6),
            "pilot": 1.0,  # reasonable default
            "home": 1.0,
        }
        self._last_send = {k: 0.0 for k in self._periods.keys()}

    def _rate_ok(self, key: str) -> bool:
        now = time.time()
        if now - self._last_send.get(key, 0.0) >= self._periods.get(key, 0.0):
            self._last_send[key] = now
            return True
        return False

    # --------------------------- WarDragon (ground sensor) ---------------------------

    def publish_system(self, s: Dict[str, Any]) -> None:
        """Publish WarDragon ground-sensor status as a track in GROUND env."""
        if not self._rate_ok("wd"):
            return

        serial = str(s.get("serial_number", "unknown")) or "unknown"
        gps = s.get("gps_data", {}) or {}
        lat = gps.get("latitude"); lon = gps.get("longitude"); hae = gps.get("altitude")
        if not _valid_latlon(lat, lon):
            return

        entity_id = f"wardragon-{serial}"
        display = f"WarDragon {serial}"

        # Typed components
        location = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
        # Altitude is optional; include if present and numeric
        try:
            if hae is not None:
                location.position.height_above_ellipsoid_meters = float(hae)  # type: ignore
        except Exception:
            pass

        ontology = Ontology(template="TEMPLATE_TRACK", platform_type="Ground Sensor")
        # >>> enum-safe environment <<<
        mil_view = MilView(environment=_env("GROUND"), disposition="DISPOSITION_NEUTRAL")
        provenance = Provenance(
            data_type="wardragon-status",
            integration_name=self.source_name,
            source_update_time=_now_utc().isoformat(),
        )
        aliases = Aliases(display_name=display)
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
                request_options=self._req_opts,  # no-op if None
            )
        except Exception as e:
            _log.warning(f"Lattice publish_system failed for {entity_id}: {e}")

    # ------------------------------- Drone (air track) -------------------------------

    def publish_drone(self, d: Any) -> None:
        """Publish/refresh a drone entity from your Drone object/dict."""
        if not self._rate_ok("drone"):
            return

        # Support both object and dict
        g = (lambda k, default=None: getattr(d, k, d.get(k, default)) if isinstance(d, dict) else getattr(d, k, default))

        entity_id = str(g("id", "unknown")) or "unknown"
        lat = g("lat"); lon = g("lon"); hae = g("alt")
        if not _valid_latlon(lat, lon):
            return

        # Build typed components
        location = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
        try:
            if hae is not None:
                location.position.height_above_ellipsoid_meters = float(hae)  # type: ignore
        except Exception:
            pass

        display = entity_id
        aliases = Aliases(display_name=display)
        ontology = Ontology(template="TEMPLATE_TRACK", platform_type="Small UAS")
        # >>> enum-safe environment <<<
        mil_view = MilView(environment=_env("AIR"), disposition="DISPOSITION_NEUTRAL")
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
            _log.warning(f"Lattice publish_drone failed for {entity_id}: {e}")

    # ---------------------------- Pilot & Home (ground) ----------------------------

    def publish_pilot(self, entity_base_id: str, lat: float, lon: float) -> None:
        if not self._rate_ok("pilot"):
            return
        if not _valid_latlon(lat, lon):
            return

        entity_id = f"{entity_base_id}-pilot"
        location = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
        ontology = Ontology(template="TEMPLATE_TRACK", platform_type="Operator")
        # >>> enum-safe environment <<<
        mil_view = MilView(environment=_env("GROUND"), disposition="DISPOSITION_FRIEND")
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
                aliases=Aliases(display_name=f"Pilot of {entity_base_id}"),
                expiry_time=expiry_time,
                data_classification=Classification(
                    default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")
                ),
                request_options=self._req_opts,
            )
        except Exception as e:
            _log.warning(f"Lattice publish_pilot failed for {entity_id}: {e}")

    def publish_home(self, entity_base_id: str, lat: float, lon: float) -> None:
        if not self._rate_ok("home"):
            return
        if not _valid_latlon(lat, lon):
            return

        entity_id = f"{entity_base_id}-home"
        location = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
        ontology = Ontology(template="TEMPLATE_TRACK", platform_type="Home Point")
        # >>> enum-safe environment <<<
        mil_view = MilView(environment=_env("GROUND"), disposition="DISPOSITION_FRIEND")
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
                aliases=Aliases(display_name=f"Home of {entity_base_id}"),
                expiry_time=expiry_time,
                data_classification=Classification(
                    default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")
                ),
                request_options=self._req_opts,
            )
        except Exception as e:
            _log.warning(f"Lattice publish_home failed for {entity_id}: {e}")
