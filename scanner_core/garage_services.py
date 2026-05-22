# Made by The Syndicate Development
import re
import time
from html import escape


VIN_PATTERN = re.compile(r"[A-HJ-NPR-Z0-9]{17}")


def normalize_garage_plate(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def normalize_garage_vin(value):
    compact = re.sub(r"[^A-Za-z0-9]", "", str(value or "").upper())
    match = VIN_PATTERN.search(compact)
    return match.group(0) if match else ""


def validate_garage_note_identity(raw_vin, raw_plate):
    vin_text = re.sub(r"[^A-Z0-9]", "", str(raw_vin or "").upper())
    plate_text = normalize_garage_plate(raw_plate)

    if not vin_text and not plate_text:
        return False, "Enter both VIN and license plate before saving a garage note."
    if not vin_text:
        return False, "Enter a VIN before saving this garage note."
    if len(vin_text) != 17:
        return False, f"VIN must be exactly 17 characters. You entered {len(vin_text)}."
    if any(char in vin_text for char in "IOQ"):
        return False, "VIN cannot contain I, O or Q. Check the VIN and try again."
    if not normalize_garage_vin(vin_text):
        return False, "VIN format is invalid. Use 17 letters and numbers."
    if not plate_text:
        return False, "Enter a license plate before saving this garage note."
    if len(plate_text) < 4:
        return False, "License plate looks too short. Check the plate and try again."

    return True, ""


def filter_garage_notes(notes, vin="", plate="", query=""):
    vin = normalize_garage_vin(vin)
    plate = normalize_garage_plate(plate)
    query_text = str(query or "").strip().upper()
    filtered = []

    for item in notes:
        item_vin = normalize_garage_vin(item.get("vin", ""))
        item_plate = normalize_garage_plate(item.get("plate", ""))
        if vin and vin != item_vin:
            continue
        if plate and plate != item_plate:
            continue
        if query_text:
            searchable = " ".join(
                str(part or "").upper()
                for part in (
                    item.get("vin"),
                    item.get("plate"),
                    item.get("title"),
                    item.get("mileage"),
                    item.get("note"),
                    item.get("created_at"),
                )
            )
            compact_searchable = re.sub(r"[^A-Z0-9]", "", searchable)
            compact_query = re.sub(r"[^A-Z0-9]", "", query_text)
            if query_text not in searchable and (not compact_query or compact_query not in compact_searchable):
                continue
        filtered.append(item)

    return filtered


def render_garage_notes_export_html(notes, app_version, vin="", plate="", query=""):
    vin = normalize_garage_vin(vin)
    plate = normalize_garage_plate(plate)
    query = str(query or "").strip()
    generated_at = time.strftime("%Y-%m-%d %H:%M:%S")

    def metric(label, value):
        return (
            '<div class="metric">'
            f"<span>{escape(str(label))}</span>"
            f"<strong>{escape(str(value or '--'))}</strong>"
            "</div>"
        )

    def field(label, value):
        value = str(value or "").strip() or "Not provided"
        return f"""
          <div class="detail-field">
            <span>{escape(label)}</span>
            <strong>{escape(value)}</strong>
          </div>
        """

    def note_card(item):
        note_text = str(item.get("note") or "").strip()
        return f"""
        <article class="note-card">
          <div class="note-header">
            <div>
              <span class="note-date">{escape(item.get('created_at') or 'No date recorded')}</span>
              <h2>{escape(item.get('title') or 'Garage note')}</h2>
            </div>
            <div class="mileage-pill">
              <span>Mileage</span>
              <strong>{escape(item.get('mileage') or 'Not provided')}</strong>
            </div>
          </div>
          <div class="detail-grid">
            {field('VIN', item.get('vin'))}
            {field('License plate', item.get('plate'))}
          </div>
          <div class="note-body">
            <span>Garage note</span>
            <p>{escape(note_text) if note_text else 'No note text saved.'}</p>
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
    .note-card {{ margin: 14px 0; padding: 22px; }}
    .note-header {{ align-items:start; border-bottom:1px solid var(--line); display:flex; gap:18px; justify-content:space-between; padding-bottom:16px; }}
    .note-date, .detail-field span, .note-body span, .mileage-pill span {{ color:var(--muted); display:block; font-size:11px; font-weight:900; letter-spacing:.12em; text-transform:uppercase; }}
    .note-header h2 {{ margin:6px 0 0; font-size:25px; line-height:1.2; }}
    .mileage-pill {{ background:#edf5ff; border:1px solid #cfe2ff; border-radius:16px; min-width:145px; padding:11px 13px; text-align:right; }}
    .mileage-pill strong {{ display:block; font-size:20px; margin-top:3px; }}
    .detail-grid {{ display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:12px; margin:16px 0; }}
    .detail-field {{ background:#f8fbff; border:1px solid var(--line); border-radius:16px; padding:13px 14px; }}
    .detail-field strong {{ display:block; font-size:17px; margin-top:5px; overflow-wrap:anywhere; }}
    .note-body {{ background:#fbfdff; border:1px solid var(--line); border-radius:16px; padding:15px 16px; }}
    .note-body p {{ color:var(--muted); line-height:1.6; margin:8px 0 0; white-space:pre-wrap; }}
    .empty {{ background:#fff; border:1px dashed var(--line); border-radius:18px; padding:20px; color:var(--muted); }}
    footer {{ color: var(--muted); margin: 24px 0; font-size: 13px; }}
    @media (max-width: 760px) {{ .summary, .detail-grid {{ grid-template-columns:1fr; }} .note-header {{ display:grid; }} .mileage-pill {{ text-align:left; }} .hero {{ padding:26px 22px; }} main {{ padding:18px; }} }}
  </style>
</head>
<body>
  <section class="hero">
    <span>Car-OBD-Diagnostics {escape(app_version)}</span>
    <h1>Garage Notes Export</h1>
    <p>Generated at {escape(generated_at)}</p>
  </section>
  <main>
    <section class="summary">
      {metric('Notes', len(notes))}
      {metric('Search', query or 'All')}
      {metric('VIN filter', vin or 'All')}
      {metric('Plate filter', plate or 'All')}
    </section>
    {cards}
    <footer>Use this software at your own risk. Licensed under GNU GPLv3.</footer>
  </main>
</body>
</html>"""
