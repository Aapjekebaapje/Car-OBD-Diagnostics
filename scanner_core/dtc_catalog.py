# Made by The Syndicate Development
try:
    from obd.codes import DTC as PYTHON_OBD_DTC
except Exception:
    PYTHON_OBD_DTC = {}


GENERIC_SYSTEMS = {
    "P00": "Fuel and air metering",
    "P01": "Fuel and air metering",
    "P02": "Fuel and injector circuit",
    "P03": "Ignition and misfire",
    "P04": "Emission control",
    "P05": "Vehicle speed, idle and auxiliary inputs",
    "P06": "Computer and output circuit",
    "P07": "Transmission",
    "B": "Body",
    "C": "Chassis",
    "U": "Network communication",
}


MISFIRE_CODES = {
    "P0300": "Random/multiple misfire",
    "P0301": "Cylinder 1 misfire",
    "P0302": "Cylinder 2 misfire",
    "P0303": "Cylinder 3 misfire",
    "P0304": "Cylinder 4 misfire",
    "P0305": "Cylinder 5 misfire",
    "P0306": "Cylinder 6 misfire",
    "P0307": "Cylinder 7 misfire",
    "P0308": "Cylinder 8 misfire",
    "P0309": "Cylinder 9 misfire",
    "P0310": "Cylinder 10 misfire",
    "P0311": "Cylinder 11 misfire",
    "P0312": "Cylinder 12 misfire",
    "P0313": "Misfire detected with low fuel",
    "P0314": "Single cylinder misfire not yet identified",
}


DTC_INFO = {
    "P0010": ("Camshaft actuator circuit bank 1", "Timing/VVT", "medium", ["VVT solenoid", "oil level or oil quality", "wiring", "ECU control"]),
    "P0011": ("Camshaft timing over-advanced bank 1", "Timing/VVT", "medium", ["dirty oil", "VVT solenoid", "mechanical timing", "oil pressure"]),
    "P0012": ("Camshaft timing over-retarded bank 1", "Timing/VVT", "medium", ["VVT solenoid", "oil problem", "mechanical timing"]),
    "P0016": ("Crankshaft/camshaft correlation fault", "Timing", "high", ["timing chain or belt alignment", "crankshaft sensor", "camshaft sensor", "mechanical timing"]),
    "P0030": ("O2 sensor heater circuit bank 1 sensor 1", "O2 sensor", "medium", ["oxygen sensor heater", "fuse", "wiring"]),
    "P0036": ("O2 sensor heater circuit bank 1 sensor 2", "O2 sensor", "medium", ["rear oxygen sensor heater", "wiring", "fuse"]),
    "P0100": ("MAF circuit fault", "Air metering", "medium", ["MAF sensor", "connector or wiring", "air leak after MAF"]),
    "P0101": ("MAF range/performance fault", "Air metering", "medium", ["dirty MAF", "air leak", "air filter", "intake leak"]),
    "P0102": ("MAF signal too low", "Air metering", "medium", ["MAF sensor", "wiring", "connector", "unmetered air leak"]),
    "P0103": ("MAF signal too high", "Air metering", "medium", ["MAF sensor", "wiring", "ECU reference voltage"]),
    "P0105": ("MAP/barometric pressure circuit fault", "Air pressure", "medium", ["MAP sensor", "vacuum hose", "wiring"]),
    "P0106": ("MAP range/performance fault", "Air pressure", "medium", ["MAP sensor", "vacuum leak", "intake pressure issue"]),
    "P0110": ("Intake air temperature sensor circuit", "Temperature", "low", ["IAT sensor", "wiring", "connector"]),
    "P0112": ("Intake air temperature signal too low", "Temperature", "low", ["IAT sensor", "short circuit", "wiring"]),
    "P0113": ("Intake air temperature signal too high", "Temperature", "low", ["IAT sensor", "open circuit", "disconnected plug"]),
    "P0115": ("Coolant temperature sensor circuit", "Cooling", "medium", ["ECT sensor", "wiring", "connector", "coolant level"]),
    "P0116": ("Coolant temperature range/performance fault", "Cooling", "medium", ["thermostat", "ECT sensor", "air in cooling system"]),
    "P0117": ("Coolant temperature signal too low", "Cooling", "medium", ["ECT sensor", "short circuit", "wiring"]),
    "P0118": ("Coolant temperature signal too high", "Cooling", "medium", ["ECT sensor", "open circuit", "disconnected plug"]),
    "P0120": ("Throttle position sensor circuit", "Throttle", "medium", ["TPS sensor", "throttle body", "wiring"]),
    "P0121": ("Throttle position sensor range/performance fault", "Throttle", "medium", ["dirty throttle body", "TPS sensor", "calibration"]),
    "P0122": ("Throttle position sensor signal too low", "Throttle", "medium", ["TPS sensor", "wiring", "connector"]),
    "P0123": ("Throttle position sensor signal too high", "Throttle", "medium", ["TPS sensor", "wiring", "reference voltage"]),
    "P0125": ("Insufficient coolant temperature for closed loop", "Cooling", "low", ["thermostat stuck open", "ECT sensor", "cooling system"]),
    "P0128": ("Coolant temperature below thermostat regulating temperature", "Cooling", "low", ["thermostat stuck open", "ECT sensor", "coolant level"]),
    "P0130": ("O2 sensor circuit bank 1 sensor 1", "O2 sensor", "medium", ["oxygen sensor", "exhaust leak", "wiring"]),
    "P0131": ("O2 sensor signal too low bank 1 sensor 1", "O2 sensor", "medium", ["lean condition", "oxygen sensor", "exhaust leak"]),
    "P0132": ("O2 sensor signal too high bank 1 sensor 1", "O2 sensor", "medium", ["rich condition", "oxygen sensor", "fuel pressure"]),
    "P0133": ("O2 sensor slow response bank 1 sensor 1", "O2 sensor", "medium", ["aged oxygen sensor", "exhaust leak", "fuel mixture issue"]),
    "P0134": ("No O2 sensor activity bank 1 sensor 1", "O2 sensor", "medium", ["oxygen sensor", "wiring", "fuse"]),
    "P0135": ("O2 sensor heater bank 1 sensor 1", "O2 sensor", "medium", ["sensor heater", "fuse", "wiring"]),
    "P0136": ("O2 sensor circuit bank 1 sensor 2", "O2 sensor", "medium", ["rear oxygen sensor", "exhaust leak", "wiring"]),
    "P0141": ("O2 sensor heater bank 1 sensor 2", "O2 sensor", "medium", ["sensor heater", "wiring", "fuse"]),
    "P0170": ("Fuel trim fault bank 1", "Fuel mixture", "medium", ["vacuum leak", "MAF/MAP", "fuel pressure", "O2 sensor"]),
    "P0171": ("System too lean bank 1", "Fuel mixture", "medium", ["vacuum leak", "dirty MAF", "low fuel pressure", "intake leak", "exhaust leak before O2 sensor"]),
    "P0172": ("System too rich bank 1", "Fuel mixture", "medium", ["leaking injector", "high fuel pressure", "MAF/MAP fault", "O2 sensor"]),
    "P0174": ("System too lean bank 2", "Fuel mixture", "medium", ["vacuum leak", "dirty MAF", "low fuel pressure"]),
    "P0175": ("System too rich bank 2", "Fuel mixture", "medium", ["injector", "fuel pressure", "sensor bias"]),
    "P0180": ("Fuel temperature sensor circuit", "Fuel", "low", ["sensor", "wiring", "connector"]),
    "P0190": ("Fuel rail pressure sensor circuit", "Fuel pressure", "high", ["fuel pressure sensor", "fuel pump", "pressure regulator", "wiring"]),
    "P0191": ("Fuel rail pressure range/performance fault", "Fuel pressure", "high", ["low fuel pressure", "sensor", "filter", "pump"]),
    "P0192": ("Fuel rail pressure signal too low", "Fuel pressure", "high", ["sensor", "wiring", "low fuel pressure"]),
    "P0193": ("Fuel rail pressure signal too high", "Fuel pressure", "high", ["sensor", "regulator", "wiring"]),
    "P0200": ("Injector circuit fault", "Injection", "high", ["injector wiring", "injector", "ECU driver"]),
    "P0201": ("Injector circuit cylinder 1", "Injection", "high", ["cylinder 1 injector", "wiring", "ECU driver"]),
    "P0202": ("Injector circuit cylinder 2", "Injection", "high", ["cylinder 2 injector", "wiring", "ECU driver"]),
    "P0203": ("Injector circuit cylinder 3", "Injection", "high", ["cylinder 3 injector", "wiring", "ECU driver"]),
    "P0204": ("Injector circuit cylinder 4", "Injection", "high", ["cylinder 4 injector", "wiring", "ECU driver"]),
    "P0217": ("Engine over-temperature condition", "Cooling", "high", ["low coolant", "thermostat", "water pump", "radiator", "cooling fan", "possible head gasket if overheating repeats"]),
    "P0300": ("Random/multiple cylinder misfire", "Misfire", "high", ["spark plugs", "ignition coils", "injectors", "vacuum leak", "compression issue", "fuel pressure", "possible head gasket with coolant loss or white smoke"]),
    "P0301": ("Cylinder 1 misfire", "Misfire", "high", ["cylinder 1 spark plug", "ignition coil", "injector", "compression", "valves", "possible head gasket"]),
    "P0302": ("Cylinder 2 misfire", "Misfire", "high", ["cylinder 2 spark plug", "ignition coil", "injector", "compression", "valves", "possible head gasket"]),
    "P0303": ("Cylinder 3 misfire", "Misfire", "high", ["cylinder 3 spark plug", "ignition coil", "injector", "compression", "valves", "possible head gasket"]),
    "P0304": ("Cylinder 4 misfire", "Misfire", "high", ["cylinder 4 spark plug", "ignition coil", "injector", "compression", "valves", "possible head gasket"]),
    "P0305": ("Cylinder 5 misfire", "Misfire", "high", ["cylinder 5 spark plug", "ignition coil", "injector", "compression"]),
    "P0306": ("Cylinder 6 misfire", "Misfire", "high", ["cylinder 6 spark plug", "ignition coil", "injector", "compression"]),
    "P0307": ("Cylinder 7 misfire", "Misfire", "high", ["cylinder 7 spark plug", "ignition coil", "injector", "compression"]),
    "P0308": ("Cylinder 8 misfire", "Misfire", "high", ["cylinder 8 spark plug", "ignition coil", "injector", "compression"]),
    "P0309": ("Cylinder 9 misfire", "Misfire", "high", ["cylinder 9 spark plug", "ignition coil", "injector", "compression"]),
    "P0310": ("Cylinder 10 misfire", "Misfire", "high", ["cylinder 10 spark plug", "ignition coil", "injector", "compression"]),
    "P0311": ("Cylinder 11 misfire", "Misfire", "high", ["cylinder 11 spark plug", "ignition coil", "injector", "compression"]),
    "P0312": ("Cylinder 12 misfire", "Misfire", "high", ["cylinder 12 spark plug", "ignition coil", "injector", "compression"]),
    "P0313": ("Misfire detected with low fuel", "Misfire", "medium", ["low fuel level", "fuel delivery", "air in fuel system"]),
    "P0314": ("Single cylinder misfire not yet identified", "Misfire", "high", ["ignition", "fuel", "compression", "sensor issue"]),
    "P0325": ("Knock sensor circuit bank 1", "Ignition", "medium", ["knock sensor", "wiring", "engine knock", "fuel quality"]),
    "P0335": ("Crankshaft position sensor circuit", "Ignition", "high", ["crankshaft sensor", "wiring", "reluctor wheel", "possible no-start"]),
    "P0340": ("Camshaft position sensor circuit", "Timing", "high", ["camshaft sensor", "wiring", "timing issue"]),
    "P0350": ("Ignition coil primary/secondary circuit", "Ignition", "high", ["ignition coil", "wiring", "ECU driver"]),
    "P0351": ("Ignition coil A circuit", "Ignition", "high", ["coil A", "wiring", "spark plug"]),
    "P0352": ("Ignition coil B circuit", "Ignition", "high", ["coil B", "wiring", "spark plug"]),
    "P0353": ("Ignition coil C circuit", "Ignition", "high", ["coil C", "wiring", "spark plug"]),
    "P0354": ("Ignition coil D circuit", "Ignition", "high", ["coil D", "wiring", "spark plug"]),
    "P0400": ("EGR flow fault", "Emission/EGR", "medium", ["EGR valve", "carbon buildup", "vacuum/control issue"]),
    "P0401": ("EGR flow insufficient", "Emission/EGR", "medium", ["blocked EGR", "EGR valve", "carbon-clogged passages"]),
    "P0402": ("EGR flow excessive", "Emission/EGR", "medium", ["EGR stuck open", "control issue", "sensor"]),
    "P0403": ("EGR circuit fault", "Emission/EGR", "medium", ["EGR solenoid", "wiring", "fuse"]),
    "P0410": ("Secondary air injection fault", "Emission", "low", ["air pump", "relay", "valve", "hoses"]),
    "P0420": ("Catalyst efficiency below threshold bank 1", "Catalyst", "medium", ["worn catalytic converter", "exhaust leak", "oxygen sensor", "misfires or rich mixture"]),
    "P0430": ("Catalyst efficiency below threshold bank 2", "Catalyst", "medium", ["catalytic converter", "exhaust leak", "oxygen sensor"]),
    "P0440": ("EVAP system fault", "EVAP", "low", ["fuel cap", "EVAP hose", "purge valve", "leak"]),
    "P0441": ("Incorrect EVAP purge flow", "EVAP", "low", ["purge valve", "hoses", "fuel cap"]),
    "P0442": ("Small EVAP leak", "EVAP", "low", ["fuel cap", "small hose leak", "EVAP lines"]),
    "P0443": ("EVAP purge valve circuit", "EVAP", "low", ["purge valve", "wiring", "fuse"]),
    "P0455": ("Large EVAP leak", "EVAP", "low", ["loose fuel cap", "large hose leak", "EVAP canister"]),
    "P0456": ("Very small EVAP leak", "EVAP", "low", ["fuel cap", "small leak", "EVAP line"]),
    "P0457": ("EVAP leak/fuel cap", "EVAP", "low", ["loose fuel cap", "fuel cap seal", "EVAP leak"]),
    "P0500": ("Vehicle speed sensor fault", "Speed", "medium", ["ABS/speed sensor", "wiring", "cluster signal"]),
    "P0505": ("Idle control system fault", "Idle", "medium", ["dirty throttle body", "IAC valve", "vacuum leak"]),
    "P0506": ("Idle speed too low", "Idle", "medium", ["throttle body", "vacuum leak", "IAC", "engine load"]),
    "P0507": ("Idle speed too high", "Idle", "medium", ["vacuum leak", "throttle body", "IAC"]),
    "P0560": ("System voltage fault", "Electrical", "medium", ["battery", "alternator", "ground", "wiring"]),
    "P0562": ("System voltage too low", "Electrical", "medium", ["weak battery", "alternator", "ground/cables"]),
    "P0563": ("System voltage too high", "Electrical", "medium", ["alternator regulator", "battery", "wiring"]),
    "P0600": ("Serial communication link fault", "ECU/Communication", "high", ["ECU communication", "CAN wiring", "power/ground"]),
    "P0601": ("ECU memory checksum fault", "ECU", "high", ["internal ECU fault", "software", "power supply"]),
    "P0606": ("ECU processor fault", "ECU", "high", ["internal ECU fault", "power/ground", "software"]),
    "P0700": ("Transmission control system fault", "Transmission", "medium", ["TCM has stored codes", "scan transmission module with enhanced scanner"]),
}


def severity_action(severity):
    if severity == "high":
        return "Possible serious issue. Inspect before buying."
    if severity == "medium":
        return "Needs follow-up. Use with caution."
    if severity == "low":
        return "Usually not urgent, but still worth checking."
    return "Review this code with live data and a manual inspection."


def explain_dtc(code, original_description=""):
    normalized = (code or "").upper().strip()
    info = DTC_INFO.get(normalized)

    if info:
        description, system, severity, causes = info
    else:
        description = _best_description(normalized, original_description)
        system = _guess_system(normalized)
        severity = _guess_severity(normalized)
        causes = _guess_causes(normalized)

    return {
        "description_en": description,
        "system": system,
        "severity": severity,
        "possible_causes": causes,
    }


def enrich_dtc(code, original_description=""):
    explanation = explain_dtc(code, original_description)
    normalized = (code or "").upper().strip()

    return {
        "code": normalized,
        "code_type": _classify_code_type(normalized),
        "description": original_description,
        "description_en": explanation["description_en"],
        "system": explanation["system"],
        "severity": explanation["severity"],
        "action_hint": severity_action(explanation["severity"]),
        "possible_causes": explanation["possible_causes"],
        "misfire": MISFIRE_CODES.get(normalized),
    }


def _best_description(code, original_description):
    if original_description:
        return original_description
    if code in PYTHON_OBD_DTC:
        return PYTHON_OBD_DTC[code]
    return "No specific description available"


def _guess_system(code):
    if not code:
        return "Unknown"

    if code[0] in GENERIC_SYSTEMS:
        return GENERIC_SYSTEMS[code[0]]

    return GENERIC_SYSTEMS.get(code[:3], "Manufacturer-specific or unknown system")


def _guess_severity(code):
    if code.startswith(("P02", "P03", "P06", "P1")):
        return "high"
    if code.startswith(("P00", "P01", "P04", "P05", "P07", "B", "C", "U")):
        return "medium"
    return "unknown"


def _guess_causes(code):
    if not code:
        return ["Code could not be recognized"]

    if code.startswith("P1"):
        return ["manufacturer-specific code", "check manufacturer-specific documentation", "check freeze-frame data"]
    if code.startswith("P03"):
        return ["ignition", "fuel", "compression", "sensors", "mechanical engine condition"]
    if code.startswith("P04"):
        return ["emission system", "EGR/EVAP/catalyst", "sensors", "hoses/leaks"]
    if code.startswith("U"):
        return ["CAN bus communication", "module power/ground", "wiring", "module offline"]
    if code.startswith("C"):
        return ["chassis/ABS/steering angle sensor", "wheel sensor", "wiring", "module-specific scanner needed"]
    if code.startswith("B"):
        return ["body module", "sensor/switch", "wiring", "module-specific scanner needed"]

    return ["check wiring/connectors", "check live data", "consult manufacturer-specific information"]


def _classify_code_type(code):
    if not code or len(code) < 2:
        return "Unknown"

    family_digit = code[1]
    if family_digit == "0":
        return "Generic"
    if family_digit == "1":
        return "Manufacturer-specific"
    return "Enhanced/Extended"
