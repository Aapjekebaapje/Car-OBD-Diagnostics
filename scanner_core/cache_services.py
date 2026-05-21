import json


def vin_cache_key(vin):
    return f"vin_cache::{(vin or '').upper().strip()}"


def load_vin_cache(get_setting, vin):
    raw = get_setting(vin_cache_key(vin), "")
    if not raw:
        return None

    try:
        return json.loads(raw)
    except Exception:
        return None


def save_vin_cache(set_setting, vin, decoded):
    try:
        return set_setting(vin_cache_key(vin), json.dumps(decoded))
    except Exception:
        return False
