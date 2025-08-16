# MIT License
#
# Copyright (c) 2024 cemaxecuter
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

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
    # Defer import failure until someone actually tries to construct the sink.
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

    We prefer the SDK enum where available; fall back to the proto string that
    is known-good in examples.
    """
    if MilEnvironment is not None:
        # Try both common enum names across SDKs
        for attr in (
            "MIL_VIEW_ENVIRONMENT_AIR",
            "ENVIRONMENT_AIR",
        ):
            if hasattr(MilEnvironment, attr):
                return getattr(MilEnvironment, attr)
    return "ENVIRONMENT_AIR"


def _coalesce_str(*vals: Any) -> Optional[str]:
    """Return the first non-empty string-ish value, else None."""
    for v in vals:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


# ────────────────────────────────────────────────────────────────────────────────
# LatticeSink
# ────────────────────────────────────────────────────────────────────────────────
class LatticeSink:
    """
    Minimal publisher for entities via the Anduril Lattice SDK.

    - Uses the *environment* token (Authorization header) and optional *sandbox*
      token via 'anduril-sandbox-authorization: Bearer <token>'.
    - For WarDragon/pilot/home (ground), we intentionally **omit** MilView.environment
      due to sandbox enum parsing issues; server defaults are used.
    - For drones (air), we still set MilView.environment to AIR.
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
            if base_url:
                self.client = Lattice(token=token, base_url=base_url, headers=headers)  # type: ignore
            else:
                self.client = Lattice(token=token, headers=headers)  # type: ignore
            _log.info("LatticeSink ACTIVE. file=%s", os.path.abspath(__file__))
            _log.info("anduril SDK version: %s", _SDK_VERSION)
            _log.info("Lattice client constructed with client-level headers=%s", bool(headers))
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
            _log.info("LatticeSink ACTIVE. file=%s", os.path.abspath(__file__))
            _log.info("anduril SDK version: %s", _SDK_VERSION)
            _log.info(
                "Lattice client constructed with client-level headers=%s; per-request headers=%s",
                False,
                bool(self._req_opts),
            )

        # Simple rate limiters
        self._periods = {
            "drone": 1.0 / max(drone_hz, 1e-6),
            "wd": 1.0 / max(wardragon_hz, 1e-6),
            "pilot": 1.0,   # 1 Hz cap is plenty
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
        Publish WarDragon ground-sensor status as a track + health text.
        NOTE: We OMIT MilView.environment to rely on server defaults.
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

        # Location / position
        location = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
        try:
            if hae is not None:
                # Height above ellipsoid is optional; ignore parse failure
                location.position.height_above_ellipsoid_meters = float(hae)  # type: ignore[attr-defined]
        except Exception:
            pass

        ontology = Ontology(template="TEMPLATE_TRACK", platform_type="Ground Sensor")
        # Keep disposition NEUTRAL, omit environment (enum differences across sandboxes)
        mil_view = MilView(disposition="DISPOSITION_NEUTRAL")

        # ---- Build health/status from system_stats if present (TEXT-ONLY, no enums) ----
        stats = (s.get("system_stats") or {})
        mem = (stats.get("memory") or {})
        disk = (stats.get("disk") or {})
        temps = (s.get("ant_sdr_temps") or {})

        def _f(x, default=0.0):
            try:
                return float(x)
            except Exception:
                return default

        cpu = _f(stats.get("cpu_usage"))
        mem_total = _f(mem.get("total"))
        mem_avail = _f(mem.get("available"))
        mem_used_pct = (100.0 * (1.0 - (mem_avail / mem_total))) if mem_total > 0 else None

        disk_total = _f(disk.get("total"))
        disk_used = _f(disk.get("used"))
        disk_used_pct = (100.0 * (disk_used / disk_total)) if disk_total > 0 else None

        box_temp = _f(stats.get("temperature"))  # overall system temp if provided
        uptime_s = _f(stats.get("uptime"))

        def _parse_temp(v):
            try:
                s = str(v)
                for cut in ("°C", "C", "c", "degC"):
                    s = s.replace(cut, "")
                return float(s.strip())
            except Exception:
                return None

        pluto_temp = _parse_temp(temps.get("pluto_temp"))
        zynq_temp = _parse_temp(temps.get("zynq_temp"))

        # Build a short roll-up line (no enums)
        parts = [f"CPU {cpu:.0f}%"]
        if mem_used_pct is not None:
            parts.append(f"Mem {mem_used_pct:.0f}%")
        if disk_used_pct is not None:
            parts.append(f"Disk {disk_used_pct:.0f}%")
        if box_temp:
            parts.append(f"T {box_temp:.0f}°C")
        if pluto_temp is not None:
            parts.append(f"Pluto {pluto_temp:.0f}°C")
        if zynq_temp is not None:
            parts.append(f"Zynq {zynq_temp:.0f}°C")
        if uptime_s:
            parts.append(f"Up {uptime_s/3600:.1f}h")
        status_msg = " | ".join(parts) if parts else "OK"

        # Compose a description that shows in the UI
        description = f"{alias_name} — {status_msg}"

        # status {code,message} is commonly accepted; use a soft heuristic code
        # (no enum here, just int). 0=OK,1=Warn,2=Crit (based on CPU/mem/disk/temp).
        sev = 0
        def bump(level):
            nonlocal sev
            sev = max(sev, level)

        if cpu >= 90: bump(2)
        elif cpu >= 75: bump(1)
        if mem_used_pct is not None:
            if mem_used_pct >= 90: bump(2)
            elif mem_used_pct >= 80: bump(1)
        if disk_used_pct is not None:
            if disk_used_pct >= 95: bump(2)
            elif disk_used_pct >= 85: bump(1)
        for t in (box_temp, pluto_temp, zynq_temp):
            if t is not None:
                if t >= 85: bump(2)
                elif t >= 75: bump(1)

        status_payload = {"code": int(sev), "message": status_msg}

        # TEXT-ONLY health (no enum fields: no connectionStatus, no healthStatus, no per-component health/status)
        now_iso = _now_utc().isoformat()
        components = [
            {
                "id": "cpu",
                "name": "CPU",
                "messages": [{"message": f"Usage {cpu:.0f}%"}],
                "updateTime": now_iso,
            },
        ]
        if mem_used_pct is not None:
            components.append({
                "id": "memory",
                "name": "Memory",
                "messages": [{"message": f"Used {mem_used_pct:.0f}%"}],
                "updateTime": now_iso,
            })
        if disk_used_pct is not None:
            components.append({
                "id": "disk",
                "name": "Disk",
                "messages": [{"message": f"Used {disk_used_pct:.0f}%"}],
                "updateTime": now_iso,
            })
        if box_temp:
            components.append({
                "id": "chassis_temp",
                "name": "Chassis Temp",
                "messages": [{"message": f"{box_temp:.0f}°C"}],
                "updateTime": now_iso,
            })
        if pluto_temp is not None:
            components.append({
                "id": "pluto_temp",
                "name": "Pluto SDR Temp",
                "messages": [{"message": f"{pluto_temp:.0f}°C"}],
                "updateTime": now_iso,
            })
        if zynq_temp is not None:
            components.append({
                "id": "zynq_temp",
                "name": "Zynq Temp",
                "messages": [{"message": f"{zynq_temp:.0f}°C"}],
                "updateTime": now_iso,
            })

        health_payload = {
            "components": components,
            "updateTime": now_iso,
            # activeAlerts omitted for now
        }

        provenance = Provenance(
            data_type="telemetry",
            integration_name=self.source_name,
            source_update_time=now_iso,
            source_description=description,  # also useful in some UIs
        )
        aliases = Aliases(name=alias_name)
        expiry_time = _now_utc() + dt.timedelta(minutes=10)

        # Try with rich fields; if this sandbox build still dislikes health, we'll still fall back.
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
                description=description,
                status=status_payload,
                health=health_payload,
                data_classification=Classification(
                    default=ClassificationInformation(level="CLASSIFICATION_LEVELS_UNCLASSIFIED")
                ),
                request_options=self._req_opts,  # no-op if None
            )
            return
        except TypeError:
            _log.info("publish_entity: description/status/health not supported in this SDK; retrying without.")
        except Exception as e:
            _log.warning("Lattice publish_system (rich) failed for %s: %s", entity_id, e)

        # Fallback: minimal, widely-compatible payload
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

        Accepts either:
          - a dict snapshot (what manager.py sends), or
          - a Drone object (attributes accessed via getattr)
        Only present fields are used; RemoteID/DroneID bits are added to description/status
        IF they exist (no assumptions).
        """
        if not self._rate_ok("drone"):
            return

        # Supports dict or object attr access
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

        # Location
        location = Location(position=Position(latitude_degrees=float(lat), longitude_degrees=float(lon)))
        try:
            if hae is not None:
                location.position.height_above_ellipsoid_meters = float(hae)  # type: ignore[attr-defined]
        except Exception:
            pass

        aliases = Aliases(name=entity_id)
        ontology = Ontology(template="TEMPLATE_TRACK", platform_type="Small UAS")

        # Keep environment=AIR (works in other examples)
        mil_view = MilView(
            environment=_air_env_value(),
            disposition="DISPOSITION_NEUTRAL",
        )

        # Optional enrichments (RemoteID/DroneID) — only if present
        id_type = g("id_type")
        ua_type_name = g("ua_type_name")
        ua_type = g("ua_type")
        operator_id_type = g("operator_id_type")
        operator_id = g("operator_id")
        mac = g("mac")
        rssi = g("rssi")
        speed = g("speed")
        vspeed = g("vspeed")
        direction = g("direction")
        caa_id = g("caa_id") or g("caa")
        index = g("index")
        runtime = g("runtime")

        desc_parts = []
        if id_type:
            desc_parts.append(f"ID:{id_type}")
        if ua_type_name or ua_type is not None:
            if ua_type_name and ua_type is not None:
                desc_parts.append(f"UA:{ua_type_name}({ua_type})")
            elif ua_type_name:
                desc_parts.append(f"UA:{ua_type_name}")
            else:
                desc_parts.append(f"UA:{ua_type}")
        if operator_id or operator_id_type:
            desc_parts.append(f"OpID:{operator_id_type or ''} {operator_id or ''}".strip())
        if caa_id:
            desc_parts.append(f"CAA:{caa_id}")
        if mac:
            desc_parts.append(f"MAC:{mac}")
        if rssi is not None:
            try:
                desc_parts.append(f"RSSI:{int(rssi)}dBm")
            except Exception:
                pass
        if speed is not None:
            try:
                desc_parts.append(f"Spd:{float(speed):.1f}m/s")
            except Exception:
                pass
        if vspeed is not None:
            try:
                desc_parts.append(f"VSpd:{float(vspeed):.1f}m/s")
            except Exception:
                pass
        if direction is not None:
            try:
                desc_parts.append(f"Crse:{float(direction):.0f}°")
            except Exception:
                pass
        if index is not None:
            desc_parts.append(f"Idx:{index}")
        if runtime is not None:
            try:
                desc_parts.append(f"Up:{float(runtime)/60:.1f}m")
            except Exception:
                pass

        description = _coalesce_str(" | ".join([p for p in desc_parts if p]), entity_id)

        # Lightweight status: 0/1/2 based on RSSI (if present)
        status_code = 0
        status_msg = None
        try:
            if rssi is not None:
                rssi_val = float(rssi)
                if rssi_val <= -90:
                    status_code = 2
                elif rssi_val <= -75:
                    status_code = 1
                status_msg = f"RSSI {int(rssi_val)} dBm"
        except Exception:
            pass
        if status_msg is None and speed is not None:
            try:
                status_msg = f"Speed {float(speed):.1f} m/s"
            except Exception:
                pass

        provenance = Provenance(
            data_type="drone-telemetry",
            integration_name=self.source_name,
            source_update_time=_now_utc().isoformat(),
            source_description=description or entity_id,
        )
        expiry_time = _now_utc() + dt.timedelta(minutes=5)

        # Try to publish with description/status if supported
        try:
            kwargs = dict(
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
            if description:
                kwargs["description"] = description
            if status_msg is not None:
                kwargs["status"] = {"code": int(status_code), "message": status_msg}

            self.client.entities.publish_entity(**kwargs)
            return
        except TypeError:
            _log.info("publish_entity (drone): description/status not supported; retrying without.")
        except Exception as e:
            _log.warning("Lattice publish_drone (rich) failed for %s: %s", entity_id, e)

        # Fallback minimal publish
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
        # OMIT environment & disposition to avoid enum/underscore mismatch
        mil_view = MilView()

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
        # OMIT environment & disposition to avoid enum/underscore mismatch
        mil_view = MilView()

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
