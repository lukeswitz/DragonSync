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
import os

# --- Anduril SDK imports & version info ----------------------------------------
try:
    import anduril as _anduril_pkg  # only for __version__
    _SDK_VERSION = getattr(_anduril_pkg, "__version__", "unknown")
except Exception:
    _SDK_VERSION = "unknown"

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

    # Prefer proper enums if the SDK exposes them
    try:
        from anduril import MilViewEnvironment, MilViewDisposition  # SDK >= certain versions
    except Exception:
        MilViewEnvironment = None  # type: ignore
        MilViewDisposition = None  # type: ignore

    # Optional request-level headers (older SDKs don’t accept headers= in ctor)
    try:
        from anduril.core.request_options import RequestOptions
    except Exception:
        RequestOptions = None  # type: ignore

except Exception as e:
    # Defer import failure until someone constructs the sink
    Lattice = None  # type: ignore
    Location = Position = MilView = Ontology = Provenance = Aliases = None  # type: ignore
    Classification = ClassificationInformation = None  # type: ignore
    RequestOptions = None  # type: ignore
    MilViewEnvironment = MilViewDisposition = None  # type: ignore
    _IMPORT_ERROR = e
else:
    _IMPORT_ERROR = None


_log = logging.getLogger("lattice_sink")


# --- helpers -------------------------------------------------------------------
def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _valid_latlon(lat: Optional[float], lon: Optional[float]) -> bool:
    try:
        if lat is None or lon is None:
            return False
        return -90.0 <= float(lat) <= 90.0 and -180.0 <= float(lon) <= 180.0
    except Exception:
        return False


def _mil_env_ground():
    """
    Return a MilView environment value for GROUND:
      - Prefer SDK enum if available
      - Fall back to proto name literal required by backend
    """
    if MilViewEnvironment is not None and hasattr(MilViewEnvironment, "MIL_VIEW_ENVIRONMENT_GROUND"):
        return MilViewEnvironment.MIL_VIEW_ENVIRONMENT_GROUND
    return "MIL_VIEW_ENVIRONMENT_GROUND"


def _mil_env_air():
    if MilViewEnvironment is not None and hasattr(MilViewEnvironment, "MIL_VIEW_ENVIRONMENT_AIR"):
        return MilViewEnvironment.MIL_VIEW_ENVIRONMENT_AIR
    return "MIL_VIEW_ENVIRONMENT_AIR"


def _mil_disp_neutral():
    if MilViewDisposition is not None and hasattr(MilViewDisposition, "DISPOSITION_NEUTRAL"):
        return MilViewDisposition.DISPOSITION_NEUTRAL
    return "DISPOSITION_NEUTRAL"


def _mil_disp_friend():
    if MilViewDisposition is not None and hasattr(MilViewDisposition, "DISPOSITION_FRIEND"):
        return MilViewDisposition.DISPOSITION_FRIEND
    return "DISPOSITION_FRIEND"


def _new_location(lat: float, lon: float, hae: Optional[float]) -> Location:
    """
    Build a Location with a Position and set whichever altitude attribute
    the installed SDK supports.
    """
    loc = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
    if hae is not None:
        try:
            # Newer schema
            if hasattr(loc.position, "altitude_hae_meters"):
                loc.position.altitude_hae_meters = float(hae)  # type: ignore
            # Older schema used this name
            elif hasattr(loc.position, "height_above_ellipsoid_meters"):
                loc.position.height_above_ellipsoid_meters = float(hae)  # type: ignore
        except Exception:
            pass
    return loc


# --- main sink -----------------------------------------------------------------
class LatticeSink:
    """Publisher for entities via the Anduril Lattice SDK.

    - Uses an *environment* token (Authorization) plus an optional *sandbox* token
      sent as the header `anduril-sandbox-authorization: Bearer <token>`.
    - Works across SDKs that either accept client-level `headers=` or require
      per-request headers via RequestOptions.

    Args:
        token: Environment token (ENVIRONMENT_TOKEN / LATTICE_TOKEN).
        base_url: Full URL, e.g. "https://<env>.sandboxes.developer.anduril.com".
        drone_hz: Max drone publish frequency (Hz).
        wardragon_hz: Max WarDragon status publish frequency (Hz).
        source_name: Provenance integration name (e.g., "DragonSync").
        sandbox_token: Optional Sandboxes token to route requests into a sandbox.
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

        # Client-level headers, if supported by this SDK build
        headers = {"anduril-sandbox-authorization": f"Bearer {self._sandbox_token}"} if self._sandbox_token else None
        self._req_opts = None

        try:
            # Primary path
            if base_url:
                self.client = Lattice(token=token, base_url=base_url, headers=headers)  # type: ignore
            else:
                self.client = Lattice(token=token, headers=headers)  # type: ignore
            client_headers = True
        except TypeError:
            # Fallback for SDKs with no headers= in constructor
            if base_url:
                self.client = Lattice(token=token, base_url=base_url)  # type: ignore
            else:
                self.client = Lattice(token=token)  # type: ignore
            client_headers = False

            if self._sandbox_token and RequestOptions is not None:
                self._req_opts = RequestOptions(
                    additional_headers={"anduril-sandbox-authorization": f"Bearer {self._sandbox_token}"}
                )

        # Simple rate limiting
        self._periods = {
            "drone": 1.0 / max(drone_hz, 1e-6),
            "wd": 1.0 / max(wardragon_hz, 1e-6),
            "pilot": 1.0,
            "home": 1.0,
        }
        self._last_send = {k: 0.0 for k in self._periods.keys()}

        # Startup logs for troubleshooting
        _log.info("LatticeSink ACTIVE. file=%s", os.path.abspath(__file__))
        _log.info("anduril SDK version: %s", _SDK_VERSION)
        if MilViewEnvironment is not None:
            _log.info("MilView.environment provider: SDK enums (e.g. MIL_VIEW_ENVIRONMENT_GROUND)")
        else:
            _log.info("MilView.environment provider: proto strings (e.g. 'MIL_VIEW_ENVIRONMENT_GROUND')")
        _log.info("Lattice client constructed with client-level headers=%s", client_headers)

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

        location = _new_location(float(lat), float(lon), hae)
        ontology = Ontology(template="TEMPLATE_TRACK", platform_type="Ground Sensor")

        environment = _mil_env_ground()
        disposition = _mil_disp_neutral()
        _log.debug("[DBG] publish_system env=%r (%s) disp=%r", environment, type(environment), disposition)

        mil_view = MilView(environment=environment, disposition=disposition)
        provenance = Provenance(
            data_type="telemetry",
            integration_name=self.source_name,
            source_update_time=_now_utc(),
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
            _log.warning("Lattice publish_system failed for %s: %s", entity_id, e)

    # ------------------------------- Drone (air track) -------------------------------

    def publish_drone(self, d: Any) -> None:
        """Publish/refresh a drone entity from a Drone object/dict."""
        if not self._rate_ok("drone"):
            return

        # Support both dict and object access
        def g(k, default=None):
            if isinstance(d, dict):
                return d.get(k, default)
            return getattr(d, k, default)

        entity_id = str(g("id", "unknown")) or "unknown"
        lat = g("lat"); lon = g("lon"); hae = g("alt")
        if not _valid_latlon(lat, lon):
            return

        location = _new_location(float(lat), float(lon), hae)
        display = entity_id
        aliases = Aliases(display_name=display)
        ontology = Ontology(template="TEMPLATE_TRACK", platform_type="Small UAS")

        environment = _mil_env_air()
        disposition = _mil_disp_neutral()
        _log.debug("[DBG] publish_drone env=%r (%s) disp=%r", environment, type(environment), disposition)

        mil_view = MilView(environment=environment, disposition=disposition)
        provenance = Provenance(
            data_type="drone-telemetry",
            integration_name=self.source_name,
            source_update_time=_now_utc(),
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

    # ---------------------------- Pilot & Home (ground) ----------------------------

    def publish_pilot(self, entity_base_id: str, lat: float, lon: float) -> None:
        if not self._rate_ok("pilot"):
            return
        if not _valid_latlon(lat, lon):
            return

        entity_id = f"{entity_base_id}-pilot"
        location = _new_location(float(lat), float(lon), None)
        ontology = Ontology(template="TEMPLATE_TRACK", platform_type="Operator")

        environment = _mil_env_ground()
        disposition = _mil_disp_friend()
        _log.debug("[DBG] publish_pilot env=%r (%s) disp=%r", environment, type(environment), disposition)

        mil_view = MilView(environment=environment, disposition=disposition)
        provenance = Provenance(
            data_type="pilot-position",
            integration_name=self.source_name,
            source_update_time=_now_utc(),
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
            _log.warning("Lattice publish_pilot failed for %s: %s", entity_id, e)

    def publish_home(self, entity_base_id: str, lat: float, lon: float) -> None:
        if not self._rate_ok("home"):
            return
        if not _valid_latlon(lat, lon):
            return

        entity_id = f"{entity_base_id}-home"
        location = _new_location(float(lat), float(lon), None)
        ontology = Ontology(template="TEMPLATE_TRACK", platform_type="Home Point")

        environment = _mil_env_ground()
        disposition = _mil_disp_friend()
        _log.debug("[DBG] publish_home env=%r (%s) disp=%r", environment, type(environment), disposition)

        mil_view = MilView(environment=environment, disposition=disposition)
        provenance = Provenance(
            data_type="home-position",
            integration_name=self.source_name,
            source_update_time=_now_utc(),
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
            _log.warning("Lattice publish_home failed for %s: %s", entity_id, e)
