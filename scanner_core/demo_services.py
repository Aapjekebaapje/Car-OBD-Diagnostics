# Made by The Syndicate Development
import math
import time

from scanner_core.dtc_catalog import enrich_dtc


DEMO_PRESETS = {
    "idle": {
        "label": "Idle",
        "description": "Calm warm idle with healthy trims and no active diagnostic faults.",
        "default_speed_kmh": 0.0,
    },
    "cruise": {
        "label": "Cruise",
        "description": "Stable highway-style cruise with moderate RPM and healthy ECU values.",
        "default_speed_kmh": 88.0,
    },
    "heavy_load": {
        "label": "Heavy load",
        "description": "High throttle, higher temperatures and strong engine load for stress testing the UI.",
        "default_speed_kmh": 132.0,
    },
    "fault_present": {
        "label": "Fault present",
        "description": "MIL-on style scenario with rougher trims, incomplete readiness and demo fault codes.",
        "default_speed_kmh": 42.0,
    },
}


def normalize_demo_preset(name):
    preset = str(name or "").strip().lower().replace("-", "_").replace(" ", "_")
    return preset if preset in DEMO_PRESETS else "idle"


def get_demo_presets():
    return [
        {
            "id": preset_id,
            "label": preset["label"],
            "description": preset["description"],
            "default_speed_kmh": preset["default_speed_kmh"],
        }
        for preset_id, preset in DEMO_PRESETS.items()
    ]


def get_demo_preset(name):
    preset_id = normalize_demo_preset(name)
    return preset_id, dict(DEMO_PRESETS[preset_id])


def get_demo_default_speed(name):
    _, preset = get_demo_preset(name)
    return float(preset["default_speed_kmh"])


def _animated_demo_speed(base_speed, preset_id, now):
    base = max(0.0, min(220.0, float(base_speed or 0.0)))

    if preset_id == "cruise":
        wave = math.sin(now * 0.42) * 6.0 + math.sin(now * 0.13) * 2.5
        return max(72.0, min(108.0, base + wave))
    if preset_id == "heavy_load":
        wave = abs(math.sin(now * 0.55)) * 16.0 + math.sin(now * 0.22) * 5.0
        return max(108.0, min(168.0, base + wave))
    if preset_id == "fault_present":
        wave = math.sin(now * 0.95) * 8.0 + math.sin(now * 0.31) * 4.0
        return max(18.0, min(62.0, base + wave))

    wave = abs(math.sin(now * 0.85)) * 3.0
    return max(0.0, min(8.0, base + wave))


def build_demo_vehicle_snapshot(speed_kmh=0.0, preset="idle"):
    now = time.time()
    preset_id = normalize_demo_preset(preset)
    speed = _animated_demo_speed(speed_kmh, preset_id, now)
    displayed_speed = max(0, int(round(speed)))

    if preset_id == "cruise":
        base_idle_rpm = 980.0 + math.sin(now * 1.5) * 18.0
        load_factor = speed * 16.5
        transient = math.sin(now * 1.9) * 48.0
        coolant = round(89.0 + min(6.0, speed * 0.024) + math.sin(now * 0.08) * 0.6, 1)
        load = round(min(58.0, 26.0 + speed * 0.14 + abs(math.sin(now * 1.1)) * 2.0), 1)
        fuel_trim = round(math.sin(now * 0.7) * 1.1, 1)
        voltage = round(13.95 + math.sin(now * 0.2) * 0.05, 2)
        maf = round(11.5 + speed * 0.09 + abs(math.sin(now * 1.4)) * 0.35, 2)
        throttle = round(min(33.0, 13.0 + speed * 0.08 + abs(math.sin(now * 1.2)) * 1.4), 1)
        fuel_status = "Closed loop"
        oil_temp = 90
        intake_temp = 29
        ambient_temp = 22
        intake_pressure = 41
        fuel_pressure = 332
        barometric_pressure = 101
        timing_advance = 18
        short_trim = round(math.sin(now * 0.8) * 0.8, 1)
        fuel_level = 58
        runtime = "00:34:12"
        distance_mil = "0 km"
        warmups = "12"
        distance_since_clear = "328 km"
        time_since_clear = "540 min"
    elif preset_id == "heavy_load":
        base_idle_rpm = 1180.0 + math.sin(now * 1.9) * 26.0
        load_factor = speed * 24.0
        transient = math.sin(now * 2.6) * min(220.0, speed * 1.8)
        coolant = round(93.0 + min(10.0, speed * 0.03) + abs(math.sin(now * 0.16)) * 1.4, 1)
        load = round(min(96.0, 58.0 + speed * 0.2 + abs(math.sin(now * 1.6)) * 5.0), 1)
        fuel_trim = round(2.8 + math.sin(now * 0.8) * 1.2, 1)
        voltage = round(13.65 - min(0.28, speed * 0.0013) + math.sin(now * 0.35) * 0.05, 2)
        maf = round(18.8 + speed * 0.14 + abs(math.sin(now * 2.1)) * 0.9, 2)
        throttle = round(min(92.0, 34.0 + speed * 0.22 + abs(math.sin(now * 1.7)) * 4.6), 1)
        fuel_status = "Closed loop"
        oil_temp = 101
        intake_temp = 34
        ambient_temp = 23
        intake_pressure = 62
        fuel_pressure = 380
        barometric_pressure = 100
        timing_advance = 11
        short_trim = round(1.8 + math.sin(now * 0.9) * 1.0, 1)
        fuel_level = 46
        runtime = "00:52:48"
        distance_mil = "0 km"
        warmups = "16"
        distance_since_clear = "612 km"
        time_since_clear = "880 min"
    elif preset_id == "fault_present":
        base_idle_rpm = 910.0 + math.sin(now * 3.8) * 82.0
        load_factor = speed * 14.0
        transient = math.sin(now * 5.4) * min(180.0, 70.0 + speed * 1.4)
        coolant = round(87.0 + min(7.0, speed * 0.018) + math.sin(now * 0.2) * 1.3, 1)
        load = round(min(71.0, 24.0 + speed * 0.18 + abs(math.sin(now * 2.7)) * 8.5), 1)
        fuel_trim = round(13.2 + math.sin(now * 1.3) * 1.8, 1)
        voltage = round(13.52 + math.sin(now * 0.45) * 0.09, 2)
        maf = round(7.6 + speed * 0.08 + abs(math.sin(now * 2.5)) * 0.8, 2)
        throttle = round(min(42.0, 12.0 + speed * 0.12 + abs(math.sin(now * 2.0)) * 4.2), 1)
        fuel_status = "Closed loop / trim compensating"
        oil_temp = 88
        intake_temp = 31
        ambient_temp = 20
        intake_pressure = 46
        fuel_pressure = 315
        barometric_pressure = 99
        timing_advance = 7
        short_trim = round(7.4 + math.sin(now * 1.6) * 2.2, 1)
        fuel_level = 37
        runtime = "00:14:26"
        distance_mil = "18 km"
        warmups = "1"
        distance_since_clear = "14 km"
        time_since_clear = "22 min"
    else:
        base_idle_rpm = 820.0 + math.sin(now * 2.4) * 25.0
        load_factor = speed * 26.0
        transient = math.sin(now * 3.2) * min(140.0, speed * 2.2)
        coolant = round(86.0 + min(9.0, speed * 0.035) + math.sin(now * 0.1) * 1.2, 1)
        load = round(min(89.0, 18.0 + speed * 0.42 + abs(math.sin(now * 1.6)) * 4.0), 1)
        fuel_trim = round(math.sin(now * 0.9) * 2.4, 1)
        voltage = round(13.9 - min(0.45, speed * 0.002) + math.sin(now * 0.3) * 0.08, 2)
        maf = round(4.8 + speed * 0.11 + abs(math.sin(now * 1.8)) * 0.5, 2)
        throttle = round(min(78.0, 7.0 + speed * 0.3 + abs(math.sin(now * 1.4)) * 3.0), 1)
        fuel_status = "Closed loop"
        oil_temp = 84
        intake_temp = 27
        ambient_temp = 21
        intake_pressure = 38
        fuel_pressure = 320
        barometric_pressure = 100
        timing_advance = 12
        short_trim = 1.6
        fuel_level = 63
        runtime = "00:18:32"
        distance_mil = "0 km"
        warmups = "9"
        distance_since_clear = "186 km"
        time_since_clear = "240 min"

    rpm = max(760, min(7800, int(round(base_idle_rpm + load_factor + transient))))

    return {
        "status": {"label": "Monitor status", "value": f"Demo preset: {DEMO_PRESETS[preset_id]['label']}"},
        "fuel_status": {"label": "Fuel system", "value": fuel_status},
        "rpm": {"label": "RPM", "value": f"{rpm} RPM"},
        "speed": {"label": "Speed", "value": f"{displayed_speed} km/h"},
        "coolant_temp": {"label": "Coolant temperature", "value": f"{coolant} C"},
        "oil_temp": {"label": "Oil temperature", "value": f"{oil_temp} C"},
        "intake_temp": {"label": "Intake air temperature", "value": f"{intake_temp} C"},
        "ambient_temp": {"label": "Ambient air temperature", "value": f"{ambient_temp} C"},
        "engine_load": {"label": "Engine load", "value": f"{load} %"},
        "throttle": {"label": "Throttle position", "value": f"{throttle} %"},
        "intake_pressure": {"label": "Intake manifold pressure", "value": f"{intake_pressure} kPa"},
        "fuel_pressure": {"label": "Fuel pressure", "value": f"{fuel_pressure} kPa"},
        "barometric_pressure": {"label": "Barometric pressure", "value": f"{barometric_pressure} kPa"},
        "timing_advance": {"label": "Timing advance", "value": f"{timing_advance} deg"},
        "short_fuel_trim_1": {"label": "Short fuel trim bank 1", "value": f"{short_trim} %"},
        "long_fuel_trim_1": {"label": "Long fuel trim bank 1", "value": f"{fuel_trim} %"},
        "maf": {"label": "MAF air flow", "value": f"{maf} g/s"},
        "fuel_level": {"label": "Fuel level", "value": f"{fuel_level} %"},
        "runtime": {"label": "Engine runtime", "value": runtime},
        "distance_mil": {"label": "Distance with MIL on", "value": distance_mil},
        "control_voltage": {"label": "ECU voltage", "value": f"{voltage} V"},
        "voltage": {"label": "Adapter voltage", "value": f"{round(voltage + 0.1, 2)} V"},
        "warmups_since_clear": {"label": "Warmups since codes cleared", "value": warmups},
        "distance_since_clear": {"label": "Distance since codes cleared", "value": distance_since_clear},
        "time_since_clear": {"label": "Time since codes cleared", "value": time_since_clear},
    }


def build_demo_readiness(preset="idle"):
    preset_id = normalize_demo_preset(preset)

    if preset_id == "fault_present":
        return {
            "available": True,
            "mil": True,
            "dtc_count": 2,
            "ignition_type": "Spark",
            "monitors": [
                {"name": "Misfire", "available": True, "complete": False},
                {"name": "Fuel System", "available": True, "complete": False},
                {"name": "Components", "available": True, "complete": True},
                {"name": "Catalyst", "available": True, "complete": False},
                {"name": "Evap System", "available": True, "complete": False},
                {"name": "Oxygen Sensor", "available": True, "complete": True},
            ],
        }

    if preset_id == "heavy_load":
        monitors = [
            {"name": "Misfire", "available": True, "complete": True},
            {"name": "Fuel System", "available": True, "complete": True},
            {"name": "Components", "available": True, "complete": True},
            {"name": "Catalyst", "available": True, "complete": True},
            {"name": "Evap System", "available": True, "complete": False},
            {"name": "Oxygen Sensor", "available": True, "complete": True},
        ]
    else:
        monitors = [
            {"name": "Misfire", "available": True, "complete": True},
            {"name": "Fuel System", "available": True, "complete": True},
            {"name": "Components", "available": True, "complete": True},
            {"name": "Catalyst", "available": True, "complete": True},
            {"name": "Evap System", "available": True, "complete": True if preset_id == "cruise" else False},
            {"name": "Oxygen Sensor", "available": True, "complete": True},
        ]

    return {
        "available": True,
        "mil": False,
        "dtc_count": 0,
        "ignition_type": "Spark",
        "monitors": monitors,
    }


def build_demo_freeze_frame(preset="idle"):
    preset_id = normalize_demo_preset(preset)

    if preset_id != "fault_present":
        return {
            "available": False,
            "values": {},
        }

    return {
        "available": True,
        "values": {
            "trigger_code": "P0301",
            "rpm": "1280 RPM",
            "speed": "42 km/h",
            "coolant_temp": "88 C",
            "engine_load": "47 %",
            "long_fuel_trim_1": "14.8 %",
            "control_voltage": "13.6 V",
        },
    }


def build_demo_dtc_snapshot(preset="idle"):
    preset_id = normalize_demo_preset(preset)

    if preset_id != "fault_present":
        return {
            "stored": [],
            "pending": [],
            "permanent": [],
            "message": "Demo code scan completed. No fault codes found for this preset.",
        }

    return {
        "stored": [enrich_dtc("P0171", "")],
        "pending": [enrich_dtc("P0301", "")],
        "permanent": [],
        "message": "Demo code scan completed. 2 code(s) found.",
    }


def build_demo_vehicle_profile():
    return {
        "vin": "WVWZZZ1JZXW000001",
        "vin_status": "ready",
        "vin_message": "Demo VIN loaded locally.",
        "vin_last_update": time.strftime("%H:%M:%S"),
        "decoded": {
            "make": "Volkswagen",
            "model": "Golf",
            "model_year": "2008",
            "fuel_type": "Gasoline",
            "body_class": "Hatchback",
            "engine_cylinders": "4",
            "engine_displacement_l": "1.6",
            "drive_type": "FWD",
            "plant_country": "Germany",
        },
        "plate_query": "",
        "plate_status": "idle",
        "plate_message": "Demo mode does not use RDW lookup.",
        "plate_last_update": None,
        "rdw": {},
    }
