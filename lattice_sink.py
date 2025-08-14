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

import logging, time, datetime as dt
from typing import Optional, Dict, Any

# ---------- Imports ----------
try:
    import anduril
    from anduril import (
        Lattice, Location, Position, MilView, Ontology, Provenance, Aliases,
        Classification, ClassificationInformation,
    )
except Exception as e:
    Lattice = Location = Position = MilView = Ontology = Provenance = Aliases = None  # type: ignore
    Classification = ClassificationInformation = None  # type: ignore
    _IMPORT_ERROR = e
else:
    _IMPORT_ERROR = None

# Optional per-request headers (older SDKs)
try:
    from anduril.core.request_options import RequestOptions
except Exception:
    RequestOptions = None  # type: ignore

_log = logging.getLogger(__name__)
_log.info("LatticeSink ACTIVE. file=%s", __file__)
try:
    _log.info("anduril SDK version: %s", getattr(anduril, "__version__", "unknown"))
except Exception:
    pass

def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)

def _valid_latlon(lat: Optional[float], lon: Optional[float]) -> bool:
    try:
        if lat is None or lon is None: return False
        return -90.0 <= float(lat) <= 90.0 and -180.0 <= float(lon) <= 180.0
    except Exception:
        return False

def _resolve_env_members():
    """
    Try very hard to get the real enum members; otherwise return safe string fallbacks.
    Returns: (ground_val, air_val, provider_label)
    """
    # 1) Nested enum on MilView (most likely)
    try:
        env_enum = getattr(MilView, "Environment", None)  # type: ignore
        if env_enum is not None:
            g = getattr(env_enum, "ENVIRONMENT_GROUND", None)
            a = getattr(env_enum, "ENVIRONMENT_AIR", None)
            if g is not None and a is not None:
                return g, a, "MilView.Environment(enum)"
    except Exception:
        pass

    # 2) Common module locations (defensive)
    for modpath in [
        "anduril.entities.types.mil_view",
        "anduril.entities.v1.mil_view",
        "anduril.types.mil_view",
    ]:
        try:
            mod = __import__(modpath, fromlist=["Environment"])
            env_enum = getattr(mod, "Environment", None)
            if env_enum is not None:
                g = getattr(env_enum, "ENVIRONMENT_GROUND", None)
                a = getattr(env_enum, "ENVIRONMENT_AIR", None)
                if g is not None and a is not None:
                    return g, a, f"{modpath}.Environment(enum)"
        except Exception:
            pass

    # 3) Fallback: **bare** strings (letting SDK prefix properly)
    _log.warning("Could not locate Environment enum; using bare strings ('GROUND','AIR') to avoid underscore bug.")
    return "GROUND", "AIR", "bare-string"

class LatticeSink:
    """
    Publishes entities to Lattice via the Anduril SDK.
    Supports environment token + optional sandboxes token.
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
            _log.info("Lattice client constructed; per-request headers=%s", bool(self._req_opts))

        # Resolve enum/bare values once
        self._env_ground, self._env_air, provider = _resolve_env_members()
        _log.info("MilView.environment provider: %s  (GROUND=%r, AIR=%r)", provider, self._env_ground, self._env_air)

        # Rate limiting
        self._periods = {"drone": 1.0 / max(drone_hz, 1e-6), "wd": 1.0 / max(wardragon_hz, 1e-6), "pilot": 1.0, "home": 1.0}
        self._last_send = {k: 0.0 for k in self._periods.keys()}

    def _rate_ok(self, key: str) -> bool:
        now = time.time()
        if now - self._last_send.get(key, 0.0) >= self._periods.get(key, 0.0):
            self._last_send[key] = now
            return True
        return False

    # --------------------------- WarDragon (ground sensor) ---------------------------
    def publish_system(self, s: Dict[str, Any]) -> None:
        if not self._rate_ok("wd"): return
        serial = str(s.get("serial_number", "unknown")) or "unknown"
        gps = s.get("gps_data", {}) or {}
        lat, lon, hae = gps.get("latitude"), gps.get("longitude"), gps.get("altitude")
        if not _valid_latlon(lat, lon): return

        entity_id = f"wardragon-{serial}"
        loc = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
        try:
            if hae is not None:
                loc.position.height_above_ellipsoid_meters = float(hae)  # type: ignore
        except Exception:
            pass

        mil_view = MilView(environment=self._env_ground, disposition="DISPOSITION_NEUTRAL")
        _log.error("[DBG] system env about to send: %r  type=%s", getattr(mil_view, "environment", None), type(getattr(mil_view, "environment", None)))

        try:
            self.client.entities.publish_entity(
                entity_id=entity_id,
                is_live=True,
                location=loc,
                ontology=Ontology(template="TEMPLATE_TRACK", platform_type="Ground Sensor"),
                mil_view=mil_view,
                provenance=Provenance(data_type="wardragon-status", integration_name=self.source_name, source_update_time=_now_utc().isoformat()),
                aliases=Aliases(display_name=f"WarDragon {serial}"),
                expiry_time=_now_utc() + dt.timedelta(minutes=10),
                data_classification=Classification(default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")),
                request_options=self._req_opts,
            )
        except Exception as e:
            _log.warning(f"Lattice publish_system failed for {entity_id}: {e}")

    # ----------------------------------- Drone (air) --------------------------------
    def publish_drone(self, d: Any) -> None:
        if not self._rate_ok("drone"): return
        g = (lambda k, default=None: getattr(d, k, d.get(k, default)) if isinstance(d, dict) else getattr(d, k, default))
        entity_id = str(g("id", "unknown")) or "unknown"
        lat, lon, hae = g("lat"), g("lon"), g("alt")
        if not _valid_latlon(lat, lon): return

        loc = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
        try:
            if hae is not None:
                loc.position.height_above_ellipsoid_meters = float(hae)  # type: ignore
        except Exception:
            pass

        mil_view = MilView(environment=self._env_air, disposition="DISPOSITION_NEUTRAL")
        _log.error("[DBG] drone env about to send: %r  type=%s", getattr(mil_view, "environment", None), type(getattr(mil_view, "environment", None)))

        try:
            self.client.entities.publish_entity(
                entity_id=entity_id,
                is_live=True,
                location=loc,
                ontology=Ontology(template="TEMPLATE_TRACK", platform_type="Small UAS"),
                mil_view=mil_view,
                provenance=Provenance(data_type="drone-telemetry", integration_name=self.source_name, source_update_time=_now_utc().isoformat()),
                aliases=Aliases(display_name=entity_id),
                expiry_time=_now_utc() + dt.timedelta(minutes=5),
                data_classification=Classification(default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")),
                request_options=self._req_opts,
            )
        except Exception as e:
            _log.warning(f"Lattice publish_drone failed for {entity_id}: {e}")

    # ---------------------------- Pilot & Home (ground) ----------------------------
    def publish_pilot(self, entity_base_id: str, lat: float, lon: float) -> None:
        if not self._rate_ok("pilot"): return
        if not _valid_latlon(lat, lon): return
        loc = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
        mil_view = MilView(environment=self._env_ground, disposition="DISPOSITION_FRIEND")
        _log.error("[DBG] pilot env about to send: %r  type=%s", getattr(mil_view, "environment", None), type(getattr(mil_view, "environment", None)))
        try:
            self.client.entities.publish_entity(
                entity_id=f"{entity_base_id}-pilot",
                is_live=True,
                location=loc,
                ontology=Ontology(template="TEMPLATE_TRACK", platform_type="Operator"),
                mil_view=mil_view,
                provenance=Provenance(data_type="pilot-position", integration_name=self.source_name, source_update_time=_now_utc().isoformat()),
                aliases=Aliases(display_name=f"Pilot of {entity_base_id}"),
                expiry_time=_now_utc() + dt.timedelta(minutes=30),
                data_classification=Classification(default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")),
                request_options=self._req_opts,
            )
        except Exception as e:
            _log.warning(f"Lattice publish_pilot failed for {entity_base_id}: {e}")

    def publish_home(self, entity_base_id: str, lat: float, lon: float) -> None:
        if not self._rate_ok("home"): return
        if not _valid_latlon(lat, lon): return
        loc = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
        mil_view = MilView(environment=self._env_ground, disposition="DISPOSITION_FRIEND")
        _log.error("[DBG] home env about to send: %r  type=%s", getattr(mil_view, "environment", None), type(getattr(mil_view, "environment", None)))
        try:
            self.client.entities.publish_entity(
                entity_id=f"{entity_base_id}-home",
                is_live=True,
                location=loc,
                ontology=Ontology(template="TEMPLATE_TRACK", platform_type="Home Point"),
                mil_view=mil_view,
                provenance=Provenance(data_type="home-position", integration_name=self.source_name, source_update_time=_now_utc().isoformat()),
                aliases=Aliases(display_name=f"Home of {entity_base_id}"),
                expiry_time=_now_utc() + dt.timedelta(hours=4),
                data_classification=Classification(default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")),
                request_options=self._req_opts,
            )
        except Exception as e:
            _log.warning(f"Lattice publish_home failed for {entity_base_id}: {e}")
