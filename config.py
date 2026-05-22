# Made by The Syndicate Development
"""Configuration for the OBD Scanner.

All interval values are in seconds.

Lower interval values update the dashboard faster, but they also ask the OBD
adapter and ECU for data more often. If your adapter becomes unstable, shows
missing values, or the dashboard feels noisy, increase the intervals a little.
"""

# Version shown in the dashboard, sidebar and exported HTML reports.
APP_VERSION = "v0.4.2"

# Main dashboard refresh loop.
# This controls the general live-data update speed for normal sensor values.
# 0.1 = 10 times per second.
POLL_INTERVAL = 0.1

# Fast gauge refresh loop for RPM and vehicle speed.
# Keep this low if you want the main gauges to feel close to live.
# 0.05 = 20 times per second.
RPM_POLL_INTERVAL = 0.05

# OBD connection settings.
# Timeout: how long one connection attempt may wait for a response.
# Attempts: how many times the app tries before giving up.
# Retry delay: pause between connection attempts.
OBD_CONNECT_TIMEOUT = 1.0
OBD_CONNECT_ATTEMPTS = 3
OBD_CONNECT_RETRY_DELAY = 1.0

# Maximum live-data delay used by the poll guard.
# If repeated OBD query errors happen, the app slows polling down up to this
# value to give weak adapters or slow ECUs more breathing room.
MAX_POLL_INTERVAL = 0.8

# Sensor priority intervals.
# Fast sensors are useful while driving and can update often.
# Medium sensors are useful, but do not need millisecond updates.
# Slow sensors are non-critical values such as fuel level or counters.
FAST_SENSOR_INTERVAL = 0.5
MEDIUM_SENSOR_INTERVAL = 2.0
SLOW_SENSOR_INTERVAL = 10.0

# Stale-data threshold for fast values.
# If a fast value has not updated within this time, the UI may treat it as old.
STALE_AFTER_SECONDS = 0.9

# Number of saved scans and garage notes shown in history lists.
SCAN_HISTORY_LIMIT = 20
