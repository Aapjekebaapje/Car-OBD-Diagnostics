# Made by The Syndicate Development
def build_scanner_session_state(status, connection_quality=None, connection_hint=None):
    status = dict(status or {})
    quality = dict(connection_quality or {})
    hint = dict(connection_hint or {})

    demo_mode = bool(status.get("demo_mode"))
    connecting = bool(status.get("connecting"))
    connected = bool(status.get("connected"))
    port_label = status.get("current_port") or "No COM port selected"
    phase = str(quality.get("phase") or "").strip()
    phase_lower = phase.lower()
    adapter_connected = bool(quality.get("adapter_connected"))
    port_powered = bool(quality.get("port_powered"))
    ecu_connected = bool(quality.get("car_connected"))
    live_data_active = bool(quality.get("live_data_active"))
    selected_port_present = bool(quality.get("selected_port_present"))

    session = {
        "key": "offline",
        "title": "Scanner offline",
        "detail": "Waiting for a USB OBD adapter or a live ECU response.",
        "status_label": "Not connected",
        "adapter_label": "Offline",
        "system_label": "Offline",
        "scope_label": "Standard OBD Only",
        "port_label": port_label,
        "connected": connected,
        "connecting": connecting,
        "demo_mode": demo_mode,
        "adapter_connected": adapter_connected,
        "ecu_connected": ecu_connected,
        "live_data_active": live_data_active,
    }

    if demo_mode:
        session.update(
            {
                "key": "demo",
                "title": "Demo session active",
                "detail": "The diagnostic tablet is simulating a standard OBD-II session.",
                "status_label": "Demo connected",
                "adapter_label": "Demo",
                "system_label": "Demo",
                "connected": True,
                "adapter_connected": True,
                "ecu_connected": True,
                "live_data_active": True,
            }
        )
        return session

    hint_kind = str(hint.get("kind") or "").strip().lower()
    hint_label = hint.get("label") or session["title"]
    hint_detail = hint.get("detail") or session["detail"]

    if live_data_active or hint_kind == "live" or connected:
        session.update(
            {
                "key": "ecu_live",
                "title": "Live ECU data active",
                "detail": hint_detail,
                "status_label": "Connected",
                "adapter_label": "Online",
                "system_label": "Connected",
                "connected": True,
            }
        )
        return session

    if (adapter_connected or selected_port_present) and not ecu_connected:
        if port_powered or "obd connected" in phase_lower:
            session.update(
                {
                    "key": "obd_port_detected",
                    "title": "OBD port detected",
                    "detail": "The USB adapter sees the vehicle bus. Waiting for ECU response.",
                    "status_label": "OBD port detected",
                    "adapter_label": "USB connected",
                    "system_label": "Waiting for ECU",
                    "adapter_connected": True,
                    "ecu_connected": False,
                }
            )
            return session

        session.update(
            {
                "key": "usb_adapter_detected",
                "title": "USB adapter connected",
                "detail": "The USB adapter is connected. Waiting for the vehicle OBD port to wake up.",
                "status_label": "USB connected",
                "adapter_label": "USB connected",
                "system_label": "Waiting for OBD port",
                "adapter_connected": True,
                "ecu_connected": False,
            }
        )
        return session

    if connecting:
        session.update(
            {
                "key": "connecting",
                "title": "Connecting to scanner",
                "detail": "Trying to detect the adapter and negotiate a live ECU session.",
                "status_label": "Connecting...",
                "adapter_label": "Searching",
                "system_label": "Connecting",
            }
        )
        return session

    if hint_kind in {"ignition_likely_off", "ecu_no_response"}:
        session.update(
            {
                "key": hint_kind,
                "title": hint_label,
                "detail": hint_detail,
                "status_label": "Adapter found",
                "adapter_label": "Adapter found",
                "system_label": "Waiting for ECU" if hint_kind == "ignition_likely_off" else "No ECU response",
            }
        )
        return session

    if hint_kind == "adapter_missing":
        session.update(
            {
                "key": "adapter_missing",
                "title": hint_label,
                "detail": hint_detail,
                "status_label": "Not connected",
                "adapter_label": "Offline",
                "system_label": "Offline",
            }
        )
        return session

    if hint_kind == "searching":
        session.update(
            {
                "key": "searching",
                "title": hint_label,
                "detail": hint_detail,
                "status_label": "Not connected",
                "adapter_label": "Offline",
                "system_label": "Offline",
            }
        )

    return session
