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

import logging, time, json
import datetime as dt
from typing import Optional, Dict, Any, Tuple

# ---------- SDK imports (best-effort) ----------
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

import httpx

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
        if lat is None or lon is None:
            return False
        return -90.0 <= float(lat) <= 90.0 and -180.0 <= float(lon) <= 180.0
    except Exception:
        return False

class LatticeSink:
    """
    Publishes entities to Lattice via the Anduril SDK with a robust HTTP fallback.
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

        self._token = (token or "").strip()
        self._base_url = (base_url or "").strip().rstrip("/")
        self._sandbox_token = (sandbox_token or "").strip() or None
        self.source_name = source_name

        headers = {"anduril-sandbox-authorization": f"Bearer {self._sandbox_token}"} if self._sandbox_token else None
        self._req_opts = None
        try:
            if self._base_url:
                self.client = Lattice(token=self._token, base_url=self._base_url, headers=headers)  # type: ignore
            else:
                self.client = Lattice(token=self._token, headers=headers)  # type: ignore
            _log.info("Lattice client constructed with client-level headers=%s", bool(headers))
        except TypeError:
            if self._base_url:
                self.client = Lattice(token=self._token, base_url=self._base_url)  # type: ignore
            else:
                self.client = Lattice(token=self._token)  # type: ignore
            if self._sandbox_token and RequestOptions is not None:
                self._req_opts = RequestOptions(
                    additional_headers={"anduril-sandbox-authorization": f"Bearer {self._sandbox_token}"}
                )
            _log.info("Lattice client constructed; per-request headers=%s", bool(self._req_opts))

        self._periods = {
            "drone": 1.0 / max(drone_hz, 1e-6),
            "wd": 1.0 / max(wardragon_hz, 1e-6),
            "pilot": 1.0,
            "home": 1.0,
        }
        self._last_send = {k: 0.0 for k in self._periods.keys()}

    # ----------------- helpers -----------------
    def _rate_ok(self, key: str) -> bool:
        now = time.time()
        if now - self._last_send.get(key, 0.0) >= self._periods.get(key, 0.0):
            self._last_send[key] = now
            return True
        return False

    def _http_headers(self) -> Dict[str, str]:
        h = {
            "authorization": f"Bearer {self._token}",
            "content-type": "application/json",
        }
        if self._sandbox_token:
            h["anduril-sandbox-authorization"] = f"Bearer {self._sandbox_token}"
        return h

    def _common_json(
        self,
        *,
        entity_id: str,
        display: str,
        ontology_template: str,
        platform_type: str,
        lat: float,
        lon: float,
        hae: Optional[float],
        env_value: Any,
        disposition_value: Any,
        ttl_minutes: int,
    ) -> Dict[str, Any]:
        pos = {"latitudeDegrees": float(lat), "longitudeDegrees": float(lon)}
        if hae is not None:
            pos["heightAboveEllipsoidMeters"] = float(hae)

        return {
            "entityId": entity_id,
            "isLive": True,
            "location": {"position": pos},
            "ontology": {"template": ontology_template, "platformType": platform_type},
            "milView": {"environment": env_value, "disposition": disposition_value},
            "provenance": {
                "dataType": "telemetry",
                "integrationName": self.source_name,
                "sourceUpdateTime": _now_utc().isoformat(),
            },
            "aliases": {"displayName": display},
            "expiryTime": (_now_utc() + dt.timedelta(minutes=ttl_minutes)).isoformat(),
            "dataClassification": {"default": {"level": "CLASSIFICATION_LEVELS_UNCLASSIFIED"}},
        }

    def _http_put_entity(self, payload: Dict[str, Any]) -> Tuple[int, str]:
        url = f"{self._base_url}/api/v1/entities"
        # log compact payload to see exactly what we send
        _log.error("HTTP payload -> %s", json.dumps(payload, separators=(",", ":")))
        r = httpx.put(url, json=payload, headers=self._http_headers(), timeout=60)
        return r.status_code, r.text

    def _http_try_env_variants(
        self,
        *,
        entity_id: str,
        display: str,
        ontology_template: str,
        platform_type: str,
        lat: float,
        lon: float,
        hae: Optional[float],
        ttl_minutes: int,
        ground: bool,
    ) -> None:
        # Order of attempts for milView.environment
        preferred = "ENVIRONMENT_GROUND" if ground else "ENVIRONMENT_AIR"
        variants: Tuple[str, Any] = (
            ("ENUM_CANON", preferred),
            ("BARE", preferred.replace("ENVIRONMENT_", "")),             # "GROUND"/"AIR"
            ("NO_UNDERSCORE", preferred.replace("_", "")),               # "ENVIRONMENTGROUND"
            ("ENUM_NUM_1", 1),
            ("ENUM_NUM_2", 2),
        )
        for label, env_val in variants:
            payload = self._common_json(
                entity_id=entity_id,
                display=display,
                ontology_template=ontology_template,
                platform_type=platform_type,
                lat=lat,
                lon=lon,
                hae=hae,
                env_value=env_val,
                disposition_value="DISPOSITION_NEUTRAL" if ground else "DISPOSITION_NEUTRAL",
                ttl_minutes=ttl_minutes,
            )
            try:
                code, text = self._http_put_entity(payload)
                if 200 <= code < 300:
                    _log.info("HTTP fallback publish OK via %s (status=%s)", label, code)
                    return
                _log.warning("HTTP %s failed: %s %s", label, code, text)
            except Exception as e:
                _log.warning("HTTP %s exception: %s", label, e)

        _log.error("All HTTP environment variants failed for %s.", entity_id)

    # ----------------- publishers -----------------
    def publish_system(self, s: Dict[str, Any]) -> None:
        if not self._rate_ok("wd"):
            return
        serial = str(s.get("serial_number", "unknown")) or "unknown"
        gps = s.get("gps_data", {}) or {}
        lat, lon, hae = gps.get("latitude"), gps.get("longitude"), gps.get("altitude")
        if not _valid_latlon(lat, lon):
            return

        entity_id = f"wardragon-{serial}"
        display = f"WarDragon {serial}"

        # SDK first
        try:
            loc = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
            try:
                if hae is not None:
                    loc.position.height_above_ellipsoid_meters = float(hae)  # type: ignore
            except Exception:
                pass
            mv = MilView(environment="ENVIRONMENT_GROUND", disposition="DISPOSITION_NEUTRAL")
            self.client.entities.publish_entity(
                entity_id=entity_id,
                is_live=True,
                location=loc,
                ontology=Ontology(template="TEMPLATE_TRACK", platform_type="Ground Sensor"),
                mil_view=mv,
                provenance=Provenance(
                    data_type="wardragon-status",
                    integration_name=self.source_name,
                    source_update_time=_now_utc().isoformat(),
                ),
                aliases=Aliases(display_name=display),
                expiry_time=_now_utc() + dt.timedelta(minutes=10),
                data_classification=Classification(
                    default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")
                ),
                request_options=self._req_opts,
            )
            return
        except Exception as e:
            _log.warning("SDK publish_system failed (%s). Falling back to HTTP.", e)

        self._http_try_env_variants(
            entity_id=entity_id,
            display=display,
            ontology_template="TEMPLATE_TRACK",
            platform_type="Ground Sensor",
            lat=float(lat),
            lon=float(lon),
            hae=float(hae) if hae is not None else None,
            ttl_minutes=10,
            ground=True,
        )

    def publish_drone(self, d: Any) -> None:
        if not self._rate_ok("drone"):
            return
        g = (lambda k, default=None: getattr(d, k, d.get(k, default)) if isinstance(d, dict) else getattr(d, k, default))
        entity_id = str(g("id", "unknown")) or "unknown"
        lat, lon, hae = g("lat"), g("lon"), g("alt")
        if not _valid_latlon(lat, lon):
            return

        display = entity_id

        # SDK first
        try:
            loc = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
            try:
                if hae is not None:
                    loc.position.height_above_ellipsoid_meters = float(hae)  # type: ignore
            except Exception:
                pass
            mv = MilView(environment="ENVIRONMENT_AIR", disposition="DISPOSITION_NEUTRAL")
            self.client.entities.publish_entity(
                entity_id=entity_id,
                is_live=True,
                location=loc,
                ontology=Ontology(template="TEMPLATE_TRACK", platform_type="Small UAS"),
                mil_view=mv,
                provenance=Provenance(
                    data_type="drone-telemetry",
                    integration_name=self.source_name,
                    source_update_time=_now_utc().isoformat(),
                ),
                aliases=Aliases(display_name=display),
                expiry_time=_now_utc() + dt.timedelta(minutes=5),
                data_classification=Classification(
                    default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")
                ),
                request_options=self._req_opts,
            )
            return
        except Exception as e:
            _log.warning("SDK publish_drone failed (%s). Falling back to HTTP.", e)

        self._http_try_env_variants(
            entity_id=entity_id,
            display=display,
            ontology_template="TEMPLATE_TRACK",
            platform_type="Small UAS",
            lat=float(lat),
            lon=float(lon),
            hae=float(hae) if hae is not None else None,
            ttl_minutes=5,
            ground=False,
        )

    def publish_pilot(self, entity_base_id: str, lat: float, lon: float) -> None:
        if not self._rate_ok("pilot"):
            return
        if not _valid_latlon(lat, lon):
            return
        entity_id = f"{entity_base_id}-pilot"
        display = f"Pilot of {entity_base_id}"

        try:
            loc = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
            mv = MilView(environment="ENVIRONMENT_GROUND", disposition="DISPOSITION_FRIEND")
            self.client.entities.publish_entity(
                entity_id=entity_id,
                is_live=True,
                location=loc,
                ontology=Ontology(template="TEMPLATE_TRACK", platform_type="Operator"),
                mil_view=mv,
                provenance=Provenance(
                    data_type="pilot-position",
                    integration_name=self.source_name,
                    source_update_time=_now_utc().isoformat(),
                ),
                aliases=Aliases(display_name=display),
                expiry_time=_now_utc() + dt.timedelta(minutes=30),
                data_classification=Classification(
                    default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")
                ),
                request_options=self._req_opts,
            )
            return
        except Exception as e:
            _log.warning("SDK publish_pilot failed (%s). Falling back to HTTP.", e)

        self._http_try_env_variants(
            entity_id=entity_id,
            display=display,
            ontology_template="TEMPLATE_TRACK",
            platform_type="Operator",
            lat=float(lat),
            lon=float(lon),
            hae=None,
            ttl_minutes=30,
            ground=True,
        )

    def publish_home(self, entity_base_id: str, lat: float, lon: float) -> None:
        if not self._rate_ok("home"):
            return
        if not _valid_latlon(lat, lon):
            return
        entity_id = f"{entity_base_id}-home"
        display = f"Home of {entity_base_id}"

        try:
            loc = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
            mv = MilView(environment="ENVIRONMENT_GROUND", disposition="DISPOSITION_FRIEND")
            self.client.entities.publish_entity(
                entity_id=entity_id,
                is_live=True,
                location=loc,
                ontology=Ontology(template="TEMPLATE_TRACK", platform_type="Home Point"),
                mil_view=mv,
                provenance=Provenance(
                    data_type="home-position",
                    integration_name=self.source_name,
                    source_update_time=_now_utc().isoformat(),
                ),
                aliases=Aliases(display_name=display),
                expiry_time=_now_utc() + dt.timedelta(hours=4),
                data_classification=Classification(
                    default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")
                ),
                request_options=self._req_opts,
            )
            return
        except Exception as e:
            _log.warning("SDK publish_home failed (%s). Falling back to HTTP.", e)

        self._http_try_env_variants(
            entity_id=entity_id,
            display=display,
            ontology_template="TEMPLATE_TRACK",
            platform_type="Home Point",
            lat=float(lat),
            lon=float(lon),
            hae=None,
            ttl_minutes=240,
            ground=True,
        )
