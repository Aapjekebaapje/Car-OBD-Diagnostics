import threading
import time
import traceback
import json
import re
from html import escape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from config import APP_VERSION
from scanner_core.demo_services import (
    build_demo_dtc_snapshot,
    build_demo_freeze_frame,
    get_demo_default_speed,
    get_demo_presets,
    get_demo_preset,
    normalize_demo_preset,
    build_demo_readiness,
    build_demo_vehicle_profile,
    build_demo_vehicle_snapshot,
)
from flask import Flask, Response, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from scanner_core.cache_services import load_vin_cache, save_vin_cache
from scanner_core.dtc_catalog import enrich_dtc
from scanner_core.obd_services import (
    connection_quality_snapshot as build_connection_quality_snapshot,
    detect_connection_hint,
    get_freeze_frame_snapshot,
    get_readiness_snapshot,
    list_serial_ports,
    run_connection_test,
)
from scanner_core.report_services import build_purchase_report
from scanner_core.session_services import build_scanner_session_state
from scanner_core.storage_services import (
    db_path_from_file,
    get_recent_garage_notes as storage_get_recent_garage_notes,
    get_recent_scans as storage_get_recent_scans,
    get_setting as storage_get_setting,
    init_storage,
    save_garage_note as storage_save_garage_note,
    save_scan_snapshot as storage_save_scan_snapshot,
    set_setting as storage_set_setting,
)
from scanner_core.translation import LANGUAGE_OPTIONS, get_language, get_translations, localize_payload, translate

try:
    import obd
    OBD_AVAILABLE = True
    OBD_IMPORT_ERROR = None
except Exception as e:
    obd = None
    OBD_AVAILABLE = False
    OBD_IMPORT_ERROR = e

app = Flask(__name__)


def current_language():
    return get_language(request.cookies.get("obd_lang", "en"))


def localized_jsonify(payload, status_code=200):
    return jsonify(localize_payload(payload, current_language())), status_code


@app.context_processor
def inject_translations():
    lang = current_language()
    translations = get_translations(lang)
    translations["meta"]["title"] = f"OBD Scanner {APP_VERSION}"
    translations["partials"]["startup"]["title"] = f"OBD Scanner {APP_VERSION}"
    translations["partials"]["sidebar"]["brand_name"] = f"OBD Scanner {APP_VERSION}"

    return {
        "lang": lang,
        "language_options": LANGUAGE_OPTIONS,
        "i18n": translations,
        "tr": lambda key, **kwargs: translate(lang, key, **kwargs),
        "js_translations": translations.get("js", {}),
        "app_version": APP_VERSION,
    }


@app.after_request
def localize_json_response(response):
    if response.is_json:
        try:
            payload = response.get_json(silent=True)
            localized = localize_payload(payload, current_language())
            response.set_data(json.dumps(localized))
        except Exception:
            pass
    return response

DB_PATH = db_path_from_file(__file__)
POLL_INTERVAL = 0.2
RPM_POLL_INTERVAL = 0.05
MAX_POLL_INTERVAL = 0.8
STALE_AFTER_SECONDS = 0.9
SCAN_HISTORY_LIMIT = 20

connection = None
vehicle_data = {}
dtc_data = {
    "stored": [],
    "pending": [],
    "permanent": []
}
dtc_status = {
    "has_scan": False,
    "scanning": False,
    "last_scan": None,
    "message": "No fault code scan run yet."
}
readiness_data = {
    "available": False,
    "mil": None,
    "dtc_count": None,
    "ignition_type": "",
    "monitors": [],
}
freeze_frame_data = {
    "available": False,
    "values": {},
}

vehicle_profile = {
    "vin": "",
    "vin_status": "idle",
    "vin_message": "VIN not loaded yet.",
    "vin_last_update": None,
    "decoded": {},
    "plate_query": "",
    "plate_status": "idle",
    "plate_message": "No plate lookup yet.",
    "plate_last_update": None,
    "rdw": {}
}

obd_status = {
    "connected": False,
    "protocol": "Unknown",
    "error": None,
    "user_message": "Scanner starting up.",
    "last_update": None,
    "last_successful_update": None,
    "safe_mode": True,
    "limited_mode": False,
    "current_port": None,
    "connecting": False,
    "demo_mode": False,
    "connection_hint": {
        "kind": "searching",
        "label": "Searching for adapter",
        "detail": "Waiting for a USB OBD adapter or a live ECU response.",
    },
    "poll_interval": POLL_INTERVAL,
    "poll_guard_active": False,
    "poll_guard_reason": "",
    "recent_errors": []
}

state_lock = threading.Lock()
obd_lock = threading.Lock()
connect_lock = threading.Lock()
vin_refresh_lock = threading.Lock()
vin_refresh_in_progress = False
vin_autoload_attempted = False
query_error_streak = 0
current_live_poll_interval = POLL_INTERVAL
demo_drive_state = {
    "speed_kmh": 0.0,
    "preset": "idle",
}
error_log_state = {}


def is_known_port_config_error(error):
    message = str(error or "").lower()
    return (
        "cannot configure port" in message
        or "the parameter is incorrect" in message
        or "oserror(22" in message
    )


def log_error(source, error):
    console_message = friendly_message(error, source=source)
    raw_message = str(error)
    signature = f"{source}|{console_message or raw_message}"
    now = time.time()
    last_seen = error_log_state.get(signature, 0)
    should_emit_console = (now - last_seen) >= 12

    if should_emit_console:
        if is_known_port_config_error(error):
            print(f"{source}: Cannot connect to the ECU. The USB OBD adapter is not connected or not detected.")
        else:
            print(f"{source}: {raw_message}")
            if console_message and console_message != raw_message:
                print(f"{source} (friendly): {console_message}")
            traceback.print_exc()
        error_log_state[signature] = now

    with state_lock:
        obd_status["error"] = str(error)
        obd_status["user_message"] = console_message
        obd_status["last_update"] = time.strftime("%H:%M:%S")
        existing = obd_status["recent_errors"][0] if obd_status["recent_errors"] else None
        if existing and existing.get("source") == source and existing.get("technical_message") == str(error):
            existing["time"] = time.strftime("%H:%M:%S")
            existing["message"] = console_message
        else:
            technical_message = (
                "Suppressed repeated serial port configuration error."
                if is_known_port_config_error(error)
                else str(error)
            )
            obd_status["recent_errors"].insert(0, {
                "time": time.strftime("%H:%M:%S"),
                "source": source,
                "message": console_message,
                "technical_message": technical_message
            })
            del obd_status["recent_errors"][8:]


def get_command(name):
    if not OBD_AVAILABLE:
        return None

    return getattr(obd.commands, name, None)


def init_config_db():
    try:
        init_storage(DB_PATH)
    except Exception as e:
        log_error("Initialize config database", e)


def get_setting(key, default=None):
    try:
        return storage_get_setting(DB_PATH, key, default)
    except Exception as e:
        log_error("Read config", e)
        return default


def set_setting(key, value):
    try:
        return storage_set_setting(DB_PATH, key, value)
    except Exception as e:
        log_error("Save config", e)
        return False


def get_configured_port():
    port = get_setting("obd_port", "")
    port = port.strip() if port else ""
    return port or None


def get_demo_mode_enabled():
    return str(get_setting("demo_mode", "0")).strip().lower() in {"1", "true", "yes", "on"}


def set_demo_mode_enabled(enabled):
    return set_setting("demo_mode", "1" if enabled else "0")


def get_limited_mode_enabled():
    return str(get_setting("limited_mode", "0")).strip().lower() in {"1", "true", "yes", "on"}


def set_limited_mode_enabled(enabled):
    return set_setting("limited_mode", "1" if enabled else "0")


POLL_PROFILES = {
    "performance": {
        "label": "Performance",
        "limited": False,
        "description": "Performance uses faster polling for a more live feel.",
    },
    "balanced": {
        "label": "Balanced",
        "limited": False,
        "description": "Balanced is recommended for normal diagnostics.",
    },
    "safe": {
        "label": "Safe",
        "limited": True,
        "description": "Safe slows non-critical values and limits polling to core live data.",
    },
}


def normalize_poll_profile(profile):
    profile = str(profile or "balanced").strip().lower()
    return profile if profile in POLL_PROFILES else "balanced"


def get_poll_profile_name():
    return normalize_poll_profile(get_setting("poll_profile", "balanced"))


def get_poll_profile():
    name = get_poll_profile_name()
    return {
        "id": name,
        **POLL_PROFILES[name],
    }


def set_poll_profile_name(profile):
    return set_setting("poll_profile", normalize_poll_profile(profile))


def get_demo_preset_name():
    return normalize_demo_preset(get_setting("demo_preset", "idle"))


def set_demo_preset_name(preset):
    normalized = normalize_demo_preset(preset)
    return set_setting("demo_preset", normalized)


def apply_demo_preset_state(preset, reset_speed=True):
    preset_name = normalize_demo_preset(preset)
    default_speed = get_demo_default_speed(preset_name)
    with state_lock:
        demo_drive_state["preset"] = preset_name
        if reset_speed:
            demo_drive_state["speed_kmh"] = default_speed
    return preset_name, default_speed


def now_time():
    return time.strftime("%H:%M:%S")


def reset_vehicle_profile():
    global vehicle_profile, vin_autoload_attempted

    with state_lock:
        vehicle_profile = {
            "vin": "",
            "vin_status": "idle",
            "vin_message": "VIN not loaded yet.",
            "vin_last_update": None,
            "decoded": {},
            "plate_query": "",
            "plate_status": "idle",
            "plate_message": "No plate lookup yet.",
            "plate_last_update": None,
            "rdw": {}
        }
        vin_autoload_attempted = False


def update_vehicle_profile(**updates):
    with state_lock:
        vehicle_profile.update(updates)


def set_vehicle_value(key, label, value):
    measured_at = time.time()
    with state_lock:
        previous = dict(vehicle_data.get(key, {}))
        vehicle_data[key] = build_live_item(previous, label, value, measured_at)


def build_live_item(previous, label, value, measured_at=None):
    measured_at = measured_at or time.time()
    previous = previous or {}
    is_fresh = value not in {None, "", "N/A"}

    if is_fresh:
        updated_epoch = measured_at
        display_value = value
    else:
        updated_epoch = previous.get("updated_epoch")
        display_value = previous.get("value", "N/A")

    age_seconds = None if updated_epoch is None else max(0.0, measured_at - updated_epoch)
    stale = bool(updated_epoch and age_seconds is not None and age_seconds >= STALE_AFTER_SECONDS)

    return {
        "label": label,
        "value": display_value,
        "updated_at": time.strftime("%H:%M:%S", time.localtime(updated_epoch)) if updated_epoch else "--",
        "updated_epoch": updated_epoch,
        "stale": stale if display_value != "N/A" else False,
    }


def refresh_vehicle_stale_flags():
    now = time.time()

    with state_lock:
        for key, item in list(vehicle_data.items()):
            updated_epoch = item.get("updated_epoch")
            vehicle_data[key] = {
                **item,
                "stale": bool(updated_epoch and (now - updated_epoch) >= STALE_AFTER_SECONDS),
            }


def apply_poll_guard_success():
    global query_error_streak, current_live_poll_interval

    if query_error_streak > 0:
        query_error_streak -= 1

    if query_error_streak == 0:
        current_live_poll_interval = POLL_INTERVAL

    with state_lock:
        obd_status["poll_interval"] = round(current_live_poll_interval, 2)
        obd_status["poll_guard_active"] = current_live_poll_interval > POLL_INTERVAL
        obd_status["poll_guard_reason"] = (
            "Polling slowed temporarily because the adapter returned repeated query errors."
            if current_live_poll_interval > POLL_INTERVAL
            else ""
        )


def apply_poll_guard_error():
    global query_error_streak, current_live_poll_interval

    query_error_streak += 1
    if query_error_streak >= 3:
        current_live_poll_interval = min(MAX_POLL_INTERVAL, round(POLL_INTERVAL + min(0.6, query_error_streak * 0.05), 2))

    with state_lock:
        obd_status["poll_interval"] = round(current_live_poll_interval, 2)
        obd_status["poll_guard_active"] = current_live_poll_interval > POLL_INTERVAL
        obd_status["poll_guard_reason"] = (
            "Polling slowed temporarily because the adapter returned repeated query errors."
            if current_live_poll_interval > POLL_INTERVAL
            else ""
        )


def reset_readiness_state():
    global readiness_data

    with state_lock:
        readiness_data = {
            "available": False,
            "mil": None,
            "dtc_count": None,
            "ignition_type": "",
            "monitors": [],
        }


def reset_dtc_state(message="No fault code scan run yet."):
    global dtc_data, freeze_frame_data

    with state_lock:
        dtc_data = {
            "stored": [],
            "pending": [],
            "permanent": []
        }
        dtc_status["has_scan"] = False
        dtc_status["scanning"] = False
        dtc_status["last_scan"] = None
        dtc_status["message"] = message
        freeze_frame_data = {
            "available": False,
            "values": {},
        }


def friendly_message(error=None, source=None, port=None):
    raw_message = str(error or "").strip()
    message = raw_message.lower()
    target_port = port or get_configured_port()
    port_label = target_port or "the selected port"

    if (
        "the parameter is incorrect" in message
        or "oserror(22" in message
        or "cannot configure port" in message
    ):
        return "Cannot connect to the ECU. The USB OBD adapter is not connected or not detected."

    if source == "Connect OBD":
        if "could not open port" in message or "filenotfounderror" in message:
            return f"No adapter found on {port_label}. Check the cable and COM port."
        if "access is denied" in message or "permissionerror" in message:
            return f"{port_label} is busy or blocked by another app. Close other OBD software and try again."
        if "unable to connect" in message or "not connected" in message:
            return "Adapter found, but the car is not responding. Turn ignition on and try again."
        if "no obd connection found" in message:
            return "No OBD connection found. Check the adapter, ignition, and selected COM port."
        if "python-obd did not load" in message:
            return "The OBD library could not start. Reinstall the scanner dependencies."

    if source == "Live data query":
        return "Live data could not be read. Check the ignition and reconnect if needed."

    if source == "Read DTC":
        return "Fault codes could not be read right now. Try reconnecting and scan again."

    if source == "Clear fault codes":
        return "Clearing fault codes failed. Keep ignition on and try once more."

    if source == "Change COM port":
        return "Cannot connect to the ECU. Check the USB OBD adapter."

    if source == "Initialize config database" or source == "Read config" or source == "Save config":
        return "Scanner settings could not be loaded or saved."

    if source == "Read VIN":
        return "VIN could not be read from the car. Some cars do not expose it over standard OBD."

    if source == "Decode VIN":
        return "VIN was read, but online vehicle details could not be loaded."

    if source == "Lookup RDW":
        return "RDW lookup failed. Check the plate and your internet connection."

    if raw_message:
        return raw_message

    return "An unknown scanner error occurred."


LIVE_COMMANDS = {
    "status": ("Monitor status", get_command("STATUS")),
    "fuel_status": ("Fuel system", get_command("FUEL_STATUS")),
    "speed": ("Speed", get_command("SPEED")),
    "warmups_since_clear": ("Warmups since codes cleared", get_command("WARMUPS_SINCE_DTC_CLEAR")),
    "distance_since_clear": ("Distance since codes cleared", get_command("DISTANCE_SINCE_DTC_CLEAR")),
    "time_since_clear": ("Time since codes cleared", get_command("TIME_SINCE_DTC_CLEARED")),
    "coolant_temp": ("Coolant temperature", get_command("COOLANT_TEMP")),
    "oil_temp": ("Oil temperature", get_command("OIL_TEMP")),
    "intake_temp": ("Intake air temperature", get_command("INTAKE_TEMP")),
    "ambient_temp": ("Ambient air temperature", get_command("AMBIANT_AIR_TEMP")),
    "engine_load": ("Engine load", get_command("ENGINE_LOAD")),
    "throttle": ("Throttle position", get_command("THROTTLE_POS")),
    "intake_pressure": ("Intake manifold pressure", get_command("INTAKE_PRESSURE")),
    "fuel_pressure": ("Fuel pressure", get_command("FUEL_PRESSURE")),
    "barometric_pressure": ("Barometric pressure", get_command("BAROMETRIC_PRESSURE")),
    "timing_advance": ("Timing advance", get_command("TIMING_ADVANCE")),
    "short_fuel_trim_1": ("Short fuel trim bank 1", get_command("SHORT_FUEL_TRIM_1")),
    "long_fuel_trim_1": ("Long fuel trim bank 1", get_command("LONG_FUEL_TRIM_1")),
    "maf": ("MAF air flow", get_command("MAF")),
    "fuel_level": ("Fuel level", get_command("FUEL_LEVEL")),
    "runtime": ("Engine runtime", get_command("RUN_TIME")),
    "distance_mil": ("Distance with MIL on", get_command("DISTANCE_W_MIL")),
    "control_voltage": ("ECU voltage", get_command("CONTROL_MODULE_VOLTAGE")),
    "voltage": ("Adapter voltage", get_command("ELM_VOLTAGE")),
}
LIMITED_MODE_COMMAND_KEYS = {
    "speed",
    "coolant_temp",
    "engine_load",
    "throttle",
    "long_fuel_trim_1",
    "control_voltage",
}
RPM_COMMAND = get_command("RPM")
SPEED_COMMAND = get_command("SPEED")
ENGINE_LOAD_COMMAND = get_command("ENGINE_LOAD")
THROTTLE_COMMAND = get_command("THROTTLE_POS")
FAST_LOOP_COMMAND_KEYS = {"speed", "engine_load", "throttle"}


def get_active_live_commands():
    commands = {key: value for key, value in LIVE_COMMANDS.items() if key not in FAST_LOOP_COMMAND_KEYS}
    if get_poll_profile()["limited"]:
        return {
            key: value
            for key, value in commands.items()
            if key in LIMITED_MODE_COMMAND_KEYS
        }
    return commands

VIN_PATTERN = re.compile(r"[A-HJ-NPR-Z0-9]{17}")
RDW_DATASET_URL = "https://opendata.rdw.nl/resource/m9d7-ebf2.json"
NHTSA_DECODE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValuesExtended/{vin}?format=json"

VIN_MODEL_YEAR_CODES = {
    "A": 1980, "B": 1981, "C": 1982, "D": 1983, "E": 1984, "F": 1985, "G": 1986, "H": 1987,
    "J": 1988, "K": 1989, "L": 1990, "M": 1991, "N": 1992, "P": 1993, "R": 1994, "S": 1995,
    "T": 1996, "V": 1997, "W": 1998, "X": 1999, "Y": 2000, "1": 2001, "2": 2002, "3": 2003,
    "4": 2004, "5": 2005, "6": 2006, "7": 2007, "8": 2008, "9": 2009,
}

VIN_COUNTRY_CODES = {
    "1": "United States",
    "2": "Canada",
    "3": "Mexico",
    "J": "Japan",
    "K": "South Korea",
    "L": "China",
    "S": "United Kingdom",
    "T": "Switzerland",
    "V": "France or Spain",
    "W": "Germany",
    "Y": "Sweden or Finland",
    "Z": "Italy",
}


def number_from_value(value):
    if value is None:
        return None

    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", "."))
    return float(match.group(0)) if match else None


def get_supported_sensor_matrix():
    if get_demo_mode_enabled():
        sensors = []
        for key, (label, command) in LIVE_COMMANDS.items():
            sensors.append({
                "key": key,
                "label": label,
                "command": command.name if command else key.upper(),
                "supported": True
            })
        sensors.sort(key=lambda item: item["label"].lower())
        return sensors

    supported_names = set()

    try:
        if connection and connection.is_connected():
            with obd_lock:
                supported_names = {command.name for command in connection.supported_commands}
    except Exception as e:
        log_error("Read supported commands", e)

    sensors = []

    for key, (label, command) in LIVE_COMMANDS.items():
        command_name = command.name if command else "Unavailable"
        supported = bool(command and command_name in supported_names)
        sensors.append({
            "key": key,
            "label": label,
            "command": command_name,
            "supported": supported
        })

    sensors.sort(key=lambda item: (not item["supported"], item["label"].lower()))
    return sensors


def build_health_report():
    with state_lock:
        status = dict(obd_status)
        vehicle = dict(vehicle_data)
        dtc = {
            "stored": list(dtc_data["stored"]),
            "pending": list(dtc_data["pending"]),
            "permanent": list(dtc_data["permanent"])
        }
        profile = dict(vehicle_profile)
        connection_hint = dict(obd_status.get("connection_hint") or {})

    stored_count = len(dtc["stored"])
    pending_count = len(dtc["pending"])
    permanent_count = len(dtc["permanent"])
    rpm = number_from_value(vehicle.get("rpm", {}).get("value"))
    control_voltage = number_from_value(vehicle.get("control_voltage", {}).get("value"))
    coolant_temp = number_from_value(vehicle.get("coolant_temp", {}).get("value"))
    fuel_trim = number_from_value(vehicle.get("long_fuel_trim_1", {}).get("value"))
    warmups_since_clear = number_from_value(vehicle.get("warmups_since_clear", {}).get("value"))
    distance_since_clear = number_from_value(vehicle.get("distance_since_clear", {}).get("value"))
    time_since_clear = number_from_value(vehicle.get("time_since_clear", {}).get("value"))

    checklist = []
    score = 100
    status_level = "good"
    headline = "Looks healthy so far."

    if not status.get("connected"):
        checklist.append({
            "level": "warning",
            "title": "Scanner not connected",
            "detail": "No live vehicle connection yet, so results are incomplete."
        })
        score = 0
        status_level = "warning"
        headline = "No live vehicle data yet."

        if connection_hint.get("kind") == "ignition_likely_off":
            checklist.append({
                "level": "info",
                "title": "Ignition is likely off",
                "detail": connection_hint.get("detail") or "Turn the ignition on so the ECU can respond."
            })

    if stored_count > 0:
        checklist.append({
            "level": "danger",
            "title": f"{stored_count} stored fault code(s)",
            "detail": "Stored DTCs usually deserve follow-up before buying."
        })
        score -= min(40, stored_count * 12)

    if pending_count > 0:
        checklist.append({
            "level": "warning",
            "title": f"{pending_count} pending fault code(s)",
            "detail": "Pending codes can point to intermittent or recently detected issues."
        })
        score -= min(20, pending_count * 6)

    if permanent_count > 0:
        checklist.append({
            "level": "warning",
            "title": f"{permanent_count} permanent fault code(s)",
            "detail": "Permanent codes may stay after repairs until drive cycles complete."
        })
        score -= min(15, permanent_count * 4)

    if control_voltage is not None and control_voltage < 11.8:
        checklist.append({
            "level": "warning",
            "title": "Low ECU voltage",
            "detail": f"Voltage looks low at about {control_voltage:.1f} V. Battery or charging system may need attention."
        })
        score -= 10

    if fuel_trim is not None and abs(fuel_trim) >= 12:
        checklist.append({
            "level": "warning",
            "title": "Fuel trim looks high",
            "detail": f"Long fuel trim is around {fuel_trim:.1f}. Could hint at air/fuel imbalance."
        })
        score -= 8

    if coolant_temp is not None and coolant_temp > 108:
        checklist.append({
            "level": "danger",
            "title": "Coolant temperature is high",
            "detail": f"Coolant is around {coolant_temp:.0f} C. Check cooling system health."
        })
        score -= 20

    if rpm is None:
        checklist.append({
            "level": "info",
            "title": "No RPM data yet",
            "detail": "Turn ignition on and start the engine to get a better health picture."
        })

    if not profile.get("vin"):
        checklist.append({
            "level": "info",
            "title": "VIN not read yet",
            "detail": "Some cars do not expose VIN over standard OBD, but reading it helps confirm identity."
        })

    checklist.append({
        "level": "info",
        "title": "Standard OBD only",
        "detail": "Engine and emission data are read over standard OBD-II. ABS, airbag and body modules may need a brand-specific scanner."
    })

    possible_recent_clear = status.get("connected") and (
        (warmups_since_clear is not None and warmups_since_clear <= 3)
        or (distance_since_clear is not None and distance_since_clear <= 50)
        or (time_since_clear is not None and time_since_clear <= 120)
    )

    if possible_recent_clear:
        details = []
        if warmups_since_clear is not None:
            details.append(f"{warmups_since_clear:.0f} warm-up cycle(s)")
        if distance_since_clear is not None:
            details.append(f"{distance_since_clear:.0f} km")
        if time_since_clear is not None:
            details.append(f"{time_since_clear:.0f} minute(s)")

        checklist.append({
            "level": "warning",
            "title": "Codes may have been cleared recently",
            "detail": (
                "ECU counters since DTC clear look low"
                + (f" ({', '.join(details)})." if details else ".")
                + " This can hide faults that have not returned yet."
            )
        })
        score -= 18

    score = max(0, min(100, score))

    if status.get("connected"):
        if stored_count > 0 or (control_voltage is not None and control_voltage < 11.4) or (coolant_temp is not None and coolant_temp > 112):
            status_level = "danger"
            headline = "Possible red flags detected."
        elif pending_count > 0 or permanent_count > 0 or (fuel_trim is not None and abs(fuel_trim) >= 12) or possible_recent_clear:
            status_level = "warning"
            headline = "A few things need checking."

    return {
        "score": score,
        "status": status_level,
        "headline": headline,
        "counts": {
            "stored": stored_count,
            "pending": pending_count,
            "permanent": permanent_count
        },
        "checklist": checklist
    }


def build_battery_check():
    with state_lock:
        vehicle = dict(vehicle_data)
        status = dict(obd_status)

    ecu_voltage = number_from_value(vehicle.get("control_voltage", {}).get("value"))
    adapter_voltage = number_from_value(vehicle.get("voltage", {}).get("value"))
    rpm = number_from_value(vehicle.get("rpm", {}).get("value"))
    voltage = ecu_voltage if ecu_voltage is not None else adapter_voltage

    result = {
        "available": voltage is not None,
        "status": "unknown",
        "headline": "Battery check unavailable",
        "detail": "ECU or adapter voltage is not available yet.",
        "voltage": voltage,
        "ecu_voltage": ecu_voltage,
        "adapter_voltage": adapter_voltage,
        "running": bool(rpm is not None and rpm > 450),
    }

    if voltage is None:
        return result

    if result["running"]:
        if voltage < 13.2:
            result.update({
                "status": "warning",
                "headline": "Charging voltage looks low",
                "detail": f"Voltage is about {voltage:.1f} V while the engine appears to be running. Check alternator, battery and grounds.",
            })
        elif voltage > 15.0:
            result.update({
                "status": "warning",
                "headline": "Charging voltage looks high",
                "detail": f"Voltage is about {voltage:.1f} V. Check alternator regulator and battery condition.",
            })
        else:
            result.update({
                "status": "good",
                "headline": "Charging voltage looks normal",
                "detail": f"Voltage is about {voltage:.1f} V with the engine running.",
            })
    else:
        if voltage < 11.8:
            result.update({
                "status": "warning",
                "headline": "Battery voltage looks low",
                "detail": f"Voltage is about {voltage:.1f} V. Charge or test the battery before deeper diagnostics.",
            })
        elif voltage < 12.2:
            result.update({
                "status": "info",
                "headline": "Battery voltage is a little low",
                "detail": f"Voltage is about {voltage:.1f} V with no clear running RPM signal.",
            })
        else:
            result.update({
                "status": "good",
                "headline": "Battery voltage looks usable",
                "detail": f"Voltage is about {voltage:.1f} V with no clear running RPM signal.",
            })

    if status.get("demo_mode"):
        result["detail"] += " Demo mode values are simulated."

    return result


def build_simple_summary(payload):
    health = payload.get("health", {})
    battery = payload.get("battery_check", {})
    dtc = payload.get("dtc", {})
    readiness = payload.get("readiness", {})
    status = payload.get("status", {})

    stored = len(dtc.get("stored", []))
    pending = len(dtc.get("pending", []))
    permanent = len(dtc.get("permanent", []))
    incomplete = [
        item.get("name", "")
        for item in readiness.get("monitors", [])
        if item.get("available") and not item.get("complete")
    ]

    items = []
    level = "good"
    headline = "No obvious red flags right now."

    if not status.get("connected"):
        level = "warning"
        headline = "Connect the scanner for a real result."
        items.append("No live ECU connection is active yet.")

    if stored or pending or permanent:
        level = "danger" if stored else "warning"
        headline = "Fault codes need attention."
        items.append(f"Codes found: stored {stored}, pending {pending}, permanent {permanent}.")

    if battery.get("status") in {"warning", "danger"}:
        level = "warning" if level == "good" else level
        items.append(battery.get("headline", "Battery or charging system needs checking."))

    if incomplete:
        level = "warning" if level == "good" else level
        items.append(f"Readiness incomplete: {', '.join(incomplete[:4])}.")

    if health.get("status") == "danger":
        level = "danger"
        headline = health.get("headline", headline)
    elif health.get("status") == "warning" and level == "good":
        level = "warning"
        headline = health.get("headline", "A few things need checking.")

    if not items:
        items.append("No stored fault codes, critical voltage warning or readiness warning is visible in the current snapshot.")

    return {
        "enabled_by_default": False,
        "level": level,
        "headline": headline,
        "items": items,
    }


def build_pid_support_summary():
    sensors = get_supported_sensor_matrix()
    supported = [item for item in sensors if item["supported"]]
    unsupported = [item for item in sensors if not item["supported"]]
    return {
        "total": len(sensors),
        "supported_count": len(supported),
        "unsupported_count": len(unsupported),
        "supported": supported,
        "unsupported": unsupported,
    }


def enrich_connection_quality(status, connection_quality):
    quality = dict(connection_quality or {})
    if status.get("demo_mode"):
        quality["quality"] = {
            "level": "good",
            "label": "Demo mode",
            "detail": "Simulated adapter and ECU are online.",
        }
        return quality

    detected_ports = list_serial_ports()
    selected_port = str(status.get("current_port") or get_configured_port() or "").strip().upper()
    selected_port_present = any(
        str(item.get("device") or "").strip().upper() == selected_port
        for item in detected_ports
    )
    any_usb_serial_present = bool(detected_ports)

    if selected_port_present or any_usb_serial_present:
        quality["adapter_connected"] = True
        quality["selected_port_present"] = bool(selected_port_present)
        quality["detected_ports"] = detected_ports
        if not quality.get("phase") or str(quality.get("phase")).lower() == "not connected":
            quality["phase"] = "USB Adapter Detected"

    if quality.get("live_data_active"):
        summary = {
            "level": "good",
            "label": "Live ECU data",
            "detail": "Standard OBD live data is available.",
        }
    elif quality.get("car_connected"):
        summary = {
            "level": "good",
            "label": "ECU responding",
            "detail": "The ECU is responding on standard OBD.",
        }
    elif quality.get("port_powered"):
        summary = {
            "level": "warning",
            "label": "OBD port detected",
            "detail": "The adapter sees the vehicle bus. Waiting for ECU response.",
        }
    elif quality.get("adapter_connected"):
        summary = {
            "level": "warning",
            "label": "USB adapter connected",
            "detail": "The USB adapter is connected. Waiting for the vehicle OBD port to wake up.",
        }
    else:
        summary = {
            "level": "info",
            "label": "Unknown",
            "detail": "Waiting for adapter detection.",
        }

    quality["quality"] = summary
    return quality


def current_scan_payload():
    with state_lock:
        status = dict(obd_status)
        vehicle = dict(vehicle_data)
        dtc = {
            "stored": list(dtc_data["stored"]),
            "pending": list(dtc_data["pending"]),
            "permanent": list(dtc_data["permanent"])
        }
        profile = dict(vehicle_profile)
        readiness = dict(readiness_data)
        freeze_frame = dict(freeze_frame_data)
        demo_preset = normalize_demo_preset(demo_drive_state.get("preset", get_demo_preset_name()))

    connection_quality = (
        {
            "phase": "Demo mode",
            "adapter_connected": True,
            "port_powered": True,
            "car_connected": True,
            "live_data_active": True,
        }
        if status.get("demo_mode")
        else build_connection_quality_snapshot(connection, status.get("connecting"), status.get("error"))
    )
    connection_quality = enrich_connection_quality(status, connection_quality)
    session_state = build_scanner_session_state(
        status,
        connection_quality,
        status.get("connection_hint"),
    )
    preset_id, preset_meta = get_demo_preset(demo_preset)

    payload = {
        "app_version": APP_VERSION,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "session_state": {
            **session_state,
            "demo_preset": preset_id,
            "demo_preset_label": preset_meta["label"],
        },
        "vehicle": vehicle,
        "dtc": dtc,
        "vehicle_profile": profile,
        "connection_quality": connection_quality,
        "connection_hint": dict(status.get("connection_hint") or {}),
        "readiness": readiness,
        "freeze_frame": freeze_frame,
        "health": build_health_report(),
        "battery_check": build_battery_check(),
        "pid_support": build_pid_support_summary(),
        "standard_obd_only": True,
        "demo": {
            "enabled": bool(status.get("demo_mode")),
            "preset": preset_id,
            "presets": get_demo_presets(),
        },
    }
    payload["report"] = build_purchase_report(payload)
    payload["simple_summary"] = build_simple_summary(payload)
    return payload


def save_scan_snapshot(label):
    payload = current_scan_payload()
    created_at = payload["created_at"]
    health = payload["health"]
    status = payload["status"]
    summary = (
        f"{health['status'].upper()} | score {health['score']} | stored {health['counts']['stored']} "
        f"| pending {health['counts']['pending']} | {status.get('protocol', 'Unknown')} | "
        f"{status.get('current_port') or 'auto'}"
    )

    return storage_save_scan_snapshot(DB_PATH, created_at, label, summary, payload)


def normalize_garage_plate(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def get_recent_garage_notes(limit=SCAN_HISTORY_LIMIT):
    return storage_get_recent_garage_notes(DB_PATH, limit)


def filter_garage_notes(notes, vin="", plate=""):
    vin = normalize_vin(vin)
    plate = normalize_garage_plate(plate)
    filtered = []
    for item in notes:
        item_vin = normalize_vin(item.get("vin", ""))
        item_plate = normalize_garage_plate(item.get("plate", ""))
        if vin and vin != item_vin:
            continue
        if plate and plate != item_plate:
            continue
        filtered.append(item)
    return filtered


def save_garage_note_snapshot(vin, plate, title, mileage, note):
    payload = current_scan_payload()
    created_at = payload["created_at"]
    vin = normalize_vin(vin)
    plate = normalize_garage_plate(plate)
    return storage_save_garage_note(
        DB_PATH,
        created_at,
        vin,
        plate,
        title.strip() or "Garage note",
        mileage.strip() or "--",
        note.strip(),
        payload,
    )


def render_export_html(payload):
    status = payload.get("status", {})
    vehicle = payload.get("vehicle", {})
    dtc = payload.get("dtc", {})
    health = payload.get("health", {})
    battery = payload.get("battery_check", {})
    readiness = payload.get("readiness", {})
    report = payload.get("report", {})

    def row(label, value):
        safe_value = value if value not in (None, "") else "--"
        return f"<tr><th>{escape(str(label))}</th><td>{escape(str(safe_value))}</td></tr>"

    def code_rows(title, codes):
        if not codes:
            return f"<h2>{escape(title)}</h2><p>No codes.</p>"
        rows = []
        for item in codes:
            causes = ", ".join(item.get("possible_causes") or [])
            rows.append(
                "<tr>"
                f"<td>{escape(item.get('code', '--'))}</td>"
                f"<td>{escape(item.get('description_en') or item.get('description') or '--')}</td>"
                f"<td>{escape(item.get('system') or '--')}</td>"
                f"<td>{escape(item.get('severity') or '--')}</td>"
                f"<td>{escape(causes or '--')}</td>"
                "</tr>"
            )
        return (
            f"<h2>{escape(title)}</h2>"
            "<table><thead><tr><th>Code</th><th>Description</th><th>System</th><th>Severity</th><th>Possible causes</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )

    readiness_items = readiness.get("monitors", []) if readiness.get("available") else []
    readiness_rows = "".join(
        row(item.get("name", "Monitor"), "Ready" if item.get("complete") else "Incomplete")
        for item in readiness_items
    ) or row("Readiness", "No readiness data available")

    report_sections = "".join(
        f"<h3>{escape(section.get('title', 'Section'))}</h3><ul>"
        + "".join(f"<li>{escape(str(item))}</li>" for item in section.get("items", []))
        + "</ul>"
        for section in report.get("sections", [])
    )

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>OBD Scan Report {escape(payload.get('created_at', ''))}</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #172033; margin: 32px; }}
    h1, h2, h3 {{ margin-bottom: 8px; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 24px; }}
    th, td {{ border: 1px solid #d6dee8; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f1f5f9; width: 220px; }}
    .note {{ color: #627286; }}
  </style>
</head>
<body>
  <h1>OBD Scan Report</h1>
  <p class="note">Generated by OBD-scanner-Python {escape(APP_VERSION)} at {escape(payload.get('created_at', '--'))}</p>
  <h2>Overview</h2>
  <table>
    {row('Connection', 'Connected' if status.get('connected') else 'Not connected')}
    {row('Protocol', status.get('protocol', 'Unknown'))}
    {row('Port', status.get('current_port') or 'auto')}
    {row('Health score', health.get('score', '--'))}
    {row('Health verdict', health.get('headline', '--'))}
    {row('Battery / charging', battery.get('headline', '--'))}
  </table>
  <h2>Live Highlights</h2>
  <table>
    {row('RPM', vehicle.get('rpm', {}).get('value', '--'))}
    {row('Speed', vehicle.get('speed', {}).get('value', '--'))}
    {row('Coolant temp', vehicle.get('coolant_temp', {}).get('value', '--'))}
    {row('ECU voltage', vehicle.get('control_voltage', {}).get('value', '--'))}
    {row('Long fuel trim bank 1', vehicle.get('long_fuel_trim_1', {}).get('value', '--'))}
  </table>
  {code_rows('Stored Codes', dtc.get('stored', []))}
  {code_rows('Pending Codes', dtc.get('pending', []))}
  {code_rows('Permanent Codes', dtc.get('permanent', []))}
  <h2>Readiness</h2>
  <table>{readiness_rows}</table>
  <h2>Report Details</h2>
  {report_sections or '<p>No report details available.</p>'}
  <p class="note">Standard OBD-II only. ABS, airbag and body modules may require brand-specific diagnostics.</p>
</body>
</html>"""


def render_garage_notes_export_html(notes, vin="", plate=""):
    vin = normalize_vin(vin)
    plate = normalize_garage_plate(plate)
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")

    def metric(label, value):
        return (
            '<div class="metric">'
            f"<span>{escape(str(label))}</span>"
            f"<strong>{escape(str(value or '--'))}</strong>"
            "</div>"
        )

    def note_card(item):
        payload = item.get("payload") or {}
        health = payload.get("health") or {}
        status = payload.get("status") or {}
        vehicle = payload.get("vehicle") or {}
        return f"""
        <article class="note-card">
          <div class="note-head">
            <div>
              <span>{escape(item.get('created_at', '--'))}</span>
              <h2>{escape(item.get('title') or 'Garage note')}</h2>
            </div>
            <strong>{escape(item.get('mileage') or '--')}</strong>
          </div>
          <div class="identity-row">
            <span>VIN: {escape(item.get('vin') or '--')}</span>
            <span>Plate: {escape(item.get('plate') or '--')}</span>
          </div>
          <p class="note-text">{escape(item.get('note') or '')}</p>
          <div class="metric-grid">
            {metric('Health score', health.get('score', '--'))}
            {metric('Protocol', status.get('protocol', 'Unknown'))}
            {metric('RPM', (vehicle.get('rpm') or {}).get('value', '--'))}
            {metric('Speed', (vehicle.get('speed') or {}).get('value', '--'))}
          </div>
        </article>
        """

    cards = "\n".join(note_card(item) for item in notes) or '<p class="empty">No garage notes found for this filter.</p>'
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Garage Notes Export</title>
  <style>
    :root {{ color-scheme: light; --blue:#0d6efd; --text:#172033; --muted:#64748b; --line:#d6e0ec; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #eef4fb; color: var(--text); font-family: Segoe UI, Arial, sans-serif; }}
    .hero {{ background: linear-gradient(135deg, #0d6efd, #153e9f); color: #fff; padding: 34px 40px; }}
    .hero span {{ display:block; font-size:12px; font-weight:800; letter-spacing:.14em; text-transform:uppercase; opacity:.86; }}
    .hero h1 {{ margin: 8px 0 10px; font-size: 34px; }}
    .hero p {{ margin: 0; opacity: .9; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 26px; }}
    .summary {{ display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; margin-top: -48px; margin-bottom: 18px; }}
    .metric, .note-card {{ background: rgba(255,255,255,.96); border:1px solid var(--line); border-radius:18px; box-shadow:0 16px 40px rgba(40,68,110,.10); }}
    .metric {{ padding: 16px; }}
    .metric span {{ display:block; color:var(--muted); font-size:11px; font-weight:900; letter-spacing:.12em; text-transform:uppercase; }}
    .metric strong {{ display:block; margin-top:6px; font-size:20px; }}
    .note-card {{ margin: 14px 0; padding: 20px; }}
    .note-head {{ display:flex; justify-content:space-between; gap:16px; border-bottom:1px solid var(--line); padding-bottom:14px; }}
    .note-head span, .identity-row, .note-text {{ color: var(--muted); }}
    .note-head h2 {{ margin:4px 0 0; font-size:24px; }}
    .identity-row {{ display:flex; flex-wrap:wrap; gap:10px; margin:14px 0; font-weight:700; }}
    .identity-row span {{ background:#edf5ff; border:1px solid #cfe2ff; border-radius:999px; padding:7px 10px; }}
    .note-text {{ white-space:pre-wrap; line-height:1.55; }}
    .metric-grid {{ display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:10px; margin-top:16px; }}
    .empty {{ background:#fff; border:1px dashed var(--line); border-radius:18px; padding:20px; color:var(--muted); }}
    footer {{ color: var(--muted); margin: 24px 0; font-size: 13px; }}
    @media (max-width: 760px) {{ .summary, .metric-grid {{ grid-template-columns:1fr; }} .hero {{ padding:26px 22px; }} main {{ padding:18px; }} }}
  </style>
</head>
<body>
  <section class="hero">
    <span>Car-OBD-Diagnostics {escape(APP_VERSION)}</span>
    <h1>Garage Notes Export</h1>
    <p>Generated at {escape(generated_at)}</p>
  </section>
  <main>
    <section class="summary">
      {metric('Notes', len(notes))}
      {metric('VIN filter', vin or 'All')}
      {metric('Plate filter', plate or 'All')}
      {metric('Generated', generated_at)}
    </section>
    {cards}
    <footer>Use this software at your own risk. Licensed under GNU GPLv3.</footer>
  </main>
</body>
</html>"""


def get_recent_scans(limit=SCAN_HISTORY_LIMIT):
    return storage_get_recent_scans(DB_PATH, limit)


def connect_obd():
    global connection, query_error_streak, current_live_poll_interval

    with connect_lock:
        try:
            query_error_streak = 0
            current_live_poll_interval = POLL_INTERVAL
            demo_mode = get_demo_mode_enabled()
            with state_lock:
                obd_status["demo_mode"] = demo_mode
                obd_status["limited_mode"] = bool(get_poll_profile()["limited"])
                obd_status["poll_interval"] = POLL_INTERVAL
                obd_status["poll_guard_active"] = False
                obd_status["poll_guard_reason"] = ""

            if demo_mode:
                preset_name, default_speed = apply_demo_preset_state(get_demo_preset_name(), reset_speed=False)
                connection = None
                set_status(
                    True,
                    protocol="Simulator",
                    user_message="Demo mode is active. Simulating a standard OBD-II session.",
                    connecting=False
                )
                with state_lock:
                    obd_status["current_port"] = "Demo mode"
                    obd_status["connection_hint"] = detect_connection_hint(None, demo_mode=True)
                    demo_drive_state["preset"] = preset_name
                    if not demo_drive_state.get("speed_kmh"):
                        demo_drive_state["speed_kmh"] = default_speed
                return

            if not OBD_AVAILABLE:
                connection = None
                set_status(
                    False,
                    error=f"python-obd did not load: {OBD_IMPORT_ERROR}",
                    user_message=friendly_message(
                        f"python-obd did not load: {OBD_IMPORT_ERROR}",
                        source="Connect OBD"
                    ),
                    connecting=False
                )
                return

            port = get_configured_port()

            with state_lock:
                obd_status["current_port"] = port
                obd_status["connecting"] = True
                obd_status["user_message"] = (
                    f"Connecting to {port}..." if port else "Searching for OBD adapter..."
                )
                obd_status["last_update"] = time.strftime("%H:%M:%S")

            print("Connecting OBD...")

            if port:
                new_connection = obd.OBD(port, fast=False)
            else:
                new_connection = obd.OBD(fast=False)

            connection = new_connection

            if new_connection.is_connected():
                protocol = new_connection.protocol_name()
                set_status(
                    True,
                    protocol=protocol,
                    user_message=f"Connected via {protocol} on {port or 'auto-detect'}.",
                    connecting=False
                )
                print("Connected:", protocol, "port:", port or "auto")
            else:
                set_status(
                    False,
                    error="No OBD connection found.",
                    user_message=friendly_message("No OBD connection found.", source="Connect OBD", port=port),
                    connecting=False
                )
                print("No OBD connection.")

            with state_lock:
                obd_status["connection_hint"] = detect_connection_hint(connection, obd_status.get("error"))

        except Exception as e:
            connection = None
            set_status(
                False,
                error=str(e),
                user_message=friendly_message(e, source="Connect OBD", port=port if "port" in locals() else None),
                connecting=False
            )
            with state_lock:
                obd_status["connection_hint"] = detect_connection_hint(None, e)
            log_error("Connect OBD", e)


def set_status(connected, protocol=None, error=None, user_message=None, connecting=None):
    with state_lock:
        obd_status["connected"] = connected
        obd_status["protocol"] = protocol or "Unknown"
        obd_status["error"] = error
        obd_status["limited_mode"] = bool(get_poll_profile()["limited"])
        if user_message is not None:
            obd_status["user_message"] = user_message
        if connecting is not None:
            obd_status["connecting"] = connecting
        obd_status["last_update"] = time.strftime("%H:%M:%S")
        obd_status["connection_hint"] = detect_connection_hint(connection, error, obd_status.get("demo_mode", False))
        if connected:
            obd_status["last_successful_update"] = obd_status["last_update"]


def safe_query(command):
    if command is None:
        return "N/A"

    if not connection or not connection.is_connected():
        return "N/A"

    try:
        if hasattr(connection, "supports") and not connection.supports(command):
            return "N/A"

        with obd_lock:
            response = connection.query(command)

        if response.is_null():
            return "N/A"

        apply_poll_guard_success()
        return str(response.value)

    except Exception as e:
        apply_poll_guard_error()
        log_error("Live data query", e)
        return "N/A"


def fetch_json(url):
    request_obj = Request(
        url,
        headers={
            "User-Agent": "OBD-Scanner-Pro/1.0",
            "Accept": "application/json"
        }
    )

    with urlopen(request_obj, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_vin(raw_value):
    if raw_value is None:
        return ""

    compact = re.sub(r"[^A-Za-z0-9]", "", str(raw_value).upper())
    match = VIN_PATTERN.search(compact)
    return match.group(0) if match else ""


def read_vin():
    vin_command = get_command("VIN")

    if vin_command is None:
        raise RuntimeError("VIN command is not available in python-obd.")

    if not connection or not connection.is_connected():
        raise RuntimeError("No OBD connection.")

    with obd_lock:
        response = connection.query(vin_command)

    if response.is_null() or not response.value:
        raise RuntimeError("No VIN response from vehicle.")

    vin = normalize_vin(response.value)

    if not vin:
        raise RuntimeError(f"Could not parse VIN from response: {response.value}")

    return vin


def _clean_vehicle_field(value):
    if value is None:
        return ""

    text = str(value).strip()
    if not text or text.lower() in {"0", "null", "none", "not applicable"}:
        return ""
    return text


def _first_vehicle_field(*values):
    for value in values:
        cleaned = _clean_vehicle_field(value)
        if cleaned:
            return cleaned
    return ""


def _join_vehicle_fields(*values, separator=" / "):
    parts = []
    seen = set()

    for value in values:
        cleaned = _clean_vehicle_field(value)
        if not cleaned:
            continue
        normalized = cleaned.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        parts.append(cleaned)

    return separator.join(parts)


def _build_rdw_fuel_description(row):
    return _join_vehicle_fields(
        row.get("brandstofomschrijving"),
        row.get("brandstof_omschrijving"),
        row.get("brandstof_omschrijving_1"),
        row.get("brandstof_omschrijving_2"),
        row.get("brandstof_omschrijving_3"),
        row.get("brandstof"),
    )


def _build_vin_extra_details(item):
    detail_specs = [
        ("manufacturer", "Manufacturer"),
        ("vehicle_type", "Vehicle type"),
        ("series", "Series"),
        ("trim", "Trim"),
        ("vin_wmi", "WMI"),
        ("vin_vds", "Vehicle descriptor"),
        ("vin_vis", "Vehicle identifier"),
        ("vin_check_digit", "Check digit"),
        ("vin_year_code", "Model year code"),
        ("vin_model_year_estimate", "Estimated model year"),
        ("vin_plant_code", "Plant code"),
        ("vin_serial_number", "Serial number"),
        ("vin_country_hint", "Country hint"),
        ("fuel_type_secondary", "Secondary fuel"),
        ("transmission_style", "Transmission"),
        ("engine_model", "Engine model"),
        ("engine_power_hp", "Engine power"),
        ("engine_configuration", "Engine configuration"),
        ("drive_type", "Drive type"),
        ("doors", "Doors"),
        ("seats", "Seats"),
        ("plant_company", "Plant company"),
        ("plant_location", "Plant location"),
    ]

    details = []
    for key, label in detail_specs:
        value = _clean_vehicle_field(item.get(key))
        if value:
            details.append({
                "key": key,
                "label": label,
                "value": value,
            })
    return details


def _decode_vin_year_code(code):
    base_year = VIN_MODEL_YEAR_CODES.get(str(code or "").upper())
    if not base_year:
        return ""

    current_year = time.localtime().tm_year + 1
    candidate = base_year
    while candidate + 30 <= current_year:
        candidate += 30
    return str(candidate)


def _decode_vin_structure(vin):
    normalized = normalize_vin(vin)
    if len(normalized) != 17:
        return {}

    wmi = normalized[:3]
    vds = normalized[3:9]
    vis = normalized[9:]
    year_code = normalized[9]
    plant_code = normalized[10]
    serial_number = normalized[11:]

    return {
        "vin_wmi": wmi,
        "vin_vds": vds,
        "vin_vis": vis,
        "vin_check_digit": normalized[8],
        "vin_year_code": year_code,
        "vin_model_year_estimate": _decode_vin_year_code(year_code),
        "vin_plant_code": plant_code,
        "vin_serial_number": serial_number,
        "vin_country_hint": VIN_COUNTRY_CODES.get(normalized[0], ""),
    }


def decode_vin_with_nhtsa(vin):
    cached = load_vin_cache(get_setting, vin)
    if cached and cached.get("_cache_version") == 4:
        return cached

    payload = fetch_json(NHTSA_DECODE_URL.format(vin=quote(vin)))
    results = payload.get("Results") or []

    if not results:
        raise RuntimeError("NHTSA returned no VIN data.")

    item = results[0]

    model = _join_vehicle_fields(
        item.get("Model"),
        item.get("Series"),
        item.get("Series2"),
        item.get("Trim"),
        item.get("Trim2"),
    )
    fuel_type = _join_vehicle_fields(
        item.get("FuelTypePrimary"),
        item.get("FuelTypeSecondary"),
        item.get("ElectrificationLevel"),
    )
    body_class = _first_vehicle_field(
        item.get("BodyClass"),
        item.get("VehicleType"),
        item.get("BodyCabType"),
    )
    engine_cylinders = _clean_vehicle_field(item.get("EngineCylinders"))
    displacement_l = _clean_vehicle_field(item.get("DisplacementL"))
    engine_hp = _clean_vehicle_field(item.get("EngineHP"))
    engine_summary = _join_vehicle_fields(
        f"{engine_cylinders} cyl" if engine_cylinders else "",
        f"{displacement_l} L" if displacement_l else "",
        item.get("EngineModel"),
        f"{engine_hp} hp" if engine_hp else "",
    )
    drive_type = _first_vehicle_field(
        item.get("DriveType"),
        item.get("TransmissionStyle"),
    )
    plant_location = _join_vehicle_fields(
        item.get("PlantCity"),
        item.get("PlantState"),
        item.get("PlantCountry"),
        separator=", ",
    )

    decoded = {
        "_cache_version": 4,
        "make": _first_vehicle_field(item.get("Make"), item.get("Manufacturer")),
        "model": model,
        "model_year": _clean_vehicle_field(item.get("ModelYear")),
        "manufacturer": _clean_vehicle_field(item.get("Manufacturer")),
        "vehicle_type": _clean_vehicle_field(item.get("VehicleType")),
        "body_class": body_class,
        "series": _join_vehicle_fields(item.get("Series"), item.get("Series2")),
        "trim": _join_vehicle_fields(item.get("Trim"), item.get("Trim2")),
        "fuel_type": fuel_type,
        "fuel_type_secondary": _clean_vehicle_field(item.get("FuelTypeSecondary")),
        "engine_cylinders": engine_cylinders,
        "engine_displacement_l": displacement_l,
        "engine_model": _clean_vehicle_field(item.get("EngineModel")),
        "engine_power_hp": engine_hp,
        "engine_configuration": _clean_vehicle_field(item.get("EngineConfiguration")),
        "engine_summary": engine_summary,
        "drive_type": drive_type,
        "transmission_style": _clean_vehicle_field(item.get("TransmissionStyle")),
        "plant_country": _clean_vehicle_field(item.get("PlantCountry")),
        "plant_state": _clean_vehicle_field(item.get("PlantState")),
        "plant_city": _clean_vehicle_field(item.get("PlantCity")),
        "plant_company": _clean_vehicle_field(item.get("PlantCompanyName")),
        "plant_location": plant_location,
        "doors": _clean_vehicle_field(item.get("Doors")),
        "seats": _clean_vehicle_field(item.get("Seats")),
        "electrification_level": _clean_vehicle_field(item.get("ElectrificationLevel")),
        "error_code": _clean_vehicle_field(item.get("ErrorCode")),
        "error_text": _clean_vehicle_field(item.get("ErrorText")),
    }
    decoded.update(_decode_vin_structure(vin))
    decoded["model_year"] = _first_vehicle_field(decoded.get("model_year"), decoded.get("vin_model_year_estimate"))
    decoded["plant_location"] = _first_vehicle_field(decoded.get("plant_location"), decoded.get("vin_country_hint"))
    decoded["extra_details"] = _build_vin_extra_details(decoded)
    save_vin_cache(set_setting, vin, decoded)
    return decoded


def normalize_plate(plate):
    return re.sub(r"[^A-Za-z0-9]", "", str(plate or "").upper())


def lookup_plate_with_rdw(plate):
    normalized_plate = normalize_plate(plate)

    if not normalized_plate:
        raise RuntimeError("Plate is empty.")

    where_clause = quote(f"kenteken = '{normalized_plate}'")
    url = (
        f"{RDW_DATASET_URL}?$where={where_clause}"
        "&$limit=1"
    )

    rows = fetch_json(url)

    if not rows:
        raise RuntimeError("No RDW vehicle found for this plate.")

    row = rows[0]

    return normalized_plate, {
        "plate": row.get("kenteken", normalized_plate),
        "brand": row.get("merk", ""),
        "model": row.get("handelsbenaming", ""),
        "vehicle_type": row.get("voertuigsoort", ""),
        "first_registration": row.get("datum_eerste_toelating", ""),
        "first_registration_nl": row.get("datum_eerste_tenaamstelling_in_nederland", ""),
        "apk_expiry": row.get("vervaldatum_apk", ""),
        "fuel": _build_rdw_fuel_description(row),
        "color": row.get("eerste_kleur", ""),
        "seats": row.get("aantal_zitplaatsen", ""),
        "doors": row.get("aantal_deuren", ""),
        "weight_empty": row.get("massa_ledig_voertuig", ""),
        "engine_cc": row.get("cilinderinhoud", ""),
        "cylinders": row.get("aantal_cilinders", ""),
        "power_kw": row.get("vermogen_massarijklaar", ""),
        "emission_class": row.get("emissieklasse", ""),
        "catalog_price": row.get("catalogusprijs", ""),
        "body": row.get("inrichting", ""),
        "wheelbase": row.get("wielbasis", ""),
    }


def refresh_vin_profile():
    global vin_refresh_in_progress

    with vin_refresh_lock:
        if vin_refresh_in_progress:
            return False, "VIN refresh already running."
        vin_refresh_in_progress = True

    if get_demo_mode_enabled():
        update_vehicle_profile(**build_demo_vehicle_profile())
        with vin_refresh_lock:
            vin_refresh_in_progress = False
        return True, "Demo VIN loaded."

    update_vehicle_profile(
        vin_status="loading",
        vin_message="Reading VIN from vehicle...",
        vin_last_update=now_time()
    )

    try:
        vin = read_vin()
        update_vehicle_profile(
            vin=vin,
            vin_status="loading",
            vin_message="VIN found. Loading vehicle details...",
            vin_last_update=now_time()
        )

        decoded = decode_vin_with_nhtsa(vin)
        update_vehicle_profile(
            vin=vin,
            decoded=decoded,
            vin_status="ready",
            vin_message="VIN loaded and decoded successfully.",
            vin_last_update=now_time()
        )
        return True, "VIN loaded successfully."
    except (HTTPError, URLError) as e:
        log_error("Decode VIN", e)
        update_vehicle_profile(
            vin_status="error",
            vin_message="VIN read may have worked, but online decode is unavailable right now.",
            vin_last_update=now_time()
        )
        return False, friendly_message(e, source="Decode VIN")
    except Exception as e:
        log_error("Read VIN", e)
        update_vehicle_profile(
            vin_status="error",
            vin_message=friendly_message(e, source="Read VIN"),
            vin_last_update=now_time()
        )
        return False, friendly_message(e, source="Read VIN")
    finally:
        with vin_refresh_lock:
            vin_refresh_in_progress = False


def auto_refresh_vin_if_needed():
    with state_lock:
        vin = vehicle_profile.get("vin", "")
        vin_status = vehicle_profile.get("vin_status", "idle")

    if vin or vin_status == "loading":
        return

    refresh_vin_profile()


def set_manual_vin(raw_vin):
    vin = normalize_vin(raw_vin)

    if not vin:
        update_vehicle_profile(
            vin_status="error",
            vin_message="Manual VIN is invalid. Use 17 letters and numbers.",
            vin_last_update=now_time()
        )
        return False, "Enter a valid 17-character VIN."

    update_vehicle_profile(
        vin=vin,
        decoded={},
        vin_status="loading",
        vin_message="Manual VIN saved. Loading vehicle details...",
        vin_last_update=now_time()
    )

    try:
        decoded = decode_vin_with_nhtsa(vin)
        update_vehicle_profile(
            vin=vin,
            decoded=decoded,
            vin_status="ready",
            vin_message="Manual VIN loaded and decoded successfully.",
            vin_last_update=now_time()
        )
        return True, "Manual VIN saved."
    except (HTTPError, URLError) as e:
        log_error("Decode VIN", e)
        update_vehicle_profile(
            vin=vin,
            decoded={},
            vin_status="error",
            vin_message="VIN saved, but online vehicle details are unavailable right now.",
            vin_last_update=now_time()
        )
        return False, friendly_message(e, source="Decode VIN")
    except Exception as e:
        log_error("Decode VIN", e)
        update_vehicle_profile(
            vin=vin,
            decoded={},
            vin_status="error",
            vin_message="VIN saved, but vehicle details could not be loaded.",
            vin_last_update=now_time()
        )
        return False, "VIN saved, but vehicle details could not be loaded."


def refresh_plate_profile(plate):
    if get_demo_mode_enabled():
        update_vehicle_profile(
            plate_query=normalize_plate(plate),
            plate_status="ready",
            plate_message="Demo mode does not perform RDW lookups.",
            plate_last_update=now_time(),
            rdw={}
        )
        return True, "Demo mode RDW placeholder loaded."

    update_vehicle_profile(
        plate_query=normalize_plate(plate),
        plate_status="loading",
        plate_message="Looking up RDW vehicle data...",
        plate_last_update=now_time()
    )

    try:
        normalized_plate, rdw_data = lookup_plate_with_rdw(plate)
        update_vehicle_profile(
            plate_query=normalized_plate,
            rdw=rdw_data,
            plate_status="ready",
            plate_message="RDW vehicle data loaded.",
            plate_last_update=now_time()
        )
        return True, "RDW lookup completed."
    except (HTTPError, URLError) as e:
        log_error("Lookup RDW", e)
        update_vehicle_profile(
            plate_status="error",
            plate_message="RDW could not be reached right now.",
            plate_last_update=now_time()
        )
        return False, friendly_message(e, source="Lookup RDW")
    except Exception as e:
        log_error("Lookup RDW", e)
        update_vehicle_profile(
            plate_status="error",
            plate_message=friendly_message(e, source="Lookup RDW"),
            plate_last_update=now_time()
        )
        return False, friendly_message(e, source="Lookup RDW")


def read_dtc(command):
    if command is None:
        return []

    if not connection or not connection.is_connected():
        raise RuntimeError("No OBD connection.")

    try:
        with obd_lock:
            response = connection.query(command)

        if response.is_null() or not response.value:
            return []

        results = []

        for code, description in response.value:
            results.append(enrich_dtc(code, description))

        return results

    except Exception as e:
        raise RuntimeError(f"DTC query failed: {e}") from e


def scan_dtc_codes():
    global dtc_data, freeze_frame_data

    if get_demo_mode_enabled():
        with state_lock:
            demo_preset = normalize_demo_preset(demo_drive_state.get("preset", get_demo_preset_name()))
        demo_dtc = build_demo_dtc_snapshot(demo_preset)
        new_dtc_data = {
            "stored": list(demo_dtc["stored"]),
            "pending": list(demo_dtc["pending"]),
            "permanent": list(demo_dtc["permanent"]),
        }
        with state_lock:
            dtc_data = new_dtc_data
            freeze_frame_data = build_demo_freeze_frame(demo_preset)
            dtc_status["has_scan"] = True
            dtc_status["scanning"] = False
            dtc_status["last_scan"] = now_time()
            dtc_status["message"] = demo_dtc["message"]
        return new_dtc_data

    if not connection or not connection.is_connected():
        raise RuntimeError("No OBD connection.")

    with state_lock:
        dtc_status["scanning"] = True
        dtc_status["message"] = "Scanning fault codes..."
        dtc_status["last_scan"] = now_time()

    try:
        new_dtc_data = {
            "stored": read_dtc(get_command("GET_DTC")),
            "pending": read_dtc(get_command("GET_CURRENT_DTC")),
            "permanent": read_dtc(get_command("GET_PERMANENT_DTC"))
        }
        total = (
            len(new_dtc_data["stored"])
            + len(new_dtc_data["pending"])
            + len(new_dtc_data["permanent"])
        )

        with state_lock:
            dtc_data = new_dtc_data
            freeze_frame_data = get_freeze_frame_snapshot(connection, obd_lock, get_command)
            dtc_status["has_scan"] = True
            dtc_status["scanning"] = False
            dtc_status["last_scan"] = now_time()
            dtc_status["message"] = (
                f"Scan completed. {total} code(s) found."
                if total
                else "Scan completed. No fault codes found."
            )

        return new_dtc_data
    except Exception:
        with state_lock:
            dtc_status["has_scan"] = False
            dtc_status["scanning"] = False
            dtc_status["last_scan"] = now_time()
            dtc_status["message"] = "Fault code scan failed."
        raise


def get_protocol_name():
    try:
        if connection and connection.is_connected():
            return connection.protocol_name()
    except Exception as e:
        log_error("Read protocol", e)

    return "Unknown"


def update_loop():
    global vehicle_data, dtc_data, readiness_data

    last_readiness_refresh = 0

    while True:
        try:
            if get_demo_mode_enabled():
                with state_lock:
                    demo_speed = float(demo_drive_state.get("speed_kmh", 0.0))
                    demo_preset = normalize_demo_preset(demo_drive_state.get("preset", get_demo_preset_name()))
                demo_snapshot = build_demo_vehicle_snapshot(demo_speed, demo_preset)
                now = time.time()
                with state_lock:
                    previous = dict(vehicle_data)
                    vehicle_data = {
                        key: build_live_item(previous.get(key), item["label"], item["value"], now)
                        for key, item in demo_snapshot.items()
                    }
                    readiness_data = build_demo_readiness(demo_preset)
                    obd_status["connected"] = True
                    obd_status["protocol"] = "Simulator"
                    obd_status["error"] = None
                    obd_status["user_message"] = "Demo mode is generating live OBD-II values."
                    obd_status["connecting"] = False
                    obd_status["current_port"] = "Demo mode"
                    obd_status["demo_mode"] = True
                    obd_status["connection_hint"] = detect_connection_hint(None, demo_mode=True)
                    obd_status["last_update"] = now_time()
                    obd_status["last_successful_update"] = obd_status["last_update"]
                    obd_status["poll_interval"] = POLL_INTERVAL
                    obd_status["poll_guard_active"] = False
                    obd_status["poll_guard_reason"] = ""

                with state_lock:
                    if not vehicle_profile.get("vin"):
                        vehicle_profile.update(build_demo_vehicle_profile())

                time.sleep(POLL_INTERVAL)
                continue

            if not connection or not connection.is_connected():
                reset_readiness_state()
                refresh_vehicle_stale_flags()
                set_status(
                    False,
                    error="OBD not connected. Reconnecting...",
                    user_message="Connection lost. Trying to reconnect...",
                    connecting=True
                )
                connect_obd()
                with state_lock:
                    current_error = obd_status.get("error")
                time.sleep(8 if is_known_port_config_error(current_error) else 3)
                continue

            with state_lock:
                previous_data = dict(vehicle_data)

            data = {}
            cycle_time = time.time()

            for key, item in get_active_live_commands().items():
                label, command = item
                value = safe_query(command)
                data[key] = {
                    **build_live_item(previous_data.get(key), label, value, cycle_time),
                }

            protocol = get_protocol_name()
            now = time.time()

            if now - last_readiness_refresh >= 5:
                readiness_snapshot = get_readiness_snapshot(connection, obd_lock, get_command)
                with state_lock:
                    readiness_data = readiness_snapshot
                last_readiness_refresh = now

            with state_lock:
                for fast_key, fallback_label in {
                    "rpm": "RPM",
                    "speed": "Speed",
                    "engine_load": "Engine load",
                    "throttle": "Throttle position",
                }.items():
                    data[fast_key] = dict(vehicle_data.get(fast_key, previous_data.get(fast_key, {
                        "label": fallback_label,
                        "value": "N/A"
                    })))
                vehicle_data = data
                obd_status["connected"] = True
                obd_status["protocol"] = protocol
                obd_status["error"] = None
                obd_status["user_message"] = "Live data is updating."
                obd_status["connecting"] = False
                obd_status["demo_mode"] = False
                obd_status["limited_mode"] = bool(get_poll_profile()["limited"])
                obd_status["last_update"] = time.strftime("%H:%M:%S")
                obd_status["last_successful_update"] = obd_status["last_update"]
                obd_status["connection_hint"] = detect_connection_hint(connection, None)

            time.sleep(current_live_poll_interval)

        except Exception as e:
            log_error("Update loop", e)
            set_status(False, error=str(e))
            time.sleep(max(current_live_poll_interval, 0.3))


def rpm_update_loop():
    global vin_autoload_attempted

    while True:
        try:
            if get_demo_mode_enabled():
                with state_lock:
                    demo_speed = float(demo_drive_state.get("speed_kmh", 0.0))
                    demo_preset = normalize_demo_preset(demo_drive_state.get("preset", get_demo_preset_name()))
                demo_rpm = build_demo_vehicle_snapshot(demo_speed, demo_preset).get("rpm", {}).get("value", "N/A")
                set_vehicle_value("rpm", "RPM", demo_rpm)
                time.sleep(POLL_INTERVAL)
                continue

            if not connection or not connection.is_connected():
                vin_autoload_attempted = False
                time.sleep(0.25)
                continue

            rpm_value = safe_query(RPM_COMMAND)
            set_vehicle_value("rpm", "RPM", rpm_value)
            speed_value = safe_query(SPEED_COMMAND)
            set_vehicle_value("speed", "Speed", speed_value)
            engine_load_value = safe_query(ENGINE_LOAD_COMMAND)
            set_vehicle_value("engine_load", "Engine load", engine_load_value)
            throttle_value = safe_query(THROTTLE_COMMAND)
            set_vehicle_value("throttle", "Throttle position", throttle_value)

            with state_lock:
                vin = vehicle_profile.get("vin", "")
                vin_status = vehicle_profile.get("vin_status", "idle")
                should_refresh_vin = (
                    not vin
                    and not vin_autoload_attempted
                    and vin_status not in {"loading", "ready"}
                )

            if should_refresh_vin:
                vin_autoload_attempted = True
                threading.Thread(target=auto_refresh_vin_if_needed, daemon=True).start()

            time.sleep(RPM_POLL_INTERVAL)
        except Exception as e:
            log_error("RPM update loop", e)
            time.sleep(0.25)


@app.route("/")
def dashboard():
    try:
        return render_template("dashboard.html")
    except Exception as e:
        log_error("Render dashboard", e)
        return "Dashboard could not load. Check the console.", 500


@app.route("/api/status")
def api_status():
    with state_lock:
        status = dict(obd_status)
    status["limited_mode"] = bool(get_poll_profile()["limited"])
    connection_quality = (
        {
            "phase": "Demo mode",
            "adapter_connected": True,
            "port_powered": True,
            "car_connected": True,
            "live_data_active": True,
        }
        if status.get("demo_mode")
        else build_connection_quality_snapshot(connection, status.get("connecting"), status.get("error"))
    )
    connection_quality = enrich_connection_quality(status, connection_quality)
    return jsonify({
        **status,
        "poll_profile": get_poll_profile(),
        "connection_quality": connection_quality,
        "session_state": build_scanner_session_state(
            status,
            connection_quality,
            status.get("connection_hint"),
        ),
    })


@app.route("/api/connection/test", methods=["POST"])
def api_connection_test():
    if get_demo_mode_enabled():
        return jsonify({
            "success": True,
            "phase": "Demo mode",
            "protocol": "Simulator",
            "steps": [
                {"name": "USB adapter detected", "ok": True, "detail": "Simulated adapter"},
                {"name": "OBD protocol detected", "ok": True, "detail": "Simulator"},
                {"name": "ECU responding", "ok": True, "detail": "Demo ECU"},
            ]
        })

    with state_lock:
        current_status = dict(obd_status)

    if connection and current_status.get("connected"):
        protocol = current_status.get("protocol") or "Unknown"
        port = current_status.get("current_port") or "auto-detect"
        return jsonify({
            "success": True,
            "phase": "Using current live connection",
            "protocol": protocol,
            "steps": [
                {"name": "USB adapter detected", "ok": True, "detail": port},
                {"name": "OBD protocol detected", "ok": True, "detail": protocol},
                {"name": "ECU responding", "ok": True, "detail": "Live session already active"},
            ]
        })

    result = run_connection_test(obd, get_configured_port())
    return jsonify(result), (200 if result.get("success") else 400)


@app.route("/api/data")
def api_data():
    payload = current_scan_payload()
    with state_lock:
        payload["dtc_status"] = dict(dtc_status)
    return jsonify(payload)


@app.route("/api/report")
def api_report():
    payload = current_scan_payload()
    return jsonify(payload.get("report", {}))


@app.route("/api/report/export")
def api_report_export():
    payload = current_scan_payload()
    filename = f"obd-scan-report-{time.strftime('%Y%m%d-%H%M%S')}.html"
    return Response(
        render_export_html(payload),
        mimetype="text/html",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/api/codes/scan", methods=["POST"])
def api_codes_scan():
    try:
        scan_dtc_codes()
        payload = current_scan_payload()
        with state_lock:
            payload["success"] = True
            payload["message"] = dtc_status["message"]
            payload["dtc_status"] = dict(dtc_status)
        return jsonify(payload)
    except Exception as e:
        log_error("Read DTC", e)
        payload = current_scan_payload()
        with state_lock:
            payload["success"] = False
            payload["message"] = friendly_message(e, source="Read DTC")
            payload["dtc_status"] = dict(dtc_status)
        return jsonify(payload), 400


@app.route("/api/clear", methods=["POST"])
def clear_codes():
    if not connection or not connection.is_connected():
        return jsonify({
            "success": False,
            "message": "No OBD connection."
        }), 400

    with state_lock:
        safe_mode_enabled = obd_status["safe_mode"]

    if safe_mode_enabled:
        return jsonify({
            "success": False,
            "message": "SAFE Mode is active. Clearing fault codes is blocked."
        }), 400

    payload = request.get_json(silent=True) or {}
    confirm = payload.get("confirm")

    if confirm != "YES":
        return jsonify({
            "success": False,
            "message": "Confirmation is missing."
        }), 400

    try:
        with obd_lock:
            clear_command = get_command("CLEAR_DTC")
            if clear_command is None:
                raise RuntimeError("CLEAR_DTC command is not available.")

            connection.query(clear_command)
        with state_lock:
            dtc_status["scanning"] = False
            dtc_status["message"] = "Clear command sent. Run a new scan to verify the ECU is clean."
        return jsonify({
            "success": True,
            "message": "Clear command sent. Turn ignition off/on if needed and scan again."
        })

    except Exception as e:
        log_error("Clear fault codes", e)
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@app.route("/api/safe-mode", methods=["POST"])
def set_safe_mode():
    try:
        payload = request.get_json(silent=True) or {}
        enabled = bool(payload.get("enabled", True))

        with state_lock:
            obd_status["safe_mode"] = enabled

        return jsonify({
            "success": True,
            "safe_mode": enabled
        })
    except Exception as e:
        log_error("Change SAFE Mode", e)
        return jsonify({
            "success": False,
            "message": str(e)
        }), 500


@app.route("/api/config")
def api_config():
    return jsonify({
        "app_version": APP_VERSION,
        "obd_port": get_configured_port() or "",
        "detected_ports": list_serial_ports(),
        "demo_mode": get_demo_mode_enabled(),
        "limited_mode": bool(get_poll_profile()["limited"]),
        "poll_profile": get_poll_profile(),
        "poll_profiles": [{"id": key, **value} for key, value in POLL_PROFILES.items()],
        "demo_preset": get_demo_preset_name(),
        "demo_presets": get_demo_presets(),
        "poll_interval": POLL_INTERVAL,
    })


@app.route("/api/poll-profile", methods=["POST"])
def api_poll_profile():
    try:
        payload = request.get_json(silent=True) or {}
        profile = normalize_poll_profile(payload.get("profile", "balanced"))

        if not set_poll_profile_name(profile):
            return jsonify({
                "success": False,
                "message": "Polling profile could not be saved."
            }), 500

        profile_meta = get_poll_profile()
        with state_lock:
            obd_status["limited_mode"] = bool(profile_meta["limited"])
            obd_status["last_update"] = time.strftime("%H:%M:%S")
            obd_status["user_message"] = f"{profile_meta['label']} polling profile active."

        return jsonify({
            "success": True,
            "poll_profile": profile_meta,
            "limited_mode": bool(profile_meta["limited"]),
            "status": dict(obd_status),
        })
    except Exception as e:
        log_error("Change polling profile", e)
        return jsonify({
            "success": False,
            "message": "Polling profile could not be changed."
        }), 500


@app.route("/api/config/ports")
def api_ports():
    return jsonify({
        "ports": list_serial_ports(),
        "selected": get_configured_port() or "",
    })


@app.route("/api/config/port", methods=["POST"])
def set_obd_port():
    global connection, vehicle_data, dtc_data

    try:
        payload = request.get_json(silent=True) or {}
        port = str(payload.get("port", "")).strip().upper()

        if not set_setting("obd_port", port):
            return jsonify({
                "success": False,
                "message": "COM port could not be saved."
            }), 500

        with obd_lock:
            try:
                if connection:
                    connection.close()
            except Exception as e:
                log_error("Close OBD connection", e)
            finally:
                connection = None

        with state_lock:
            vehicle_data = {}
            obd_status["connected"] = False
            obd_status["protocol"] = "Unknown"
            obd_status["current_port"] = port or None
            obd_status["error"] = "COM port changed. Reconnecting..."
            obd_status["user_message"] = (
                f"COM port saved to {port}. Reconnecting..." if port else "No COM port selected. Reconnecting..."
            )
            obd_status["connecting"] = True
            obd_status["last_update"] = time.strftime("%H:%M:%S")

        reset_vehicle_profile()
        reset_readiness_state()
        reset_dtc_state("COM port changed. Run a new fault code scan after reconnecting.")
        connect_obd()

        return jsonify({
            "success": True,
            "message": f"COM port saved: {port}" if port else "COM selection cleared. No COM port selected.",
            "obd_port": port,
            "detected_ports": list_serial_ports(),
            "status": dict(obd_status)
        })
    except Exception as e:
        log_error("Change COM port", e)
        return jsonify({
            "success": False,
            "message": friendly_message(e, source="Change COM port", port=port if "port" in locals() else None)
        }), 500


@app.route("/api/supported")
def supported_commands():
    try:
        support = build_pid_support_summary()
        return jsonify({
            **support,
            "standard_obd_only": True,
        })
    except Exception as e:
        log_error("Read supported commands", e)
        return jsonify({
            "supported": [],
            "unsupported": [],
            "standard_obd_only": True,
        })


@app.route("/api/demo-mode", methods=["POST"])
def api_demo_mode():
    global connection, vehicle_data, query_error_streak, current_live_poll_interval

    payload = request.get_json(silent=True) or {}
    enabled = bool(payload.get("enabled", False))
    demo_preset = get_demo_preset_name()

    if not set_demo_mode_enabled(enabled):
        return jsonify({
            "success": False,
            "message": "Demo mode could not be saved."
        }), 500

    with obd_lock:
        try:
            if connection:
                connection.close()
        except Exception as e:
            log_error("Close OBD connection", e)
        finally:
            connection = None

    with state_lock:
        vehicle_data = {}
        obd_status["demo_mode"] = enabled
        obd_status["current_port"] = "Demo mode" if enabled else get_configured_port()

    query_error_streak = 0
    current_live_poll_interval = POLL_INTERVAL
    apply_demo_preset_state(demo_preset, reset_speed=True)
    reset_readiness_state()
    reset_dtc_state("Demo mode changed. Run a manual fault code scan again if needed.")
    reset_vehicle_profile()
    connect_obd()

    with state_lock:
        return jsonify({
            "success": True,
            "demo_mode": enabled,
            "demo_preset": demo_preset,
            "status": dict(obd_status),
        })


@app.route("/api/demo-mode/preset", methods=["POST"])
def api_demo_preset():
    payload = request.get_json(silent=True) or {}
    requested_preset = payload.get("preset", "idle")
    preset_name = normalize_demo_preset(requested_preset)

    if not set_demo_preset_name(preset_name):
        return jsonify({
            "success": False,
            "message": "Demo preset could not be saved."
        }), 500

    preset_name, speed = apply_demo_preset_state(preset_name, reset_speed=True)

    with state_lock:
        if obd_status.get("demo_mode"):
            obd_status["last_update"] = now_time()
            obd_status["user_message"] = f"Demo preset switched to {get_demo_preset(preset_name)[1]['label']}."

    reset_readiness_state()
    reset_dtc_state("Demo preset changed. Run a manual fault code scan again if needed.")
    with state_lock:
        freeze_frame_data["available"] = False
        freeze_frame_data["values"] = {}

    return jsonify({
        "success": True,
        "demo_preset": preset_name,
        "demo_presets": get_demo_presets(),
        "speed_kmh": speed,
    })


@app.route("/api/errors")
def api_errors():
    with state_lock:
        return jsonify(list(obd_status["recent_errors"]))


@app.route("/api/vehicle")
def api_vehicle():
    with state_lock:
        return jsonify(dict(vehicle_profile))


@app.route("/api/vehicle/refresh", methods=["POST"])
def api_vehicle_refresh():
    success, message = refresh_vin_profile()

    with state_lock:
        payload = dict(vehicle_profile)

    status_code = 200 if success else 400
    return jsonify({
        "success": success,
        "message": message,
        "vehicle_profile": payload
    }), status_code


@app.route("/api/vehicle/manual", methods=["POST"])
def api_vehicle_manual():
    payload = request.get_json(silent=True) or {}
    success, message = set_manual_vin(payload.get("vin", ""))

    with state_lock:
        profile_payload = dict(vehicle_profile)

    status_code = 200 if success else 400
    return jsonify({
        "success": success,
        "message": message,
        "vehicle_profile": profile_payload
    }), status_code


@app.route("/api/vehicle/plate", methods=["POST"])
def api_vehicle_plate():
    payload = request.get_json(silent=True) or {}
    plate = payload.get("plate", "")
    success, message = refresh_plate_profile(plate)

    with state_lock:
        profile_payload = dict(vehicle_profile)

    status_code = 200 if success else 400
    return jsonify({
        "success": success,
        "message": message,
        "vehicle_profile": profile_payload
    }), status_code


@app.route("/api/scans")
def api_scans():
    try:
        return jsonify(get_recent_scans())
    except Exception as e:
        log_error("Read scans", e)
        return jsonify([])


@app.route("/api/scans/save", methods=["POST"])
def api_scans_save():
    payload = request.get_json(silent=True) or {}
    label = str(payload.get("label", "")).strip() or "Manual scan snapshot"

    try:
        saved = save_scan_snapshot(label)
        return jsonify({
            "success": True,
            "scan": saved,
            "scans": get_recent_scans()
        })
    except Exception as e:
        log_error("Save scan snapshot", e)
        return jsonify({
            "success": False,
            "message": "Could not save the scan snapshot."
        }), 500


@app.route("/api/garage-notes")
def api_garage_notes():
    try:
        notes = get_recent_garage_notes()
        notes = filter_garage_notes(
            notes,
            request.args.get("vin", ""),
            request.args.get("plate", ""),
        )
        return jsonify(notes)
    except Exception as e:
        log_error("Read garage notes", e)
        return jsonify([])


@app.route("/api/garage-notes/export")
def api_garage_notes_export():
    try:
        vin = request.args.get("vin", "")
        plate = request.args.get("plate", "")
        notes = filter_garage_notes(get_recent_garage_notes(), vin, plate)
        filename = f"garage-notes-{time.strftime('%Y%m%d-%H%M%S')}.html"
        return Response(
            render_garage_notes_export_html(notes, vin, plate),
            mimetype="text/html",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        log_error("Export garage notes", e)
        return "Garage notes export could not be created.", 500


@app.route("/api/garage-notes", methods=["POST"])
def api_garage_notes_save():
    payload = request.get_json(silent=True) or {}
    with state_lock:
        profile = dict(vehicle_profile)

    vin = normalize_vin(payload.get("vin") or profile.get("vin") or "")
    plate = normalize_garage_plate(payload.get("plate") or profile.get("plate_query") or "")
    title = str(payload.get("title", "")).strip()
    mileage = str(payload.get("mileage", "")).strip()
    note = str(payload.get("note", "")).strip()

    if not vin or not plate:
        return jsonify({
            "success": False,
            "message": "Garage notes require both VIN and license plate. Enter them manually or load/detect them first."
        }), 400

    if not note:
        return jsonify({
            "success": False,
            "message": "Note text is required."
        }), 400

    try:
        saved = save_garage_note_snapshot(vin, plate, title, mileage, note)
        return jsonify({
            "success": True,
            "note": saved,
            "notes": get_recent_garage_notes(),
        })
    except Exception as e:
        log_error("Save garage note", e)
        return jsonify({
            "success": False,
            "message": "Garage note could not be saved."
        }), 500


@app.route("/api/reconnect", methods=["POST"])
def reconnect_obd():
    global connection, vehicle_data, dtc_data

    try:
        with state_lock:
            obd_status["connected"] = False
            obd_status["protocol"] = "Unknown"
            obd_status["error"] = "Manual reconnect requested."
            obd_status["user_message"] = "Manual reconnect started. Checking adapter..."
            obd_status["connecting"] = True
            obd_status["last_update"] = time.strftime("%H:%M:%S")
            vehicle_data = {}

        reset_vehicle_profile()
        reset_readiness_state()
        reset_dtc_state("Reconnect started. Run a new fault code scan after the adapter is back online.")
        with obd_lock:
            try:
                if connection:
                    connection.close()
            except Exception as e:
                log_error("Close OBD connection", e)
            finally:
                connection = None

        connect_obd()

        with state_lock:
            return jsonify({
                "success": True,
                "message": obd_status["user_message"],
                "status": dict(obd_status)
            })
    except Exception as e:
        log_error("Reconnect OBD", e)
        return jsonify({
            "success": False,
            "message": friendly_message(e, source="Connect OBD")
        }), 500


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        return jsonify({
            "success": False,
            "message": error.description
        }), error.code

    log_error("Flask route", error)
    return jsonify({
        "success": False,
        "message": str(error)
    }), 500


if __name__ == "__main__":
    init_config_db()
    connect_obd()
    threading.Thread(target=update_loop, daemon=True).start()
    threading.Thread(target=rpm_update_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=True)
