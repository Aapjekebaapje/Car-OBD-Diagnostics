try:
    import obd
    from obd.OBDResponse import StatusTest
    from obd.utils import OBDStatus
except Exception:
    obd = None
    OBDStatus = None
    StatusTest = None

try:
    from serial.tools import list_ports
except Exception:
    list_ports = None


READINESS_ORDER = [
    "misfire",
    "fuel_system",
    "components",
    "catalyst",
    "heated_catalyst",
    "evap_system",
    "secondary_air_system",
    "ac_refrigerant",
    "oxygen_sensor",
    "oxygen_sensor_heater",
    "egr_system",
]


FREEZE_FRAME_COMMANDS = {
    "trigger_code": "FREEZE_DTC",
    "rpm": "DTC_RPM",
    "speed": "DTC_SPEED",
    "coolant_temp": "DTC_COOLANT_TEMP",
    "engine_load": "DTC_ENGINE_LOAD",
    "fuel_status": "DTC_FUEL_STATUS",
    "short_fuel_trim_1": "DTC_SHORT_FUEL_TRIM_1",
    "long_fuel_trim_1": "DTC_LONG_FUEL_TRIM_1",
    "intake_pressure": "DTC_INTAKE_PRESSURE",
    "intake_temp": "DTC_INTAKE_TEMP",
    "maf": "DTC_MAF",
    "throttle": "DTC_THROTTLE_POS",
    "control_voltage": "DTC_CONTROL_MODULE_VOLTAGE",
}


def _safe_query(connection, lock, command):
    if command is None or connection is None or not connection.is_connected():
        return None

    try:
        if hasattr(connection, "supports") and not connection.supports(command):
            return None
    except Exception:
        return None

    try:
        with lock:
            response = connection.query(command)
        if response.is_null():
            return None
        return response.value
    except Exception:
        return None


def connection_quality_snapshot(connection, connecting=False, error=None):
    phase = "Not Connected"

    try:
        if connection and hasattr(connection, "status"):
            phase = str(connection.status() or "Not Connected")
    except Exception:
        phase = "Not Connected"

    car_connected = bool(connection and connection.is_connected())
    adapter_connected = phase in {"ELM Connected", "OBD Connected", "Car Connected"} or car_connected
    port_powered = phase in {"OBD Connected", "Car Connected"} or car_connected
    live_data_active = bool(car_connected and not connecting)

    return {
        "phase": phase,
        "adapter_connected": adapter_connected,
        "port_powered": port_powered,
        "car_connected": car_connected,
        "live_data_active": live_data_active,
    }


def detect_connection_hint(connection, error=None, demo_mode=False):
    if demo_mode:
        return {
            "kind": "demo",
            "label": "Demo mode active",
            "detail": "The app is simulating a standard OBD-II session for UI testing.",
        }

    message = str(error or "").lower()
    quality = connection_quality_snapshot(connection, False, error)
    phase = quality["phase"].lower()

    if "usb obd adapter" in message or "could not open port" in message or "not detected" in message:
        return {
            "kind": "adapter_missing",
            "label": "USB adapter not detected",
            "detail": "Plug in the USB OBD adapter or choose the correct COM port.",
        }

    if quality["adapter_connected"] and not quality["car_connected"]:
        if "elm connected" in phase:
            return {
                "kind": "ignition_likely_off",
                "label": "Ignition likely off",
                "detail": "The USB adapter responds, but the ECU is not answering yet.",
            }
        return {
            "kind": "ecu_no_response",
            "label": "ECU not responding",
            "detail": "The adapter is present, but the ECU is not replying on standard OBD.",
        }

    if quality["car_connected"]:
        return {
            "kind": "live",
            "label": "ECU connected",
            "detail": "Standard OBD live data is available.",
        }

    return {
        "kind": "searching",
        "label": "Searching for adapter",
        "detail": "Waiting for a USB OBD adapter or a live ECU response.",
    }


def list_serial_ports():
    if list_ports is None:
        return []

    ports = []
    try:
        for port in list_ports.comports():
            ports.append(
                {
                    "device": port.device,
                    "description": port.description or port.device,
                    "hwid": port.hwid or "",
                }
            )
    except Exception:
        return []

    ports.sort(key=lambda item: item["device"])
    return ports


def run_connection_test(obd_module, configured_port, timeout=1.0, attempts=2, retry_delay=0.5):
    detected_ports = list_serial_ports()
    selected_port = str(configured_port or "").strip().upper()
    selected_port_present = bool(
        selected_port
        and any(str(item.get("device") or "").strip().upper() == selected_port for item in detected_ports)
    )
    any_adapter_present = selected_port_present or bool(detected_ports)
    adapter_detail = (
        configured_port
        if selected_port_present
        else ", ".join(item.get("device", "") for item in detected_ports[:4]) or "No serial ports detected"
    )

    if obd_module is None:
        return {
            "success": False,
            "phase": "Library unavailable",
            "steps": [
                {"name": "Python OBD library", "ok": False, "detail": "python-obd is not available."},
            ],
        }

    test_connection = None
    last_exception = None
    try:
        for attempt in range(1, max(1, int(attempts or 1)) + 1):
            try:
                if configured_port:
                    test_connection = obd_module.OBD(
                        configured_port,
                        fast=False,
                        timeout=timeout,
                        check_voltage=False,
                    )
                else:
                    test_connection = obd_module.OBD(
                        fast=False,
                        timeout=timeout,
                        check_voltage=False,
                    )
                if test_connection and test_connection.is_connected():
                    break
                if attempt < attempts:
                    import time
                    time.sleep(retry_delay)
            except Exception as exc:
                last_exception = exc
                try:
                    if test_connection:
                        test_connection.close()
                except Exception:
                    pass
                test_connection = None
                if attempt < attempts:
                    import time
                    time.sleep(retry_delay)

        if test_connection is None and last_exception:
            raise last_exception

        phase = str(test_connection.status())
        protocol = test_connection.protocol_name() if test_connection.is_connected() else "Unknown"

        steps = [
            {"name": "USB adapter detected", "ok": phase in {"ELM Connected", "OBD Connected", "Car Connected"}, "detail": phase},
            {"name": "OBD protocol detected", "ok": phase in {"OBD Connected", "Car Connected"}, "detail": protocol},
            {"name": "ECU responding", "ok": bool(test_connection.is_connected()), "detail": protocol if test_connection.is_connected() else "No ECU response"},
        ]

        return {
            "success": bool(test_connection.is_connected()),
            "phase": phase,
            "protocol": protocol,
            "steps": steps,
        }
    except Exception as exc:
        return {
            "success": False,
            "phase": "Connection test failed",
            "steps": [
                {"name": "USB adapter detected", "ok": any_adapter_present, "detail": adapter_detail if any_adapter_present else str(exc)},
                {"name": "OBD protocol detected", "ok": False, "detail": "Not available"},
                {"name": "ECU responding", "ok": False, "detail": str(exc)},
            ],
        }
    finally:
        try:
            if test_connection:
                test_connection.close()
        except Exception:
            pass


def get_readiness_snapshot(connection, lock, get_command):
    status_command = get_command("STATUS")
    status_value = _safe_query(connection, lock, status_command)

    if status_value is None:
        return {
            "available": False,
            "mil": None,
            "dtc_count": None,
            "ignition_type": "",
            "monitors": [],
        }

    monitors = []
    for name in READINESS_ORDER:
        test = getattr(status_value, name, None)
        if test is None or getattr(test, "name", "") == "":
            continue
        monitors.append({
            "name": name.replace("_", " ").title(),
            "available": bool(getattr(test, "available", False)),
            "complete": bool(getattr(test, "complete", False)),
        })

    return {
        "available": True,
        "mil": bool(getattr(status_value, "MIL", False)),
        "dtc_count": int(getattr(status_value, "DTC_count", 0)),
        "ignition_type": str(getattr(status_value, "ignition_type", "")),
        "monitors": monitors,
    }


def get_freeze_frame_snapshot(connection, lock, get_command):
    if connection is None or not connection.is_connected():
        return {"available": False, "values": {}}

    values = {}
    found = False

    for key, command_name in FREEZE_FRAME_COMMANDS.items():
        command = get_command(command_name)
        value = _safe_query(connection, lock, command)
        if value is None:
            continue
        found = True
        values[key] = str(value)

    return {
        "available": found,
        "values": values,
    }
