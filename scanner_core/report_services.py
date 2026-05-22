# Made by The Syndicate Development
def build_purchase_report(payload):
    status = payload.get("status", {})
    vehicle = payload.get("vehicle", {})
    dtc = payload.get("dtc", {})
    vehicle_profile = payload.get("vehicle_profile", {})
    health = payload.get("health", {})
    readiness = payload.get("readiness", {})
    freeze_frame = payload.get("freeze_frame", {})

    summary_items = []
    if status.get("connected"):
        summary_items.append("ECU connection active")
    else:
        summary_items.append("No ECU connection")

    if vehicle_profile.get("vin"):
        summary_items.append(f"VIN: {vehicle_profile['vin']}")

    if readiness.get("available"):
        incomplete = [item["name"] for item in readiness.get("monitors", []) if item.get("available") and not item.get("complete")]
        if incomplete:
            summary_items.append(f"Readiness incomplete: {', '.join(incomplete[:4])}")
        else:
            summary_items.append("Readiness monitors complete")

    stored = dtc.get("stored", [])
    pending = dtc.get("pending", [])
    permanent = dtc.get("permanent", [])

    verdict = "Healthy so far"
    if health.get("status") == "danger":
        verdict = "Potential buying risk"
    elif health.get("status") == "warning":
        verdict = "Needs attention"

    sections = [
        {
            "title": "Health",
            "items": [
                f"Score: {health.get('score', '--')}",
                f"Verdict: {verdict}",
                f"Stored codes: {len(stored)}",
                f"Pending codes: {len(pending)}",
                f"Permanent codes: {len(permanent)}",
            ],
        },
        {
            "title": "Live Highlights",
            "items": [
                f"RPM: {vehicle.get('rpm', {}).get('value', '--')}",
                f"Speed: {vehicle.get('speed', {}).get('value', '--')}",
                f"Coolant temp: {vehicle.get('coolant_temp', {}).get('value', '--')}",
                f"ECU voltage: {vehicle.get('control_voltage', {}).get('value', '--')}",
                f"Fuel trim bank 1: {vehicle.get('long_fuel_trim_1', {}).get('value', '--')}",
            ],
        },
        {
            "title": "Freeze Frame",
            "items": (
                [f"{key.replace('_', ' ').title()}: {value}" for key, value in freeze_frame.get("values", {}).items()]
                if freeze_frame.get("available")
                else ["No freeze-frame data available."]
            ),
        },
    ]

    return {
        "headline": verdict,
        "summary": summary_items,
        "sections": sections,
    }
