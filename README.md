# Car-OBD-Diagnostics

A Python and Flask based OBD-II diagnostic dashboard for reading live ECU data, fault codes, readiness information, freeze-frame data and vehicle details through a USB OBD adapter.

The project includes a tablet-style web interface, English and Dutch language support, local scan history, VIN/license plate workflows and a built-in demo mode for testing without a car connected.

Current version: `v0.4.3`

## Features

- Live OBD-II dashboard with smooth RPM and speed gauges
- Fast lightweight gauge updates through `/api/gauges`
- Separate RPM/speed polling for a more real-time gauge feel
- Prioritized OBD polling to reduce ECU and adapter load
- Selectable polling profiles: Performance, Balanced and Safe
- Coolant temperature, ECU voltage, engine load, fuel trims and other live sensor values
- Live mini charts for coolant temperature, ECU voltage, engine load and throttle position
- Stored, pending and permanent diagnostic trouble code views
- Fault code clearing with SAFE mode protection
- Readiness monitor overview
- Freeze-frame snapshot support where available
- Experimental VIN reading and manual VIN lookup
- Dutch RDW license plate lookup
- Local VIN/license plate lookup history
- Local scan history stored in SQLite
- Garage notes saved per VIN and license plate
- Garage note live search across VIN, license plate, title, mileage, note text and date
- Cleaner garage note cards with VIN, license plate, mileage and note metadata
- Garage note validation with clear feedback for invalid VINs, missing plates and empty notes
- Cleaner garage note styled HTML export
- Garage note edit action for updating saved notes
- Garage note delete action with confirmation popup
- Split garage note validation, filtering and HTML export logic into `scanner_core/garage_services.py`
- Extra UI animations for page changes, popups, actions, form feedback and status text
- Reworked page layouts for Live Data, Fault Codes, Reports, Service, Garage, History, Sensors, System, Vehicle and Purchase Checklist views
- Smooth motion layer for dropdowns, details panels, list rows, graph cards, gauges, buttons, inputs and confirmation dialogs
- USB / COM port selection
- Connection test and adapter status view
- Connection quality view for USB adapter, OBD port, ECU and live data state
- Demo mode with multiple simulated drive presets
- Styled HTML scan report export
- Export from live data or from a paused/frozen dashboard snapshot
- Report export presets for full report, fault codes, live data or vehicle info
- Multi-language report export in English or Dutch
- Battery and charging voltage check
- Optional simple summary mode
- Reset UI cache action for clearing local browser dashboard state
- Supported PID overview
- English and Dutch interface support

## Important OBD-II Note

This app uses standard OBD-II data through `python-obd`. Standard OBD-II mainly covers engine and emissions related ECU data.

ABS, airbag, BCM, window, mirror, odometer, ADAS and other manufacturer-specific module access usually requires brand-specific diagnostics, UDS/CAN tooling, security access and vehicle-specific CAN IDs. Those features are not guaranteed through this project or the `python-obd` library.

Features such as Driver Alert, speed warning, lane assist or other assistance settings are usually not available through standard OBD-II. Some cars expose them through manufacturer-specific coding tools, but this project does not write coding changes to safety or assistance modules.

## Vehicle Lookup Limitations

VIN reading and VIN based vehicle information are experimental. The VIN feature can still contain bugs and may not work correctly on every vehicle, adapter or ECU response format. It is not guaranteed to be 100% accurate. This may be improved in future updates, but it is also possible that this feature changes heavily or gets removed if it cannot be made reliable enough.

License plate lookup currently only supports Dutch license plates through RDW data. International license plate lookup may be added in a future update, but this is not guaranteed. This feature may also change or be removed later if it becomes unreliable or too limited.

## Fault Codes Testing Note

Fault code reading, pending codes, permanent codes and fault-code clearing have not been fully tested on many real vehicles yet. If you test this project with a real car and notice missing codes, wrong descriptions, unstable behavior or anything else related to error codes, feedback is very welcome.

You can share feedback here: https://discord.gg/avZDNA6wZn?


## Requirements

- Python 3.10 or newer recommended
- USB OBD-II adapter, for example an ELM327-compatible adapter
- A vehicle with an OBD-II port
- Windows, macOS or Linux

## Tested Adapter

This project is used and tested with this USB OBD-II adapter:

- [OBD-II USB adapter on Amazon.nl](https://www.amazon.nl/dp/B07MQ8GHG3)

In testing, this adapter works well with the dashboard for standard OBD-II live data, fault codes and connection detection. Results can still depend on the vehicle, ECU support, Windows COM port assignment and adapter quality, so other cars may behave differently.

Python packages used by the project:

```txt
flask
obd
pyserial
```

## Installation

Clone the repository:

```bash
git clone https://github.com/Aapjekebaapje/Car-OBD-Diagnostics.git
cd Car-OBD-Diagnostics
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

If PowerShell blocks the virtual environment activation script with an execution policy error, run this command in the same PowerShell window and then try activating again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

This only changes the policy for the current PowerShell session.

Activate it on macOS or Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Running The App

Start the Flask app:

```bash
python app.py
```

Open the dashboard:

```txt
http://127.0.0.1:5000/
```

The app runs on port `5000` by default.

## Download / Source
1. GitHub Repository: https://github.com/Aapjekebaapje/Car-OBD-Diagnostics
2. Official Website: https://thesyndicatedevelopment.nl

## Using A Real OBD Adapter

1. Plug the USB OBD-II adapter into your computer.
2. Plug the adapter into the vehicle OBD-II port.
3. Turn the ignition on.
4. Open the dashboard.
5. Go to `Service`.
6. Select the detected COM port, or leave it on auto-detect.
7. Use `Test Connection` or `Retry Connection`.

On Windows, the adapter usually appears as something like `COM3`, `COM4` or `COM5`.

## Demo Mode

Demo mode lets you test the UI without a USB adapter or vehicle.

Go to `Service` and enable `Demo Mode`. You can choose presets such as:

- Idle
- Cruise
- Heavy Load
- Fault Present

Demo mode generates simulated live data, fault code states, readiness values and vehicle information.

## Polling Profiles

The Service page includes three polling profiles:

- Performance: faster updates for a more responsive dashboard
- Balanced: recommended default for normal use
- Safe: slower polling to reduce adapter and ECU load

The selected profile is shown in the top bar and can be changed even when no USB adapter or ECU is connected. The app saves the selected profile locally and syncs it with the backend when available.

## HTML Report Export

The dashboard can export a styled HTML scan report with vehicle details, live data, diagnostic trouble codes, readiness information and freeze-frame data where available.

Reports follow the selected interface language:

- Dutch UI exports Dutch report labels
- English UI exports English report labels

The export button works in two modes:

- Live stream: exports the latest available live dashboard data
- Paused stream: exports the frozen dashboard snapshot

Report exports can be created as a full report, fault-code-only report, live-data-only report or vehicle-info-only report.

OBD units are cleaned up in the report. For example, RPM values are shown as `RPM` instead of raw library text such as `revolutions_per_minute`.

## Garage Notes

Garage notes are stored locally in SQLite and are linked to a vehicle identity. A note requires both:

- VIN
- License plate

The app can auto-fill these fields when vehicle data is detected, but they can also be entered manually.

Saved garage notes use a clean card layout with compact metadata chips for date/time, VIN, license plate and mileage. The garage database has one live search bar that filters while typing across VIN, license plate, title, mileage, note text and date/time.

The form gives clear feedback before saving. It checks for missing VIN, short VIN, invalid VIN characters, missing license plate, short license plate and empty note text. Invalid fields are highlighted so the problem is easier to see.

Filtered garage notes can be exported as a styled HTML report. The garage export focuses on the saved note details and removes unrelated live-data blocks such as health score, protocol, RPM and speed from each note card. Notes can also be deleted from the local database with a trash button and confirmation popup.

Saved garage notes can be edited later. Editing fills the note form with the existing VIN, license plate, title, mileage and note text, then updates the local SQLite record when saved.

## Configuration

Refresh timings and history limits can be adjusted in `config.py`.

```python
APP_VERSION = "v0.4.3"
POLL_INTERVAL = 0.1
RPM_POLL_INTERVAL = 0.05
OBD_CONNECT_TIMEOUT = 1.0
OBD_CONNECT_ATTEMPTS = 3
OBD_CONNECT_RETRY_DELAY = 1.0
MAX_POLL_INTERVAL = 0.8
FAST_SENSOR_INTERVAL = 0.5
MEDIUM_SENSOR_INTERVAL = 2.0
SLOW_SENSOR_INTERVAL = 10.0
STALE_AFTER_SECONDS = 0.9
SCAN_HISTORY_LIMIT = 20
```

Lower values feel more live, but they also query the ECU more often. Keep non-critical values slower to avoid noisy adapters and unnecessary ECU load.

RPM and speed are refreshed separately from slower dashboard values. This makes the gauges feel more responsive, but true millisecond-perfect sync is still limited by the vehicle ECU, OBD adapter, serial connection, Python polling and browser rendering.

## Language Support

The interface supports:

- English
- Dutch

The app loads a language-specific JavaScript file:

- `static/en_app.js`
- `static/nl_app.js`

The selected language is stored in the `obd_lang` browser cookie.

## Project Structure

```txt
.
|-- app.py
|-- config.py
|-- requirements.txt
|-- scanner_core/
|   |-- cache_services.py
|   |-- demo_services.py
|   |-- dtc_catalog.py
|   |-- garage_services.py
|   |-- obd_services.py
|   |-- report_services.py
|   |-- session_services.py
|   |-- storage_services.py
|   `-- translation.py
|-- static/
|   |-- en_app.js
|   |-- nl_app.js
|   `-- style.css
`-- templates/
    |-- dashboard.html
    |-- pages/
    `-- partials/
```

## Local Data

The app stores local configuration and scan history in:

```txt
scanner_config.db
```

This file is created and updated locally when you use the app. It stores settings, scan history and garage notes. Deleted garage notes are removed from this local database. Browser-side UI state and VIN/license plate lookup history are stored in `localStorage`.

Use the Reset UI Cache button on the System page if the browser keeps old dashboard state after an update. This only clears browser-side UI state such as selected polling profile, language cookie and local lookup history. It does not delete saved scans or garage notes from `scanner_config.db`.

## Known Bugs And Limitations

- VIN detection and VIN based vehicle details can still be unreliable on some cars or adapter response formats.
- Fault code reading and clearing have not been fully tested on many real vehicles yet.
- Standard OBD-II does not guarantee access to ABS, airbag, BCM, ADAS, odometer or manufacturer-specific modules.
- Live RPM and speed responsiveness depends on the ECU, adapter, serial connection, Python polling and browser rendering.
- Dutch RDW license plate lookup only supports Dutch plates for now.

## Troubleshooting

If no adapter is detected:

- Check the USB cable
- Check Device Manager for the COM port on Windows
- Try another USB port
- Confirm the ignition is on
- Select the correct COM port in `Service`
- Try disabling other software that may be using the adapter

If PowerShell blocks `.venv\Scripts\activate`:

- Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`
- Activate the virtual environment again
- This setting only applies to the current PowerShell window

If Windows shows `PermissionError(13)` or `Access denied` for a COM port:

- Another app or Python process is already using the adapter
- Close other OBD/serial tools
- Stop duplicate `python app.py` processes
- Unplug and reconnect the USB adapter
- Try a different COM port if Windows assigned a new one

If live data is empty or unstable:

- Confirm the vehicle supports standard OBD-II
- Try reconnecting
- Try the Safe polling profile
- Check whether the adapter is a reliable ELM327-compatible device
- Increase refresh intervals in `config.py` if the adapter returns noisy values

If the dashboard says live data could not be read while the connection still shows connected:

- Some individual PIDs may be unsupported by the car
- The app may still have valid RPM, speed or other cached live values
- Try reconnecting or switching to the Safe polling profile
- Increase polling intervals if the adapter is unstable

If fuel level jumps around:

- Some vehicles report fuel level from a tank float sensor, which can move while driving
- Fuel level is refreshed slower because it is not critical live diagnostic data
- Large jumps can also point to adapter noise, wiring issues or a worn fuel level sender

## Safety And Disclaimer

Be careful when clearing fault codes. Clearing DTCs can remove diagnostic evidence that may be useful for repair work. The app includes SAFE mode protection to prevent accidental clearing.

Do not use the dashboard while driving. Have another person operate the software or use it only while parked.

This project is provided for educational and personal diagnostic use. Use it at your own risk. The author is not responsible for any damage, data loss, broken adapters, vehicle issues, incorrect diagnostics, cleared fault codes, repair costs or any other problems caused directly or indirectly by using this software.

## License

This project is licensed under the GNU General Public License v3.0.

You are allowed to use, modify, share and distribute this project under the terms of the GPLv3. If you distribute modified versions, you must also provide the source code under the same license.
