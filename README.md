# Car-OBD-Diagnostics

A Python and Flask based OBD-II diagnostic dashboard for reading live ECU data, fault codes, readiness information, freeze-frame data and vehicle details through a USB OBD adapter.

The project includes a tablet-style web interface, English and Dutch language support, local scan history, VIN/license plate workflows and a built-in demo mode for testing without a car connected.

Current version: `v0.2.2`

## Features

- Live OBD-II dashboard with smooth RPM and speed gauges
- Fast lightweight gauge updates through `/api/gauges`
- Separate RPM/speed polling for a more real-time gauge feel
- Prioritized OBD polling to reduce ECU and adapter load
- Coolant temperature, ECU voltage, engine load, fuel trims and other live sensor values
- Stored, pending and permanent diagnostic trouble code views
- Fault code clearing with SAFE mode protection
- Readiness monitor overview
- Freeze-frame snapshot support where available
- VIN reading and manual VIN lookup
- Dutch RDW license plate lookup
- Local VIN/license plate lookup history
- Local scan history stored in SQLite
- USB / COM port selection
- Connection test and adapter status view
- Demo mode with multiple simulated drive presets
- Styled HTML scan report export
- Export from live data or from a paused/frozen dashboard snapshot
- Multi-language report export in English or Dutch
- Battery and charging voltage check
- Optional simple summary mode
- Supported PID overview
- English and Dutch interface support

## Important OBD-II Note

This app uses standard OBD-II data through `python-obd`. Standard OBD-II mainly covers engine and emissions related ECU data.

ABS, airbag, BCM, window, mirror, odometer, ADAS and other manufacturer-specific module access usually requires brand-specific diagnostics, UDS/CAN tooling, security access and vehicle-specific CAN IDs. Those features are not guaranteed through this project or the `python-obd` library.

Features such as Driver Alert, speed warning, lane assist or other assistance settings are usually not available through standard OBD-II. Some cars expose them through manufacturer-specific coding tools, but this project does not write coding changes to safety or assistance modules.

## Requirements

- Python 3.10 or newer recommended
- USB OBD-II adapter, for example an ELM327-compatible adapter
- A vehicle with an OBD-II port
- Windows, macOS or Linux

Python packages used by the project:

```txt
flask
obd
pyserial
cryptography
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

## HTML Report Export

The dashboard can export a styled HTML scan report with vehicle details, live data, diagnostic trouble codes, readiness information and freeze-frame data where available.

Reports follow the selected interface language:

- Dutch UI exports Dutch report labels
- English UI exports English report labels

The export button works in two modes:

- Live stream: exports the latest available live dashboard data
- Paused stream: exports the frozen dashboard snapshot

OBD units are cleaned up in the report. For example, RPM values are shown as `RPM` instead of raw library text such as `revolutions_per_minute`.

## Configuration

Refresh timings and history limits can be adjusted in `config.py`.

```python
POLL_INTERVAL = 0.1
RPM_POLL_INTERVAL = 0.05
OBD_CONNECT_TIMEOUT = 1.0
OBD_CONNECT_ATTEMPTS = 3
OBD_CONNECT_RETRY_DELAY = 1.0
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

This file is created and updated locally when you use the app. Browser-side VIN/license plate lookup history is stored in `localStorage`.

## Troubleshooting

If no adapter is detected:

- Check the USB cable
- Check Device Manager for the COM port on Windows
- Try another USB port
- Confirm the ignition is on
- Select the correct COM port in `Service`
- Try disabling other software that may be using the adapter

If Windows shows `PermissionError(13)` or `Access denied` for a COM port:

- Another app or Python process is already using the adapter
- Close other OBD/serial tools
- Stop duplicate `python app.py` processes
- Unplug and reconnect the USB adapter
- Try a different COM port if Windows assigned a new one

If live data is empty or unstable:

- Confirm the vehicle supports standard OBD-II
- Try reconnecting
- Try Limited Mode
- Check whether the adapter is a reliable ELM327-compatible device
- Increase refresh intervals in `config.py` if the adapter returns noisy values

If the dashboard says live data could not be read while the connection still shows connected:

- Some individual PIDs may be unsupported by the car
- The app may still have valid RPM, speed or other cached live values
- Try reconnecting or enabling Limited Mode
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
