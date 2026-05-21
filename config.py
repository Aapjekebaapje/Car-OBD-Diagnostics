"""Local tuning knobs for the OBD Scanner.

Times are in seconds. Lower values feel more live, but they also query the ECU
more often. Keep non-critical values slower to avoid noisy adapters and ECU load.
"""

# Main live-data loop cadence.
POLL_INTERVAL = 0.1

# Dedicated RPM/speed loop cadence for the dashboard gauges.
RPM_POLL_INTERVAL = 0.05

# OBD adapter connection behavior.
OBD_CONNECT_TIMEOUT = 1.0
OBD_CONNECT_ATTEMPTS = 3
OBD_CONNECT_RETRY_DELAY = 1.0

# Upper bound used when the poll guard slows down after repeated query errors.
MAX_POLL_INTERVAL = 0.8

# Sensor priority groups.
FAST_SENSOR_INTERVAL = 0.5
MEDIUM_SENSOR_INTERVAL = 2.0
SLOW_SENSOR_INTERVAL = 10.0

# Default freshness marker for fast live values.
STALE_AFTER_SECONDS = 0.9

# Number of saved scans returned in history.
SCAN_HISTORY_LIMIT = 20
