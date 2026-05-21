# OBD-scanner-Python

A Python and Flask based OBD-II diagnostic dashboard for reading live ECU data, fault codes, readiness information, freeze-frame data and vehicle details through a USB OBD adapter. The project includes a tablet-style web interface, EN/NL language support and a built-in demo mode for testing the UI without a car connected.

## Features

- Live OBD-II sensor dashboard
- RPM and speed gauges
- Coolant temperature, ECU voltage, engine load and fuel trim display
- Stored, pending and permanent diagnostic trouble code views
- Fault code clearing with SAFE mode protection
- Readiness monitor overview
- Freeze-frame snapshot support where available
- VIN and manual vehicle lookup workflow
- Scan history stored locally
- USB / COM port selection
- Connection test and adapter status view
- Demo mode with multiple simulated drive presets
- English and Dutch interface support

## Important Note

This app uses standard OBD-II data through `python-obd`. Standard OBD-II mainly covers engine and emissions related ECU data.

ABS, airbag, BCM, window, mirror and brand-specific module access usually requires manufacturer-specific diagnostics, UDS/CAN tooling, security access and vehicle-specific CAN IDs. Those features are not guaranteed through this project or the `python-obd` library.

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
git clone https://github.com/Aapjekebaapje/OBD-scanner-Python.git
cd OBD-scanner-Python
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

## Running the App

Start the Flask app:

```bash
python app.py
```

Open the dashboard:

```txt
http://127.0.0.1:5000/
```

The app runs on port `5000` by default.

## Using a Real OBD Adapter

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

Demo mode generates simulated live data, fault code states and readiness values.

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
├── app.py
├── requirements.txt
├── scanner_core/
│   ├── cache_services.py
│   ├── demo_services.py
│   ├── dtc_catalog.py
│   ├── obd_services.py
│   ├── report_services.py
│   ├── session_services.py
│   ├── storage_services.py
│   └── translation.py
├── static/
│   ├── en_app.js
│   ├── nl_app.js
│   └── style.css
└── templates/
    ├── dashboard.html
    ├── pages/
    └── partials/
```

## Local Data

The app stores local configuration and scan history in:

```txt
scanner_config.db
```

This file is created and updated locally when you use the app.

## Safety and Disclaimer

Be careful when clearing fault codes. Clearing DTCs can remove diagnostic evidence that may be useful for repair work. The app includes SAFE mode protection to prevent accidental clearing.

Do not use the dashboard while driving. Have another person operate the software or use it only while parked.

This project is provided for educational and personal diagnostic use. Use it at your own risk. The author is not responsible for any damage, data loss, broken adapters, vehicle issues, incorrect diagnostics, cleared fault codes, repair costs, or any other problems caused directly or indirectly by using this software.

## Troubleshooting

If no adapter is detected:

- Check the USB cable
- Check Device Manager for the COM port on Windows
- Try another USB port
- Confirm the ignition is on
- Select the correct COM port in `Service`
- Try disabling other software that may be using the adapter

If live data is empty:

- Confirm the vehicle supports standard OBD-II
- Try reconnecting
- Try Limited Mode
- Check whether the adapter is a reliable ELM327-compatible device

## License

This project is licensed under the GNU General Public License v3.0.

You are allowed to use, modify, share and distribute this project under the terms of the GPLv3. If you distribute modified versions, you must also provide the source code under the same license.
