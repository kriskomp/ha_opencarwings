"""Sensor platform for OpenCARWINGS listing cars."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, cast, List
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import ATTR_ATTRIBUTION, PERCENTAGE
from homeassistant.helpers.update_coordinator import CoordinatorEntity

try:
    from homeassistant.helpers.entity import EntityCategory
except Exception:  # pragma: no cover
    class EntityCategory:  # type: ignore
        DIAGNOSTIC = "diagnostic"

try:
    from homeassistant.components.sensor import SensorDeviceClass
except Exception:  # pragma: no cover
    class SensorDeviceClass:  # type: ignore
        BATTERY = "battery"
        DURATION = "duration"
        ENERGY = "energy"
        TEMPERATURE = "temperature"
        TIMESTAMP = "timestamp"

from . import DOMAIN
from .freshness import (
    as_datetime,
    command_summary,
    data_age_minutes,
    data_timestamp,
    driving_unconfirmed,
    format_local,
    format_minutes,
)
from .options import track_location_enabled
from .ticker import track_minute
from .util import CarData

_LOGGER = logging.getLogger(__name__)


# -----------------------------
# Helpers
# -----------------------------

def _parse_ts(value: str | None):
    if not value:
        return None
    try:
        # support ISO8601 like `2026-01-04T12:00:00Z` or with microseconds `...10.419903Z`
        if value.endswith("Z"):
            try:
                return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            except ValueError:
                return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(value)
    except Exception as e:
        _LOGGER.exception(e)
        return None


def _ev_getter(key: str, fallback: str | None = None) -> Callable[[CarData], Any]:
    """Get value from car['ev_info'][key], falling back to car[fallback] or car[key]."""
    def _get(car: CarData):
        car_inf = car.get_latest_car()
        if car_inf is not None:
            if fallback:
                return car_inf.to_dict().get(fallback)
            ev = car_inf.ev_info.to_dict() or {}
            if isinstance(ev, dict) and key in ev:
                return ev.get(key)
            return car_inf.to_dict().get(key)
    return _get

def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        try:
            return float(s)
        except Exception:
            return None

def _round_1(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return round(float(v), 1)
    except Exception:
        return None

# -----------------------------
# Base per-car entity
# -----------------------------

class OpenCarwingsCarEntity(CoordinatorEntity):
    """Base entity for a single car identified by VIN.

    - merges seed car dict (from initial cars list) with coordinator car dict
      so fields like odometer don't disappear if coordinator payload is missing them
    """

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: CarData | None = None) -> None:
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._vin = vin
        self._seed_car = seed_car

    def _get_car(self) -> CarData:
        if self.coordinator and getattr(self.coordinator, "data", None):
            for c in self.coordinator.data:
                if c.vin == self._vin:
                    return c or CarData(self._vin)
        return self._seed_car or CarData(self._vin)

    def _get_car_dict(self) -> dict:
        car_info = self._get_car().get_latest_car()
        if car_info is None:
            return {}
        return car_info.to_dict()

    @property
    def device_info(self) -> dict[str, Any]:
        return self._get_car().car_model_data()



@dataclass(frozen=True)
class CarSensorSpec:
    key: str
    name: str
    value: Callable[[CarData], Any]
    transform: Optional[Callable[[Any], Any]] = None
    device_class: Optional[str] = None
    unit_of_measurement: Optional[str] = None
    as_duration: bool = False  # value is minutes, shown as text like "2 h 30 min"
    diagnostic: bool = False  # fixed facts about the car, not measurements: shown in the diagnostic section


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        return None

def _to_chgtime(v: Any) -> int | None:
    if v is None or (v == 2047 or v == 4095):
        return None
    try:
        return int(v)
    except Exception:
        return None

def _plugged_to_str(v: Any) -> str:
    return "plugged" if bool(v) else "unplugged"


CAR_SENSORS: list[CarSensorSpec] = [
    CarSensorSpec(
        "range_acon",
        "Range (A/C on)",
        _ev_getter("range_acon"),
        transform=_to_float,
        unit_of_measurement="km",
    ),
    CarSensorSpec(
        "range_acoff",
        "Range (A/C off)",
        _ev_getter("range_acoff"),
        transform=_to_float,
        unit_of_measurement="km",
    ),
    CarSensorSpec("soc", "State of Charge", _ev_getter("soc"), transform=_round_1, device_class=SensorDeviceClass.BATTERY, unit_of_measurement=PERCENTAGE),
    CarSensorSpec("soh", "State of Health", _ev_getter("soh"), transform=_round_1, device_class=SensorDeviceClass.BATTERY, unit_of_measurement=PERCENTAGE),
    CarSensorSpec("soc_display", "State of Charge Display", _ev_getter("soc_display"), transform=_round_1, device_class=SensorDeviceClass.BATTERY, unit_of_measurement=PERCENTAGE),
    CarSensorSpec("charge_bars", "Charge Bars", _ev_getter("charge_bars")),
    CarSensorSpec("capacity_bars", "Capacity Bars", _ev_getter("cap_bars")),
    CarSensorSpec("gids", "GIDs", _ev_getter("gids")),
    CarSensorSpec("max_gids", "Maximum GIDs when battery is new", _ev_getter("max_gids")),
    CarSensorSpec("plugged_in", "Charge Cable", _ev_getter("plugged_in"), transform=_plugged_to_str),
    CarSensorSpec("charging", "Charging", _ev_getter("charging")),
    CarSensorSpec("charge_finish", "Charge Finish", _ev_getter("charge_finish")),
    CarSensorSpec("quick_charging", "Quick Charging", _ev_getter("quick_charging")),
    CarSensorSpec("ac_status", "AC Status", _ev_getter("ac_status")),
    CarSensorSpec("eco_mode", "Eco Mode", _ev_getter("eco_mode")),
    CarSensorSpec("car_running", "Running", _ev_getter("car_running")),
    CarSensorSpec("odometer", "Odometer", _ev_getter("", fallback="odometer"), transform=_to_int, unit_of_measurement="km"),
    CarSensorSpec("last_requested_command", "Last Requested Command", _ev_getter("", fallback="command_type_display")),
    CarSensorSpec("full_chg_time", "3 kW/240 V Charge Time", _ev_getter("full_chg_time"), transform=_to_chgtime, as_duration=True),
    CarSensorSpec("limit_chg_time", "1 kW/120 V Charge Time", _ev_getter("limit_chg_time"), transform=_to_chgtime, as_duration=True),
    CarSensorSpec("obc_6kw", "6.6 kW Charge Time", _ev_getter("obc_6kw"), transform=_to_chgtime, as_duration=True),
    CarSensorSpec("obc_6kw_avail", "6.6 kW OBC Exists", _ev_getter("obc_6kw_avail"), diagnostic=True),
    CarSensorSpec("batt_heater_avail", "Battery Heater Exists", _ev_getter("batt_heater_avail"), diagnostic=True),
    CarSensorSpec("batt_heater_status", "Battery Heater Active", _ev_getter("batt_heater_status")),
    CarSensorSpec("wh_content", "Battery Wh content", _ev_getter("wh_content"), device_class=SensorDeviceClass.ENERGY, unit_of_measurement="Wh"),
    CarSensorSpec("cabin_temp", "Cabin Temperature", _ev_getter("cabin_temp"), device_class=SensorDeviceClass.TEMPERATURE, unit_of_measurement="°C"),
]


class CarValueSensor(OpenCarwingsCarEntity, SensorEntity):
    """Generic per-car sensor based on CarSensorSpec."""

    def __init__(self, coordinator, entry_id: str, vin: str, spec: CarSensorSpec, seed_car: CarData | None = None) -> None:
        OpenCarwingsCarEntity.__init__(self, coordinator, entry_id, vin, seed_car)
        self._spec = spec
        self._attr_unique_id = f"ha_opencarwings_{spec.key}_{vin}"
        if spec.device_class and not spec.as_duration:
            self._attr_device_class = spec.device_class
        if spec.unit_of_measurement and not spec.as_duration:
            self._attr_native_unit_of_measurement = spec.unit_of_measurement
        if spec.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def name(self) -> str:
        car = self._get_car_dict()
        prefix = car.get("nickname") or "Car"
        return f"{prefix} {self._spec.name}"

    @property
    def native_value(self):
        car = self._get_car()
        val = self._spec.value(car)

        if self._spec.transform:
            val = self._spec.transform(val)
        if self._spec.as_duration:
            return format_minutes(val)
        return val

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._spec.as_duration:
            return {}
        val = self._spec.value(self._get_car())
        if self._spec.transform:
            val = self._spec.transform(val)
        return {"minutes": val}


# -----------------------------
# Status sensor 
# -----------------------------

class CarStatusSensor(OpenCarwingsCarEntity, SensorEntity):
    """High-level status string for the car (charging, running, ac_on, idle)."""

    # ``raw_car`` is the whole car as the API returns it (handy for templates and when the API changes), but it
    # is large and holds credentials; keep it in the live state only, out of the recorder database and history.
    _unrecorded_attributes = frozenset({"raw_car"})

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: CarData | None = None,
                 include_location: bool = True) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_status_{vin}"
        self._include_location = include_location

    @property
    def name(self) -> str:
        car = self._get_car_dict()
        prefix = car.get("nickname") or "Car"
        return f"{prefix} Status"

    @property
    def native_value(self) -> str:
        car = self._get_car_dict()
        ev = car.get("ev_info", {}) or {}
        if car.get("command_requested"):
            return "running_command"
        if ev.get("quick_charging"):
            return "quick_charging"
        if ev.get("charging"):
            return "charging"
        if ev.get("car_running") and not driving_unconfirmed(self._get_car().get_latest_car()):
            return "running"
        if ev.get("ac_status"):
            return "ac_on"
        if ev.get("batt_heater_status"):
            return "batt_heater"
        return "idle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Keep this SMALL and SAFE (optional). Remove entirely if you want no attributes.
        car = self._get_car_dict()
        ev = car.get("ev_info", {}) or {}
        return {
            ATTR_ATTRIBUTION: "Data provided by OpenCARWINGS",
            "last_connection": format_local(
                getattr(self._get_car().get_latest_car(), "last_connection", None)
            ),
            "last_evinfo": format_local(data_timestamp(self._get_car().get_latest_car())[0]),
            "data_age_minutes": (
                None
                if (age := data_age_minutes(self._get_car().get_latest_car())) is None
                else int(age)
            ),
            "command_requested": car.get("command_requested"),
            "driving_unconfirmed": driving_unconfirmed(self._get_car().get_latest_car()),
            "signal_level": car.get("signal_level"),
            "carrier": car.get("carrier"),
            "navi_version": car.get("navi_version"),
            "map_version": car.get("map_version"),
            "tcu_version": car.get("tcu_version"),
            "tcu_type": car.get("tcu_type"),
            "soc": ev.get("soc"),
            "range_acoff": ev.get("range_acoff"),
            "color": car.get("color"),
            "raw_car": {
                key: value
                for key, value in car.items()
                if self._include_location or key != "location"
            }
        }


# -----------------------------
# Diagnostic sensors
# -----------------------------

class CarVINSensor(OpenCarwingsCarEntity, SensorEntity):
    """Per-car diagnostic sensor reporting the VIN."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: CarData | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_vin_{vin}"

    @property
    def name(self) -> str:
        car = self._get_car_dict()
        prefix = car.get("nickname") or "Car"
        return f"{prefix} VIN"

    @property
    def native_value(self) -> str:
        return self._vin or "unknown"


class CarLastUpdatedSensor(OpenCarwingsCarEntity, SensorEntity):
    """Diagnostic: when the car last sent data (ev_info.last_updated, else last_connection)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: CarData | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_last_updated_{vin}"

    @property
    def name(self) -> str:
        car = self._get_car_dict()
        prefix = car.get("nickname")or "Car"
        return f"{prefix} Last Updated"

    @property
    def native_value(self) -> datetime | None:
        ts, _ = data_timestamp(self._get_car().get_latest_car())
        return ts

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ts, source = data_timestamp(self._get_car().get_latest_car())
        return {"source": source, "local_time": format_local(ts)}


class CarDataAgeSensor(OpenCarwingsCarEntity, SensorEntity):
    """Diagnostic: minutes since the car last sent data (updates every minute)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: CarData | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_data_age_{vin}"

    @property
    def name(self) -> str:
        car = self._get_car_dict()
        prefix = car.get("nickname") or "Car"
        return f"{prefix} Data Age"

    @property
    def native_value(self) -> str | None:
        return format_minutes(data_age_minutes(self._get_car().get_latest_car()))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        car = self._get_car().get_latest_car()
        ts, source = data_timestamp(car)
        age = data_age_minutes(car)
        return {"minutes": None if age is None else int(age), "source": source, "last_data_time": format_local(ts)}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        track_minute(self)


class CarCommandStatusSensor(OpenCarwingsCarEntity, SensorEntity):
    """Diagnostic: result of the last command sent to the car (from the API)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str, vin: str, seed_car: CarData | None = None) -> None:
        super().__init__(coordinator, entry_id, vin, seed_car)
        self._attr_unique_id = f"ha_opencarwings_command_status_{vin}"

    @property
    def name(self) -> str:
        car = self._get_car_dict()
        prefix = car.get("nickname") or "Car"
        return f"{prefix} Command Status"

    @property
    def native_value(self) -> str:
        summary = command_summary(self._get_car().get_latest_car())
        if not summary:
            return "unknown"
        if summary["command_requested"]:
            return "waiting"
        return (summary.get("command_result_display") or "unknown").lower()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        summary = command_summary(self._get_car().get_latest_car())
        if not summary:
            return {}
        return {
            "command": summary["command_type_display"],
            "command_type": summary["command_type"],
            "command_requested": summary["command_requested"],
            "requested_at": format_local(summary["command_request_time"]),
            "last_confirmed_refresh": format_local(summary["last_confirmed_refresh"]),
        }


# -----------------------------
# Setup
# -----------------------------


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coordinator = data.get("coordinator")
    cars: List[CarData] = coordinator.data if coordinator and coordinator.data is not None else data.get("cars", [])

    entities: list[SensorEntity] = []

    for car in cars:
        vin = car.vin
        if not vin:
            continue

        # Generic value sensors
        for spec in CAR_SENSORS:
            entities.append(CarValueSensor(coordinator, entry.entry_id, vin, spec, seed_car=car))

        # Status
        entities.append(CarStatusSensor(coordinator, entry.entry_id, vin, seed_car=car,
                                        include_location=track_location_enabled(entry)))

        # Diagnostics
        entities.append(CarLastUpdatedSensor(coordinator, entry.entry_id, vin, seed_car=car))
        entities.append(CarDataAgeSensor(coordinator, entry.entry_id, vin, seed_car=car))
        entities.append(CarCommandStatusSensor(coordinator, entry.entry_id, vin, seed_car=car))
        entities.append(CarVINSensor(coordinator, entry.entry_id, vin, seed_car=car))

    async_add_entities(entities)
