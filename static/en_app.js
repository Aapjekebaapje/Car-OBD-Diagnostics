const CONNECTED_POLL_MS = 200;
const DISCONNECTED_POLL_MS = 1000;
const FAST_GAUGE_POLL_MS = 40;
const IDLE_GAUGE_POLL_MS = 250;
const TACH_MIN_DEG = 135;
const TACH_MAX_DEG = 405;
const TACH_MAX_RPM = 8000;
const SPEED_MAX = 260;
const STARTUP_MAX_WAIT_MS = 2200;
const FETCH_TIMEOUT_MS = 4000;
const CHART_SAMPLE_MS = 50;
const PORT_POLL_MS = 1000;

let safeMode = true;
let pollTimer = null;
let gaugePollTimer = null;
let gaugeRequestInFlight = false;
let portPollTimer = null;
let isConnected = false;
let currentRpm = 0;
let targetRpm = 0;
let currentSpeed = 0;
let targetSpeed = 0;
let rpmVelocity = 0;
let speedVelocity = 0;
let lastGaugeFrameAt = 0;
let vinRefreshPending = false;
let activePage = "dashboard";
let pageTransitionTimer = null;
let isFrozen = false;
let frozenPayload = null;
let startupDismissed = false;
let lastLivePayload = null;
let lastVehicleProfile = {};
let lastRenderedHealthSignature = "";
let lastRenderedChecklistSignature = "";
let lastRenderedErrorSignature = "";
let lastRenderedLiveDataSignature = "";
let lastRenderedVinExtraSignature = "";
let lastRenderedCodes = {
    "stored-codes": "",
    "pending-codes": "",
    "permanent-codes": ""
};
let lastSafeModeRendered = null;
let codeScanPending = false;
let lastDtcStatus = {};
let lastConnectionQualitySignature = "";
let startupFallbackTimer = null;
let lastReadinessSignature = "";
let lastFreezeFrameSignature = "";
let lastReportSignature = "";
let lastRenderedPortSignature = "";
let demoMode = false;
let demoPreset = "idle";
let demoPresetRequestPending = false;
let limitedMode = false;
let simpleMode = false;
const rpmChartPoints = [];
const speedChartPoints = [];
const CHART_POINT_LIMIT = 60;
const VEHICLE_LOOKUP_HISTORY_KEY = "obd_vehicle_lookup_history";
const VEHICLE_LOOKUP_HISTORY_LIMIT = 10;
const demoPresetMeta = new Map();
let lastChartSampleAt = 0;
const GAUGE_STIFFNESS = 78;
const GAUGE_DAMPING = 0.9;
const RPM_MAX_VELOCITY = 30000;
const SPEED_MAX_VELOCITY = 1200;
const RPM_TARGET_DEADBAND = 12;
const SPEED_TARGET_DEADBAND = 0.4;
const RPM_SNAP_DELTA = 2600;
const SPEED_SNAP_DELTA = 45;

function byId(id) {
    return document.getElementById(id);
}

function setText(id, value) {
    const element = byId(id);
    if (!element) return;
    const next = String(value);
    if (element.textContent !== next) {
        element.textContent = next;
    }
}

function tr(key, fallback, vars = {}) {
    const source = window.APP_I18N || {};
    let text = Object.prototype.hasOwnProperty.call(source, key) ? source[key] : fallback;
    if (typeof text !== "string") {
        text = fallback;
    }
    return text.replace(/\{(\w+)\}/g, (_, name) => String(vars[name] ?? `{${name}}`));
}

function setClassName(id, className) {
    const element = byId(id);
    if (!element) return;
    if (element.className !== className) {
        element.className = className;
    }
}

function numberFromValue(value) {
    if (value === null || value === undefined) return 0;

    const match = String(value).replace(",", ".").match(/-?\d+(\.\d+)?/);
    return match ? Number(match[0]) : 0;
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function mapRange(value, min, max, targetMin, targetMax) {
    const ratio = clamp((value - min) / (max - min), 0, 1);
    return targetMin + ratio * (targetMax - targetMin);
}

function displayValue(value, fallback = "--") {
    if (value === null || value === undefined || value === "") {
        return fallback;
    }

    return String(value);
}

function isUnavailableValue(value) {
    const normalized = String(value ?? "").trim().toLowerCase();
    return normalized === "" || normalized === "--" || normalized === "n/a" || normalized === "null" || normalized === "none";
}

function displayLiveValue(value, fallback = tr("quick_no_data", "No Data")) {
    return isUnavailableValue(value) ? fallback : String(value);
}

function formatLiveValue(value, sensorKey, fallback = tr("quick_no_data", "No Data")) {
    if (isUnavailableValue(value)) {
        return fallback;
    }

    const raw = String(value).trim();
    const normalized = raw.replace(/_/g, " ").trim();
    const numericValue = (() => {
        const match = normalized.replace(/,/g, ".").match(/-?\d+(?:\.\d+)?/);
        return match ? Number(match[0]) : null;
    })();
    const lower = normalized.toLowerCase();

    const tupleMatches = [...normalized.matchAll(/['"]([^'"]+)['"]/g)].map((m) => m[1].trim());
    if (sensorKey === "fuel_system" && tupleMatches.length > 0) {
        const unique = [...new Set(tupleMatches)];
        return unique.join(" / ");
    }

    if (sensorKey === "status") {
        if (/^<obd\.OBDResponse\.Status object/.test(raw)) {
            return tr("status_report", "Status report");
        }
        if (/^<.*object.*>$/.test(raw)) {
            return tr("status_object", "Status object");
        }
    }

    if (sensorKey === "runtime" && Number.isFinite(numericValue)) {
        const totalSeconds = Math.max(0, Math.round(numericValue));
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        return [hours, minutes, seconds].map((part) => String(part).padStart(2, "0")).join(":");
    }

    if (/\bengine load\b/.test(lower) || sensorKey === "engine_load") {
        if (Number.isFinite(numericValue)) {
            return `${Math.round(numericValue)}%`;
        }
        return normalized.replace(/percent/gi, "%");
    }

    if (/\b(degree\s+celsius|degree\s*\s*celsius|celsius)\b/.test(lower)) {
        return Number.isFinite(numericValue) ? `${Math.round(numericValue)} C` : normalized.replace(/degree[\s_]*celcius/gi, "C").replace(/degree[\s_]*celsius/gi, "C");
    }

    if (/\bvolt\b/.test(lower)) {
        return Number.isFinite(numericValue) ? `${numericValue.toFixed(1)} V` : normalized.replace(/volt/gi, "V");
    }

    if (/\bpercent\b/.test(lower) || lower.includes("%")) {
        return Number.isFinite(numericValue) ? `${numericValue.toFixed(2)}%` : normalized.replace(/percent/gi, "%");
    }

    if (/\bkilopascal\b/.test(lower)) {
        return Number.isFinite(numericValue) ? `${numericValue.toFixed(0)} kPa` : normalized.replace(/kilopascal/gi, "kPa");
    }

    if (/\b(second|seconds)\b/.test(lower)) {
        return Number.isFinite(numericValue) ? `${numericValue.toFixed(0)} s` : normalized.replace(/seconds/gi, "s").replace(/second/gi, "s");
    }

    return normalized;
}

function formatCompactDate(value) {
    const raw = String(value || "").trim();
    if (!/^\d{8}$/.test(raw)) {
        return displayValue(value);
    }
    return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`;
}

function buildYearFromDate(value) {
    const raw = String(value || "").trim();
    return /^\d{8}$/.test(raw) ? raw.slice(0, 4) : "";
}

function normalizeVinCandidate(value) {
    const compact = String(value || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
    const match = compact.match(/[A-HJ-NPR-Z0-9]{17}/);
    return match ? match[0] : "";
}

function normalizePlateCandidate(value) {
    const compact = String(value || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (compact.length < 5 || compact.length > 8) {
        return "";
    }
    return compact;
}

function pulseElement(element, className = "is-updating") {
    if (!element) return;
    element.classList.remove(className);
    void element.offsetWidth;
    element.classList.add(className);
}

function animateTextSwap(element) {
    if (!element) return;
    element.classList.remove("text-swap");
    void element.offsetWidth;
    element.classList.add("text-swap");
}

function setLiveMetricText(id, nextText) {
    const element = byId(id);
    if (!element) return;

    const currentText = element.textContent || "";
    if (currentText === nextText) {
        return;
    }

    element.textContent = nextText;
}

function positionGaugeTicks() {
    const gauges = [
        { selector: ".tach-face", gauge: "rpm", radius: 146, xOffset: 0, yOffset: 0 },
        { selector: ".speed-face", gauge: "speed", radius: 146, xOffset: 0, yOffset: 1 }
    ];

    gauges.forEach(({ selector, gauge, radius, xOffset, yOffset }) => {
        const face = document.querySelector(selector);
        if (!face) return;

        const faceRect = face.getBoundingClientRect();
        const centerX = faceRect.width / 2;
        const centerY = faceRect.height / 2;

        face.querySelectorAll(`.tick[data-gauge="${gauge}"]`).forEach((tick) => {
            const angle = Number(tick.dataset.angle || 0) * (Math.PI / 180);
            const x = centerX + Math.cos(angle) * radius + xOffset;
            const y = centerY + Math.sin(angle) * radius + yOffset;
            tick.style.left = `${x}px`;
            tick.style.top = `${y}px`;
            tick.style.transform = "translate(-50%, -50%)";
        });
    });
}

function sanitizeKey(value) {
    return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function clearContainerEmptyState(container) {
    container.querySelectorAll(".empty").forEach((node) => node.remove());
}

function ensureEmptyState(container, text) {
    const existing = container.querySelector(".empty");
    if (existing) {
        if (existing.textContent !== text) {
            existing.textContent = text;
        }
        return existing;
    }

    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = text;
    container.appendChild(empty);
    return empty;
}

function setPage(pageName) {
    if (!pageName || pageName === activePage) {
        return;
    }

    document.querySelectorAll(".module-button").forEach((button) => {
        button.classList.toggle("is-active", button.dataset.page === pageName);
    });

    document.querySelectorAll(".page-screen").forEach((screen) => {
        const isTarget = screen.dataset.page === pageName;
        const isCurrent = screen.dataset.page === activePage;

        if (isCurrent && !isTarget) {
            screen.classList.remove("is-active");
            screen.classList.add("is-leaving");
        } else if (isTarget) {
            screen.classList.remove("is-leaving");
            screen.classList.add("is-active");
        } else {
            screen.classList.remove("is-active", "is-leaving");
        }
    });

    window.clearTimeout(pageTransitionTimer);
    pageTransitionTimer = window.setTimeout(() => {
        document.querySelectorAll(".page-screen.is-leaving").forEach((screen) => {
            screen.classList.remove("is-leaving");
        });
    }, 320);

    activePage = pageName;
    updateShellMode();
    if (pageName === "live") {
        refreshGaugeLayout();
    }
}

function initNavigation() {
    const nav = document.querySelector(".module-nav");

    if (!nav) return;

    nav.addEventListener("click", (event) => {
        const button = event.target.closest(".module-button");
        if (!button) return;
        event.preventDefault();
        setPage(button.dataset.page);
        window.location.hash = button.dataset.page;
    });
}

function initDashboardLauncher() {
    document.querySelectorAll("[data-page-target]").forEach((button) => {
        button.addEventListener("click", () => {
            const page = button.dataset.pageTarget;
            if (!page) return;
            setPage(page);
            window.location.hash = page;
        });
    });
}

function initPageFromHash() {
    const hashPage = window.location.hash.replace("#", "").trim() || "dashboard";

    document.querySelectorAll(".module-button").forEach((button) => {
        button.classList.toggle("is-active", button.dataset.page === hashPage);
    });

    document.querySelectorAll(".page-screen").forEach((screen) => {
        const isTarget = screen.dataset.page === hashPage;
        screen.classList.toggle("is-active", isTarget);
        screen.classList.remove("is-leaving");
    });

    activePage = hashPage;
    updateShellMode();
    if (hashPage === "live") {
        refreshGaugeLayout();
    }
}

function updateShellMode() {
    const screen = document.querySelector(".tablet-screen");
    if (!screen) return;
    screen.classList.toggle("is-home-only", activePage === "dashboard");
}

function refreshGaugeLayout() {
    window.requestAnimationFrame(() => {
        positionGaugeTicks();
        window.requestAnimationFrame(positionGaugeTicks);
    });
}

window.addEventListener("hashchange", initPageFromHash);

function currentDisplayPayload(livePayload) {
    if (isFrozen && frozenPayload) {
        return frozenPayload;
    }
    return livePayload;
}

function storeDemoPresets(presets) {
    demoPresetMeta.clear();
    (presets || []).forEach((preset) => {
        if (!preset?.id) return;
        demoPresetMeta.set(String(preset.id), preset);
    });
}

function dismissStartup(statusMessage = tr("scanner_ready", "Scanner ready.")) {
    if (startupDismissed) return;
    const overlay = byId("startup-overlay");
    setText("startup-message", statusMessage);
    if (!overlay) return;
    window.clearTimeout(startupFallbackTimer);
    window.setTimeout(() => {
        overlay.classList.add("is-hidden");
        startupDismissed = true;
    }, 700);
}

function armStartupFallback() {
    window.clearTimeout(startupFallbackTimer);
    startupFallbackTimer = window.setTimeout(() => {
        dismissStartup(tr("dashboard_loaded", "Dashboard loaded."));
    }, STARTUP_MAX_WAIT_MS);
}

async function fetchData() {
    try {
        await fetchStatusOnly(true);
    } catch (error) {
        console.error(error);
        isConnected = false;
        updateStatus({
            connected: false,
            current_port: "",
            error: tr("frontend_adapter_error", "Cannot connect to the ECU. Check whether the USB OBD adapter is plugged in."),
            user_message: tr("frontend_adapter_message", "Cannot connect to the ECU. The USB OBD adapter may not be connected.")
        });
        updateErrorLog([{
            time: "--",
            source: "Frontend",
            message: error.message,
            technical_message: error.message
        }]);
        dismissStartup(tr("frontend_adapter_short", "Cannot connect to the ECU. Check the USB OBD adapter."));
    } finally {
        scheduleNextPoll();
    }
}

async function fetchStatusOnly(shouldHydrateFullData = false) {
    const response = await fetch("/api/status", {
        signal: AbortSignal.timeout(FETCH_TIMEOUT_MS)
    });
    if (!response.ok) throw new Error(`Server returned status ${response.status}`);

    const payload = await response.json();
    const sessionState = payload.session_state || {};

    isConnected = Boolean(payload.connected);
    demoMode = Boolean(payload.demo_mode);
    safeMode = Boolean(payload.safe_mode);
    limitedMode = Boolean(payload.limited_mode);

    updateStatus(payload, sessionState);
    updateConnectionQuality(payload.connection_quality || {});
    updateSafeModeUi();
    updateLimitedModeUi();
    updateErrorLog(payload.recent_errors || []);
    updateDemoModeUi();
    updateDemoPresetUi();
        dismissStartup(payload.user_message || tr("scanner_ready", "Scanner ready."));

    if (shouldHydrateFullData && (isConnected || demoMode)) {
        await fetchFullData();
    }
}

async function fetchFullData() {
    const response = await fetch("/api/data", {
        signal: AbortSignal.timeout(FETCH_TIMEOUT_MS)
    });
    if (!response.ok) throw new Error(`Server returned status ${response.status}`);

    const payload = await response.json();
    lastLivePayload = payload;
    const status = payload.status || {};
    const vehicleProfile = payload.vehicle_profile || {};
    const displayPayload = currentDisplayPayload(payload);
    const sessionState = displayPayload.session_state || payload.session_state || {};

    if (displayPayload.demo?.presets || payload.demo?.presets) {
        storeDemoPresets(displayPayload.demo?.presets || payload.demo?.presets || []);
    }
    demoPreset = String(
        displayPayload.demo?.preset ||
        payload.demo?.preset ||
        sessionState.demo_preset ||
        demoPreset
    );

    isConnected = Boolean(status.connected);
    demoMode = Boolean(status.demo_mode);
    safeMode = Boolean(status.safe_mode);
    limitedMode = Boolean(status.limited_mode);

    updateStatus(status, sessionState);
    updateConnectionQuality(displayPayload.connection_quality || payload.connection_quality || {});
    updateSafeModeUi();
    updateLimitedModeUi();
    updateErrorLog(status.recent_errors || []);
    updateVehicleProfileView(displayPayload.vehicle_profile || vehicleProfile);
    updateHealth(displayPayload.health || {});
    updateQuickMetrics(displayPayload.vehicle || {});
    updateReadiness(displayPayload.readiness || payload.readiness || {});
    updateFreezeFrame(displayPayload.freeze_frame || payload.freeze_frame || {});
    updateReport(displayPayload.report || payload.report || {});
    updateBatteryCheck(displayPayload.battery_check || payload.battery_check || {});
    updateSimpleSummary(displayPayload.simple_summary || payload.simple_summary || {});
    updatePidSupportSummary(displayPayload.pid_support || payload.pid_support || {});
    updateDtcStatus(displayPayload.dtc_status || payload.dtc_status || {});

    if (!isFrozen) {
        updateGaugeTargets(displayPayload.vehicle || {});
        updateCharts(displayPayload.vehicle || {});
        updateLiveData(displayPayload.vehicle || {});
        updateCodes("stored-codes", displayPayload.dtc?.stored || []);
        updateCodes("pending-codes", displayPayload.dtc?.pending || []);
        updateCodes("permanent-codes", displayPayload.dtc?.permanent || []);
    }

    if (
        status.connected &&
        !status.connecting &&
        !vinRefreshPending &&
        !vehicleProfile.vin &&
        vehicleProfile.vin_status === "idle"
    ) {
        fetchVehicleProfile();
    }

    updateDemoModeUi();
    updateDemoPresetUi();
        dismissStartup(status.user_message || tr("scanner_ready", "Scanner ready."));
}

async function loadConfig() {
    try {
        const response = await fetch("/api/config");
        if (!response.ok) throw new Error(`Server returned status ${response.status}`);
        const config = await response.json();
        demoMode = Boolean(config.demo_mode);
        limitedMode = Boolean(config.limited_mode);
        demoPreset = String(config.demo_preset || "idle");
        storeDemoPresets(config.demo_presets || []);
        const portInput = byId("port-input");
        if (portInput) {
            portInput.value = config.obd_port || "";
        }
        renderPortOptions(config.detected_ports || [], config.obd_port || "");
        updateDemoModeUi();
        updateLimitedModeUi();
        updateDemoPresetUi();
        setText("scope-badge", tr("scope_standard_obd", "Standard OBD Only"));
    } catch (error) {
        console.error(error);
        setText("port-result", tr("port_config_failed", "Could not load COM configuration."));
    }
}

function renderPortOptions(ports, selectedPort = "") {
    const portInput = byId("port-input");
    if (!portInput) return;

    const normalizedPorts = Array.isArray(ports) ? ports : [];
    const nextSignature = JSON.stringify({
        selected: selectedPort || "",
        ports: normalizedPorts.map((port) => ({
            device: String(port?.device || ""),
            description: String(port?.description || "")
        }))
    });
    if (nextSignature === lastRenderedPortSignature) {
        return;
    }
    lastRenderedPortSignature = nextSignature;

    const previousValue = document.activeElement === portInput
        ? portInput.value
        : (selectedPort || portInput.value || "");
    const existingOptions = new Map(Array.from(portInput.options).map((option) => [option.value, option]));

    let emptyOption = existingOptions.get("");
    if (!emptyOption) {
        emptyOption = document.createElement("option");
        emptyOption.value = "";
    }
    emptyOption.textContent = tr("port_dropdown_empty", "No COM port selected");
    portInput.appendChild(emptyOption);

    normalizedPorts.forEach((port) => {
        const device = String(port?.device || "");
        if (!device) {
            return;
        }

        const label = port.description ? `${device} - ${port.description}` : device;
        let option = existingOptions.get(device);
        if (!option) {
            option = document.createElement("option");
            option.value = device;
        }
        option.textContent = label;
        portInput.appendChild(option);
    });

    Array.from(portInput.options).forEach((option) => {
        if (!option.value) {
            return;
        }
        const stillExists = normalizedPorts.some((port) => String(port?.device || "") === option.value);
        if (!stillExists) {
            option.remove();
        }
    });

    portInput.value = previousValue;
    if (portInput.value !== previousValue) {
        portInput.value = "";
    }

    syncPortDropdownUi();
}

function syncPortDropdownUi() {
    const portInput = byId("port-input");
    const trigger = byId("port-dropdown-trigger");
    const valueElement = byId("port-dropdown-value");
    const menu = byId("port-dropdown-menu");
    if (!portInput || !trigger || !valueElement || !menu) return;

    const options = Array.from(portInput.options).map((option) => ({
        value: option.value,
        label: option.textContent || "",
        selected: option.selected
    }));
    const selectedOption = options.find((option) => option.selected) || options[0];

    valueElement.textContent = selectedOption?.label || tr("port_dropdown_empty", "No COM port selected");
    trigger.classList.toggle("is-empty", !selectedOption?.value);

    const fragment = document.createDocumentFragment();
    options.forEach((option) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "port-dropdown-option";
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", option.selected ? "true" : "false");
        if (option.selected) {
            item.classList.add("is-selected");
        }

        const primary = document.createElement("span");
        primary.className = "port-dropdown-option-primary";
        primary.textContent = option.value || tr("port_dropdown_empty", "No COM port selected");

        const secondary = document.createElement("span");
        secondary.className = "port-dropdown-option-secondary";
        secondary.textContent = option.value ? option.label : tr("port_dropdown_helper", "Stay unlocked and do not force a COM port.");

        item.append(primary, secondary);
        item.addEventListener("click", () => {
            if (portInput.value === option.value) {
                setPortDropdownOpen(false);
                return;
            }
            portInput.value = option.value;
            syncPortDropdownUi();
            setPortDropdownOpen(false);
            portInput.dispatchEvent(new Event("change", { bubbles: true }));
        });
        fragment.appendChild(item);
    });

    menu.replaceChildren(fragment);
}

function setPortDropdownOpen(isOpen) {
    const shell = document.querySelector("[data-port-dropdown]");
    const trigger = byId("port-dropdown-trigger");
    const menu = byId("port-dropdown-menu");
    if (!shell || !trigger || !menu) return;

    shell.classList.toggle("is-open", isOpen);
    trigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
    menu.hidden = !isOpen;
}

function initPortDropdown() {
    const shell = document.querySelector("[data-port-dropdown]");
    const trigger = byId("port-dropdown-trigger");
    const menu = byId("port-dropdown-menu");
    const portInput = byId("port-input");
    if (!shell || !trigger || !menu || !portInput) return;

    trigger.addEventListener("click", () => {
        setPortDropdownOpen(!shell.classList.contains("is-open"));
    });

    document.addEventListener("click", (event) => {
        if (!shell.contains(event.target)) {
            setPortDropdownOpen(false);
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            setPortDropdownOpen(false);
        }
    });

    syncPortDropdownUi();
    setPortDropdownOpen(false);
}

function schedulePortPoll() {
    window.clearTimeout(portPollTimer);
    portPollTimer = window.setTimeout(fetchPortOptionsLive, PORT_POLL_MS);
}

async function fetchPortOptionsLive() {
    try {
        const response = await fetch("/api/config/ports", {
            signal: AbortSignal.timeout(FETCH_TIMEOUT_MS)
        });
        if (!response.ok) throw new Error(`Server returned status ${response.status}`);
        const result = await response.json();
        renderPortOptions(result.ports || [], result.selected || "");
    } catch (error) {
        console.error(error);
    } finally {
        schedulePortPoll();
    }
}

function scheduleNextPoll() {
    window.clearTimeout(pollTimer);
    pollTimer = window.setTimeout(fetchData, isConnected ? CONNECTED_POLL_MS : DISCONNECTED_POLL_MS);
}

function scheduleGaugePoll(delay = FAST_GAUGE_POLL_MS) {
    window.clearTimeout(gaugePollTimer);
    gaugePollTimer = window.setTimeout(fetchGaugeData, delay);
}

async function fetchGaugeData() {
    if (gaugeRequestInFlight) {
        scheduleGaugePoll(FAST_GAUGE_POLL_MS);
        return;
    }

    gaugeRequestInFlight = true;
    try {
        const response = await fetch("/api/gauges", {
            signal: AbortSignal.timeout(1000)
        });
        if (!response.ok) throw new Error(`Server returned status ${response.status}`);

        const payload = await response.json();
        const vehicle = {
            rpm: payload.rpm || {},
            speed: payload.speed || {},
        };

        if (!isFrozen && (payload.connected || payload.demo_mode)) {
            updateGaugeTargets(vehicle);
            updateCharts(vehicle);
        }

        scheduleGaugePoll((payload.connected || payload.demo_mode) ? FAST_GAUGE_POLL_MS : IDLE_GAUGE_POLL_MS);
    } catch (error) {
        scheduleGaugePoll(IDLE_GAUGE_POLL_MS);
    } finally {
        gaugeRequestInFlight = false;
    }
}

function updateStatus(status, sessionState = {}) {
    const dot = byId("status-dot");
    const reconnectButton = byId("reconnect-button");

    const portLabel = sessionState.port_label || status.current_port || tr("port_none_selected", "No COM port selected");
    demoMode = Boolean(status.demo_mode);

    if (dot && status.connecting) {
        dot.classList.remove("online");
    } else if (dot && status.connected) {
        dot.classList.add("online");
    } else if (dot) {
        dot.classList.remove("online");
    }

    const statusText = sessionState.status_label || (status.connecting ? tr("status_searching_adapter", "Searching for adapter...") : demoMode ? tr("status_demo_active", "Demo session active") : status.connected ? tr("status_connected", "Vehicle connected") : tr("status_offline", "Connection offline"));
    const adapterStateText = sessionState.adapter_label || (status.connecting ? tr("adapter_searching", "Searching") : demoMode ? tr("adapter_demo", "Demo") : status.connected ? tr("adapter_online", "Online") : tr("adapter_offline", "Offline"));
    const systemStatusText = sessionState.system_label || (status.connecting ? tr("system_searching", "Searching") : demoMode ? tr("system_demo", "Demo") : status.connected ? tr("system_connected", "Connected") : tr("system_offline", "Offline"));
    const liveStateText = demoMode ? tr("live_simulator", "Simulator") : status.connected ? tr("live_streaming", "Streaming") : status.connecting ? tr("live_waiting", "Waiting") : tr("live_no_data", "No Data");
    const connectionHintText = sessionState.detail || (
        status.connection_hint?.label
            ? `${status.connection_hint.label}. ${status.connection_hint.detail || ""}`
            : tr("waiting_for_adapter", "Waiting for adapter detection.")
    );

    if (byId("status-text")?.textContent !== statusText) animateTextSwap(byId("status-text"));
    if (byId("adapter-state")?.textContent !== adapterStateText) animateTextSwap(byId("adapter-state"));
    if (byId("system-status")?.textContent !== systemStatusText) animateTextSwap(byId("system-status"));
    if (byId("connection-hint")?.textContent !== connectionHintText) animateTextSwap(byId("connection-hint"));

    setText("status-text", statusText);
    setText("adapter-state", adapterStateText);
    setText("system-status", systemStatusText);
    setText("protocol", `${tr("protocol_prefix", "Protocol")}: ${status.protocol || "Unknown"}`);
    setText("status-message", status.user_message || (status.connected ? tr("live_streaming", "Streaming") : status.error || tr("status_no_connection", "No connection")));
    setText("last-update", `${tr("update_prefix", "Update")}: ${status.last_update || "--"}`);
    setText("last-successful-update", `${tr("last_live_prefix", "Last live data")}: ${status.last_successful_update || "--"}`);
    setText("current-port", portLabel);
    setText("system-protocol", status.protocol || tr("unknown", "Unknown"));
    setText("system-port", portLabel);
    setText("scope-badge", tr("scope_standard_obd", "Standard OBD Only"));
    setText("live-state", liveStateText);
    setText("connection-hint", connectionHintText);
    updateDemoModeUi();

    if (reconnectButton) {
        reconnectButton.disabled = Boolean(status.connecting);
        reconnectButton.classList.toggle("connecting", Boolean(status.connecting));
        reconnectButton.innerText = status.connecting ? tr("reconnecting", "Reconnecting...") : tr("retry_connection", "Retry Connection");
    }
}

function updateConnectionQuality(quality) {
    const items = [
        { id: "quality-adapter", label: tr("quality_adapter", "Adapter"), online: Boolean(quality.adapter_connected) },
        { id: "quality-port", label: tr("quality_port", "OBD Port"), online: Boolean(quality.port_powered) },
        { id: "quality-car", label: tr("quality_car", "Car"), online: Boolean(quality.car_connected) },
        { id: "quality-live", label: tr("quality_live", "Live"), online: Boolean(quality.live_data_active) }
    ];

    const signature = items.map((item) => `${item.id}:${item.online ? "1" : "0"}`).join("|");
    if (signature === lastConnectionQualitySignature) {
        return;
    }
    lastConnectionQualitySignature = signature;

    items.forEach((item) => {
        const element = byId(item.id);
        if (!element) return;
        const previousState = element.dataset.online;
        const nextState = item.online ? "1" : "0";
        element.classList.toggle("is-online", item.online);
        element.classList.toggle("is-offline", !item.online);
        if (previousState !== nextState) {
            element.dataset.online = nextState;
        }
        element.innerHTML = `<span>${item.label}</span><strong>${item.online ? tr("quality_ok", "Online") : tr("quality_waiting", "Waiting")}</strong>`;
    });
}

function updateDemoModeUi() {
    const button = byId("demo-mode-button");
    const copy = byId("demo-mode-copy");
    if (button) {
        button.innerText = demoMode ? tr("demo_disable", "Disable Demo Mode") : tr("demo_enable", "Enable Demo Mode");
        button.classList.toggle("is-active", demoMode);
    }
    if (copy) {
        const presetLabel = demoPresetMeta.get(demoPreset)?.label || tr("idle", "Idle");
        copy.innerText = demoMode
            ? tr("demo_mode_live", "Demo mode is live on the {preset} preset and keeps updating automatically.", { preset: presetLabel })
            : tr("demo_mode_off", "Use demo mode to test the UI without a USB adapter or car.");
    }
}

function updateLimitedModeUi() {
    const button = byId("limited-mode-button");
    const copy = byId("limited-mode-copy");
    const topbarState = byId("limited-mode-state");
    if (button) {
        button.innerText = limitedMode
            ? tr("limited_mode_disable", "Disable Limited Mode")
            : tr("limited_mode_enable", "Enable Limited Mode");
        button.classList.toggle("is-active", limitedMode);
    }
    if (copy) {
        copy.innerText = limitedMode
            ? tr("limited_mode_live", "Limited Mode is on. Only RPM, speed, coolant temp, ECU voltage, engine load and long fuel trim are polled.")
            : tr("limited_mode_off_copy", "Limited Mode is off. The scanner polls the full live ECU data set.");
    }
    if (topbarState) {
        topbarState.innerText = limitedMode
            ? tr("limited_mode_on_short", "On")
            : tr("limited_mode_off_short", "Off");
    }
}

function updateDemoPresetUi() {
    const copy = byId("demo-preset-copy");
    const preset = demoPresetMeta.get(demoPreset);

    document.querySelectorAll("[data-demo-preset]").forEach((button) => {
        const isActive = button.dataset.demoPreset === demoPreset;
        button.classList.toggle("is-active", isActive);
        button.disabled = demoPresetRequestPending;
    });

    if (copy) {
    copy.innerText = preset?.description || tr("demo_preset_calm", "Pick a calm simulator preset before driving the demo gauges.");
    }
}

function updateErrorLog(errors) {
    const errorLog = byId("error-log");
    if (!errorLog) return;

    const signature = JSON.stringify(errors || []);
    if (signature === lastRenderedErrorSignature) {
        return;
    }
    lastRenderedErrorSignature = signature;

    errorLog.replaceChildren();

    if (!errors || errors.length === 0) {
        const empty = document.createElement("p");
        empty.textContent = tr("errors_empty", "No errors logged.");
        errorLog.appendChild(empty);
        return;
    }

    errors.forEach((item, index) => {
        const row = document.createElement("div");
        row.className = "error-row";
        row.style.animationDelay = `${Math.min(index * 28, 220)}ms`;

        const meta = document.createElement("span");
        meta.textContent = `${item.time || "--"} - ${item.source || tr("unknown", "Unknown")}`;

        const message = document.createElement("strong");
        message.textContent = item.message || tr("unknown_error", "Unknown error");

        row.append(meta, message);

        if (item.technical_message) {
            const details = document.createElement("details");
            details.className = "technical-details";
            const summary = document.createElement("summary");
        summary.textContent = tr("technical_details", "Technical details");
            const pre = document.createElement("pre");
            pre.textContent = item.technical_message;
            details.append(summary, pre);
            row.appendChild(details);
        }

        errorLog.appendChild(row);
    });
}

function updateGaugeTargets(vehicle) {
    const nextRpm = numberFromValue(vehicle.rpm?.value);
    const nextSpeed = numberFromValue(vehicle.speed?.value);

    if (nextRpm !== null && nextRpm !== undefined && Math.abs(nextRpm - targetRpm) >= RPM_TARGET_DEADBAND) {
        targetRpm = nextRpm;
    }
    if (nextSpeed !== null && nextSpeed !== undefined && Math.abs(nextSpeed - targetSpeed) >= SPEED_TARGET_DEADBAND) {
        targetSpeed = nextSpeed;
    }
}

function smoothGaugeValue(current, target, velocity, dt, maxVelocity, snapDelta) {
    const difference = target - current;
    if (Math.abs(difference) >= snapDelta) {
        return {
            current: target,
            velocity: 0,
        };
    }

    const acceleration = difference * GAUGE_STIFFNESS;
    const nextVelocity = clamp(
        (velocity + acceleration * dt) * Math.pow(GAUGE_DAMPING, dt * 60),
        -maxVelocity,
        maxVelocity
    );
    const nextCurrent = current + nextVelocity * dt;

    if (Math.abs(target - nextCurrent) < 0.08 && Math.abs(nextVelocity) < 0.15) {
        return {
            current: target,
            velocity: 0,
        };
    }

    return {
        current: nextCurrent,
        velocity: nextVelocity,
    };
}

function updateQuickMetrics(vehicle) {
    setLiveMetricText("quick-coolant", formatLiveValue(vehicle.coolant_temp?.value, "coolant_temp"));
    setLiveMetricText("quick-voltage", formatLiveValue(vehicle.control_voltage?.value || vehicle.voltage?.value, "control_voltage"));
    setLiveMetricText("quick-fuel-trim", formatLiveValue(vehicle.long_fuel_trim_1?.value, "long_fuel_trim_1"));
    setLiveMetricText("quick-engine-load", formatLiveValue(vehicle.engine_load?.value, "engine_load"));
}

function pushChartPoint(buffer, value) {
    buffer.push(value);
    if (buffer.length > CHART_POINT_LIMIT) {
        buffer.shift();
    }
}

function drawLineChart(canvasId, values, color, maxValueHint = 100) {
    const canvas = byId(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    ctx.fillStyle = "#f3f6fa";
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = "#d6dee8";
    ctx.lineWidth = 1;
    for (let i = 1; i < 4; i += 1) {
        const y = (height / 4) * i;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
    }

    if (!values.length) {
        return;
    }

    const maxValue = Math.max(maxValueHint, ...values, 1);
    const stepX = values.length > 1 ? width / (values.length - 1) : width;

    const points = values.map((value, index) => ({
        x: stepX * index,
        y: height - (Math.max(value, 0) / maxValue) * (height - 12) - 6
    }));

    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);

    if (points.length === 1) {
        ctx.lineTo(points[0].x, points[0].y);
    } else {
        for (let index = 0; index < points.length - 1; index += 1) {
            const current = points[index];
            const next = points[index + 1];
            const midX = (current.x + next.x) / 2;
            const midY = (current.y + next.y) / 2;
            ctx.quadraticCurveTo(current.x, current.y, midX, midY);
        }

        const lastPoint = points[points.length - 1];
        ctx.lineTo(lastPoint.x, lastPoint.y);
    }

    ctx.stroke();
}

function updateCharts(vehicle) {
    if (!rpmChartPoints.length) {
        pushChartPoint(rpmChartPoints, numberFromValue(vehicle.rpm?.value));
    }
    if (!speedChartPoints.length) {
        pushChartPoint(speedChartPoints, numberFromValue(vehicle.speed?.value));
    }
}

function renderCharts(now) {
    if (!lastChartSampleAt || now - lastChartSampleAt >= CHART_SAMPLE_MS) {
        pushChartPoint(rpmChartPoints, currentRpm);
        pushChartPoint(speedChartPoints, currentSpeed);
        lastChartSampleAt = now;
    }

    drawLineChart("rpm-chart", rpmChartPoints, "#e14d4d", 5000);
    drawLineChart("speed-chart", speedChartPoints, "#0d6efd", 160);
}

function updateHealth(health) {
    const score = health.score ?? "--";
    const status = health.status || "good";
    const counts = health.counts || { stored: 0, pending: 0, permanent: 0 };
    const healthSignature = JSON.stringify({
        score,
        status,
        headline: health.headline || tr("health_unavailable", "Health report unavailable."),
        counts
    });

    if (healthSignature !== lastRenderedHealthSignature) {
        lastRenderedHealthSignature = healthSignature;
        setText("health-score", score);
    setText("health-headline", health.headline || tr("health_unavailable", "Health report unavailable."));
        setClassName("health-status-badge", `health-status-badge status-${status}`);
    setText("health-status-badge", status === "danger" ? tr("health_attention", "Attention") : status === "warning" ? tr("health_check", "Check") : tr("health_good", "Good"));
        setClassName("stored-status-pill", `status-pill ${counts.stored ? "status-danger" : "status-good"}`);
        setClassName("pending-status-pill", `status-pill ${counts.pending ? "status-warning" : "status-good"}`);
        setClassName("permanent-status-pill", `status-pill ${counts.permanent ? "status-warning" : "status-info"}`);
    setText("stored-status-pill", `${counts.stored || 0} ${tr("codes_stored", "Stored")}`);
    setText("pending-status-pill", `${counts.pending || 0} ${tr("codes_pending", "Pending")}`);
    setText("permanent-status-pill", `${counts.permanent || 0} ${tr("codes_permanent", "Permanent")}`);
    }

    updateCountDisplays("stored-count", counts.stored || 0);
    updateCountDisplays("pending-count", counts.pending || 0);
    updateCountDisplays("permanent-count", counts.permanent || 0);

    const checklist = byId("purchase-checklist");
    if (!checklist) return;

    const items = health.checklist || [];
    const checklistSignature = JSON.stringify(items);
    if (checklistSignature === lastRenderedChecklistSignature) {
        return;
    }
    lastRenderedChecklistSignature = checklistSignature;

    if (items.length === 0) {
        let empty = checklist.querySelector('[data-key="health-empty"]');
        if (!empty) {
            checklist.replaceChildren();
            empty = document.createElement("div");
            empty.className = "checklist-item level-good";
            empty.dataset.key = "health-empty";
            empty.innerHTML = `<strong>${tr("health_no_red_flags_title", "No obvious red flags from current scan.")}</strong><p>${tr("health_no_red_flags_copy", "Still verify with a road test and visual inspection.")}</p>`;
            checklist.appendChild(empty);
        }
        return;
    }

    const nextKeys = new Set(items.map((item, index) => sanitizeKey(`${item.level || "info"}-${item.title || `item-${index}`}`)));

    Array.from(checklist.children).forEach((child) => {
        if (!nextKeys.has(child.dataset.key || "")) {
            child.remove();
        }
    });

    items.forEach((item, index) => {
        const rowKey = sanitizeKey(`${item.level || "info"}-${item.title || `item-${index}`}`);
        let row = checklist.querySelector(`[data-key="${rowKey}"]`);

        if (!row) {
            row = document.createElement("div");
            row.dataset.key = rowKey;
            row.innerHTML = "<strong></strong><p></p>";
            checklist.appendChild(row);
        }

        row.className = `checklist-item level-${item.level || "info"}`;
        row.querySelector("strong").textContent = item.title || tr("notice", "Notice");
        row.querySelector("p").textContent = item.detail || "";
    });
}

function updateReadiness(readiness) {
    const container = byId("readiness-grid");
    if (!container) return;

    const signature = JSON.stringify(readiness || {});
    if (signature === lastReadinessSignature) {
        return;
    }
    lastReadinessSignature = signature;

    if (!readiness.available) {
        Array.from(container.children).forEach((child) => {
            if (!child.classList.contains("empty")) {
                child.remove();
            }
        });
        ensureEmptyState(container, tr("readiness_empty", "Readiness monitor data is not available yet."));
        return;
    }

    clearContainerEmptyState(container);

    const nextKeys = new Set(["mil", ...(readiness.monitors || []).map((item) => `monitor-${sanitizeKey(item.name)}`)]);
    Array.from(container.children).forEach((child) => {
        if (!nextKeys.has(child.dataset.key || "")) {
            child.remove();
        }
    });

    let milRow = container.querySelector('[data-key="mil"]');
    if (!milRow) {
        milRow = document.createElement("div");
        milRow.className = "support-row";
        milRow.dataset.key = "mil";
        milRow.innerHTML = `<div><strong>MIL</strong><p></p></div>`;
        container.appendChild(milRow);
    }
    milRow.querySelector("p").textContent = `${readiness.mil ? tr("readiness_on", "On") : tr("readiness_off", "Off")} | ${tr("readiness_dtc_count", "DTC count")}: ${readiness.dtc_count ?? "--"} | ${displayValue(readiness.ignition_type, tr("readiness_unknown_ignition", "Unknown ignition"))}`;

    (readiness.monitors || []).forEach((item, index) => {
        const rowKey = `monitor-${sanitizeKey(item.name)}`;
        let row = container.querySelector(`[data-key="${rowKey}"]`);
        if (!row) {
            row = document.createElement("div");
            row.dataset.key = rowKey;
            row.innerHTML = `<div><strong></strong><p></p></div><span class="support-badge"></span>`;
            container.appendChild(row);
        }
        row.className = `support-row ${item.complete ? "is-supported" : "is-unsupported"}`;
        row.style.animationDelay = `${Math.min(index * 18, 200)}ms`;
        row.querySelector("strong").textContent = item.name;
        row.querySelector("p").textContent = item.available ? tr("support_yes", "Supported") : tr("support_no", "Unavailable");
        const badge = row.querySelector(".support-badge");
        badge.className = `support-badge ${item.complete ? "status-good" : "status-warning"}`;
        badge.textContent = item.complete ? tr("readiness_ready", "Ready") : tr("readiness_incomplete", "Incomplete");
    });
}

function updateFreezeFrame(freezeFrame) {
    const container = byId("freeze-frame-grid");
    if (!container) return;

    const signature = JSON.stringify(freezeFrame || {});
    if (signature === lastFreezeFrameSignature) {
        return;
    }
    lastFreezeFrameSignature = signature;

    if (!freezeFrame.available || !freezeFrame.values || Object.keys(freezeFrame.values).length === 0) {
        Array.from(container.children).forEach((child) => {
            if (!child.classList.contains("empty")) {
                child.remove();
            }
        });
        ensureEmptyState(container, tr("freeze_frame_empty", "No freeze-frame snapshot available."));
        return;
    }

    clearContainerEmptyState(container);
    const entries = Object.entries(freezeFrame.values);
    const nextKeys = new Set(entries.map(([key]) => key));
    Array.from(container.children).forEach((child) => {
        if (!nextKeys.has(child.dataset.key || "")) {
            child.remove();
        }
    });

    entries.forEach(([key, value], index) => {
        let row = container.querySelector(`[data-key="${key}"]`);
        if (!row) {
            row = document.createElement("div");
            row.className = "sensor-row";
            row.dataset.key = key;
            row.innerHTML = `<span class="sensor-label"></span><strong class="sensor-value"></strong>`;
            container.appendChild(row);
        }
        row.style.animationDelay = `${Math.min(index * 18, 220)}ms`;
        row.querySelector(".sensor-label").textContent = key.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
        row.querySelector(".sensor-value").textContent = value;
    });
}

function updateReport(report) {
    const summary = byId("report-summary");
    const sections = byId("report-sections");
    if (!summary || !sections) return;

    const signature = JSON.stringify(report || {});
    if (signature === lastReportSignature) {
        return;
    }
    lastReportSignature = signature;

    setText("report-headline", report.headline || tr("report_fallback_headline", "Pre-purchase summary"));
    const summaryItems = report.summary || [];
    const detailSections = report.sections || [];

    if (summaryItems.length === 0) {
        Array.from(summary.children).forEach((child) => {
            if (!child.classList.contains("empty")) {
                child.remove();
            }
        });
        ensureEmptyState(summary, tr("report_summary_empty", "No report summary available yet."));
    } else {
        clearContainerEmptyState(summary);
        const nextKeys = new Set(summaryItems.map((_, index) => `summary-${index}`));
        Array.from(summary.children).forEach((child) => {
            if (!nextKeys.has(child.dataset.key || "")) {
                child.remove();
            }
        });
        summaryItems.forEach((item, index) => {
            const rowKey = `summary-${index}`;
            let row = summary.querySelector(`[data-key="${rowKey}"]`);
            if (!row) {
                row = document.createElement("div");
                row.className = "history-row";
                row.dataset.key = rowKey;
                row.innerHTML = `<div><strong></strong></div>`;
                summary.appendChild(row);
            }
            row.style.animationDelay = `${Math.min(index * 20, 220)}ms`;
            row.querySelector("strong").textContent = item;
        });
    }

    if (detailSections.length === 0) {
        Array.from(sections.children).forEach((child) => {
            if (!child.classList.contains("empty")) {
                child.remove();
            }
        });
        ensureEmptyState(sections, tr("report_details_empty", "No report details available yet."));
    } else {
        clearContainerEmptyState(sections);
        const nextKeys = new Set(detailSections.map((section, index) => `section-${sanitizeKey(section.title || index)}`));
        Array.from(sections.children).forEach((child) => {
            if (!nextKeys.has(child.dataset.key || "")) {
                child.remove();
            }
        });
        detailSections.forEach((section, index) => {
            const rowKey = `section-${sanitizeKey(section.title || index)}`;
            let row = sections.querySelector(`[data-key="${rowKey}"]`);
            if (!row) {
                row = document.createElement("div");
                row.className = "history-row";
                row.dataset.key = rowKey;
                row.innerHTML = `<div><strong></strong><p></p></div>`;
                sections.appendChild(row);
            }
            row.style.animationDelay = `${Math.min(index * 20, 220)}ms`;
            row.querySelector("strong").textContent = section.title;
            row.querySelector("p").textContent = (section.items || []).join(" | ");
        });
    }
}

function updateBatteryCheck(battery) {
    const badge = byId("battery-status-badge");
    const status = battery.status || "unknown";

    setText("battery-headline", battery.headline || tr("battery_unavailable", "Battery check unavailable"));
    setText("battery-detail", battery.detail || tr("battery_empty", "Voltage data is not available yet."));

    if (badge) {
        badge.className = `health-status-badge status-${status === "unknown" ? "info" : status}`;
        badge.textContent = status === "good"
            ? tr("health_good", "Good")
            : status === "warning"
                ? tr("health_check", "Check")
                : status === "danger"
                    ? tr("health_attention", "Attention")
                    : tr("unknown", "Unknown");
    }
}

function updateSimpleSummary(summary) {
    const panel = byId("simple-summary-panel");
    const list = byId("simple-summary-list");
    const button = byId("simple-mode-button");
    if (!panel || !list) return;

    panel.hidden = !simpleMode;
    if (button) {
        button.classList.toggle("is-active", simpleMode);
        button.setAttribute("aria-pressed", String(simpleMode));
        button.textContent = simpleMode ? tr("simple_mode_hide", "Hide Simple Mode") : tr("simple_mode_show", "Show Simple Mode");
    }
    if (!simpleMode) return;

    setText("simple-summary-headline", summary.headline || tr("simple_summary_unavailable", "Simple summary unavailable."));
    list.replaceChildren();
    (summary.items || []).forEach((item, index) => {
        const row = document.createElement("div");
        row.className = `checklist-item level-${summary.level || "info"}`;
        row.style.animationDelay = `${Math.min(index * 20, 180)}ms`;
        row.innerHTML = `<strong>${summary.headline || tr("simple_summary", "Simple summary")}</strong><p></p>`;
        row.querySelector("p").textContent = item;
        list.appendChild(row);
    });
}

function updatePidSupportSummary(support) {
    const container = byId("pid-support-summary");
    if (!container) return;

    const supported = support.supported_count ?? 0;
    const unsupported = support.unsupported_count ?? 0;
    const total = support.total ?? supported + unsupported;

    const cards = [
        { label: tr("pid_supported", "Supported"), value: supported },
        { label: tr("pid_unsupported", "Unsupported"), value: unsupported },
        { label: tr("pid_total", "Total checked"), value: total }
    ];

    container.replaceChildren();
    cards.forEach((card) => {
        const element = document.createElement("div");
        element.innerHTML = `<span>${card.value}</span><p>${card.label}</p>`;
        container.appendChild(element);
    });
}

function toggleSimpleMode() {
    simpleMode = !simpleMode;
    updateSimpleSummary(lastLivePayload?.simple_summary || {});
}

async function exportScanReport() {
    if (!isFrozen || !frozenPayload) {
        window.location.href = "/api/report/export";
        return;
    }

    try {
        const response = await fetch("/api/report/export", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(frozenPayload)
        });
        if (!response.ok) throw new Error(`Server returned status ${response.status}`);

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        const timestamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15);
        link.href = url;
        link.download = `obd-scan-report-${timestamp}.html`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    } catch (error) {
        console.error(error);
        setText("report-action-result", tr("save_scan_failed", "Scan could not be saved."));
    }
}

function formatEngine(decoded) {
    if (decoded.engine_summary) {
        return decoded.engine_summary;
    }

    const parts = [];
    if (decoded.engine_cylinders) parts.push(`${decoded.engine_cylinders} cyl`);
    if (decoded.engine_displacement_l) parts.push(`${decoded.engine_displacement_l} L`);
    if (decoded.engine_model) parts.push(decoded.engine_model);
    if (decoded.engine_power_hp) parts.push(`${decoded.engine_power_hp} hp`);
    return parts.length > 0 ? parts.join(" / ") : "--";
}

function renderVinExtraDetails(decoded) {
    const container = byId("vin-extra-details");
    if (!container) return;

    const details = Array.isArray(decoded.extra_details) ? decoded.extra_details : [];
    const signature = JSON.stringify(
        details.map((detail, index) => ({
            key: String(detail?.key || `detail-${index}`),
        label: String(detail?.label || tr("detail", "Detail")),
            value: displayValue(detail?.value),
        }))
    );

    if (signature === lastRenderedVinExtraSignature) {
        return;
    }
    lastRenderedVinExtraSignature = signature;

    const expectedKeys = new Set();

    if (!details.length) {
        clearContainerEmptyState(container);
        container.querySelectorAll(".spec-card").forEach((card) => card.remove());
        ensureEmptyState(container, tr("vin_extra_empty", "No additional VIN details were returned by the decoder for this vehicle."));
        return;
    }

    clearContainerEmptyState(container);

    details.forEach((detail, index) => {
        const cardKey = String(detail.key || `detail-${index}`);
        expectedKeys.add(cardKey);

        let card = container.querySelector(`.spec-card[data-key="${cardKey}"]`);
        if (!card) {
            card = document.createElement("div");
            card.className = "spec-card";
            card.dataset.key = cardKey;
            card.innerHTML = "<span></span><strong></strong>";
            container.appendChild(card);
        }

        const label = detail.label || tr("detail", "Detail");
        const value = displayValue(detail.value);
        const labelNode = card.querySelector("span");
        const valueNode = card.querySelector("strong");

        if (labelNode && labelNode.textContent !== label) {
            labelNode.textContent = label;
        }
        if (valueNode && valueNode.textContent !== value) {
            valueNode.textContent = value;
        }
    });

    container.querySelectorAll(".spec-card").forEach((card) => {
        if (!expectedKeys.has(card.dataset.key || "")) {
            card.remove();
        }
    });
}

function sleep(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
}
function updateVehicleProfileView(profile) {
    lastVehicleProfile = {
        ...lastVehicleProfile,
        ...profile,
        decoded: profile.decoded !== undefined ? profile.decoded : (lastVehicleProfile.decoded || {}),
        rdw: profile.rdw !== undefined ? profile.rdw : (lastVehicleProfile.rdw || {})
    };

    const vin = lastVehicleProfile.vin || "";
    const decoded = lastVehicleProfile.decoded || {};
    const rdw = lastVehicleProfile.rdw || {};

    setText("vin-value", vin || tr("vin_not_loaded_short", "Not loaded"));
    setText("vin-message", lastVehicleProfile.vin_message || tr("vin_not_loaded", "VIN not loaded yet."));
    const manualVinInput = byId("manual-vin-input");
    if (manualVinInput && vin && document.activeElement !== manualVinInput) {
        manualVinInput.value = vin;
    }
    setText("manual-vin-result", lastVehicleProfile.vin_message || tr("vin_manual_default", "Enter a manual VIN when the ECU does not return one automatically."));
    setText("vin-make", displayValue(decoded.make));
    setText("vin-model", displayValue(decoded.model));
    setText("vin-year", displayValue(decoded.model_year));
    setText("vin-fuel", displayValue(decoded.fuel_type));
    setText("vin-body", displayValue(decoded.body_class || decoded.vehicle_type));
    setText("vin-engine", formatEngine(decoded));
    setText("vin-drive", displayValue(decoded.drive_type || decoded.transmission_style));
    setText("vin-plant", displayValue(decoded.plant_location || decoded.plant_company || decoded.plant_country));
    renderVinExtraDetails(decoded);

    const plateInput = byId("plate-input");
    if (plateInput && lastVehicleProfile.plate_query) {
        plateInput.value = lastVehicleProfile.plate_query;
    }

    setText("plate-result", lastVehicleProfile.plate_message || tr("plate_default", "Enter a Dutch license plate manually to load RDW data."));
    setText("rdw-plate", displayValue(rdw.plate));
    setText("rdw-brand", displayValue(rdw.brand));
    setText("rdw-model", displayValue(rdw.model));
    setText("rdw-vehicle-type", displayValue(rdw.vehicle_type));
    setText("rdw-fuel", displayValue(rdw.fuel));
    setText("rdw-color", displayValue(rdw.color));
    setText("rdw-apk", formatCompactDate(rdw.apk_expiry));
    setText("rdw-first-registration", formatCompactDate(rdw.first_registration));
    setText("rdw-build-year", displayValue(buildYearFromDate(rdw.first_registration)));
    setText("rdw-engine-cc", rdw.engine_cc ? `${rdw.engine_cc} cc` : "--");
    setText("rdw-weight", rdw.weight_empty ? `${rdw.weight_empty} kg` : "--");

    const refreshButton = byId("refresh-vin-button");
    if (refreshButton) {
        refreshButton.disabled = vinRefreshPending || lastVehicleProfile.vin_status === "loading";
    refreshButton.innerText = (vinRefreshPending || lastVehicleProfile.vin_status === "loading") ? tr("reading", "Reading...") : tr("read_vin", "Read VIN");
    }

    const manualVinButton = byId("manual-vin-button");
    if (manualVinButton) {
        manualVinButton.disabled = vinRefreshPending || lastVehicleProfile.vin_status === "loading";
        manualVinButton.innerText = (vinRefreshPending || lastVehicleProfile.vin_status === "loading") ? tr("adapter_searching", "Searching") + "..." : tr("search_vin", "Search VIN");
    }

    const clearVinButton = byId("clear-vin-button");
    if (clearVinButton) {
        clearVinButton.disabled = vinRefreshPending || lastVehicleProfile.vin_status === "loading";
    }
}

function renderGauges(now = performance.now()) {
    const rpmNeedle = document.getElementById("rpm-needle");
    const speedNeedle = document.getElementById("speed-needle");
    const rpmValue = document.getElementById("rpm-value");
    const speedValue = document.getElementById("speed-value");
    const tachFace = document.querySelector(".tach-face");
    const speedFace = document.querySelector(".speed-face");

    if (!rpmNeedle || !rpmValue || !tachFace) {
        requestAnimationFrame(renderGauges);
        return;
    }

    const dt = clamp(lastGaugeFrameAt ? (now - lastGaugeFrameAt) / 1000 : 1 / 60, 1 / 240, 0.05);
    lastGaugeFrameAt = now;

    const rpmState = smoothGaugeValue(currentRpm, targetRpm, rpmVelocity, dt, RPM_MAX_VELOCITY, RPM_SNAP_DELTA);
    currentRpm = rpmState.current;
    rpmVelocity = rpmState.velocity;

    const speedState = smoothGaugeValue(currentSpeed, targetSpeed, speedVelocity, dt, SPEED_MAX_VELOCITY, SPEED_SNAP_DELTA);
    currentSpeed = speedState.current;
    speedVelocity = speedState.velocity;

    const rpmAngle = mapRange(currentRpm, 0, TACH_MAX_RPM, TACH_MIN_DEG, TACH_MAX_DEG);
    const speedAngle = mapRange(currentSpeed, 0, SPEED_MAX, TACH_MIN_DEG, TACH_MAX_DEG);
    const rpmIntensity = clamp(currentRpm / TACH_MAX_RPM, 0, 1);
    const speedIntensity = clamp(currentSpeed / SPEED_MAX, 0, 1);

    rpmNeedle.style.transform = `rotate(${rpmAngle}deg)`;
    if (speedNeedle) {
        speedNeedle.style.transform = `rotate(${speedAngle}deg)`;
    }
    rpmValue.textContent = currentRpm / 1000 < 0.05 ? "0" : (currentRpm / 1000).toFixed(1);
    speedValue.textContent = currentSpeed < 0.05 ? "0" : String(Math.round(currentSpeed));
    tachFace.style.setProperty("--rpm-glow", `${0.12 + rpmIntensity * 0.5}`);
    tachFace.style.setProperty("--rpm-scale", `${1 + rpmIntensity * 0.01}`);
    if (speedFace) {
        speedFace.style.setProperty("--rpm-glow", `${0.12 + speedIntensity * 0.45}`);
        speedFace.style.setProperty("--rpm-scale", `${1 + speedIntensity * 0.008}`);
    }

    renderCharts(now);
    requestAnimationFrame(renderGauges);
}

function updateLiveData(vehicle) {
    const grid = byId("live-grid");
    if (!grid) return;

    const signature = JSON.stringify(vehicle || {});
    if (signature === lastRenderedLiveDataSignature) {
        return;
    }
    lastRenderedLiveDataSignature = signature;

    if (!vehicle || Object.keys(vehicle).length === 0) {
        Array.from(grid.children).forEach((child) => {
            if (!child.classList.contains("empty")) {
                child.remove();
            }
        });
        ensureEmptyState(grid, tr("no_live_data", "No live data available yet."));
        return;
    }

    clearContainerEmptyState(grid);
    const liveKeys = Object.keys(vehicle).filter((key) => key !== "rpm" && key !== "speed");
    const nextKeys = new Set(liveKeys);
    Array.from(grid.children).forEach((child) => {
        if (!nextKeys.has(child.dataset.key || "")) {
            child.remove();
        }
    });

    liveKeys.forEach((key) => {
        if (key === "rpm" || key === "speed") return;

        const item = vehicle[key];
        const hasNoData = isUnavailableValue(item.value);
        let row = grid.querySelector(`[data-key="${key}"]`);
        if (!row) {
            row = document.createElement("div");
            row.dataset.key = key;
            row.innerHTML = `<div class="sensor-row-main"><span class="sensor-label"></span><span class="sensor-row-meta"></span></div><div class="sensor-row-side"><span class="sensor-state-badge">SNSR</span><strong class="sensor-value"></strong></div>`;
            grid.appendChild(row);
        }
        row.className = "sensor-row";
        row.classList.toggle("is-stale", Boolean(item.stale));
        row.classList.toggle("is-no-data", hasNoData);
        row.querySelector(".sensor-label").textContent = item.label;
        row.querySelector(".sensor-row-meta").textContent = hasNoData
            ? tr("sensor_unavailable", "Sensor unavailable right now")
            : item.stale
                ? tr("stale_at", "Stale | last ok {time}", { time: item.updated_at || "--" })
                : tr("updated_at", "Updated {time}", { time: item.updated_at || "--" });
        row.querySelector(".sensor-value").textContent = hasNoData ? tr("sensor_no_data", "No Data") : formatLiveValue(item.value, key);
    });
}

function updateCountDisplays(baseId, value) {
    const primary = document.getElementById(baseId);
    if (primary) primary.textContent = value;

    const secondary = document.getElementById(`${baseId}-codes`);
    if (secondary) secondary.textContent = value;
}

function updateDtcStatus(status) {
    lastDtcStatus = { ...lastDtcStatus, ...status };

    const scanButton = byId("scan-codes-button");
    const statusMessage = lastDtcStatus.message || tr("fault_codes_status", "No fault code scan run yet.");

    setText("codes-status-message", statusMessage);

    if (scanButton) {
        const isScanning = codeScanPending || Boolean(lastDtcStatus.scanning);
        scanButton.disabled = isScanning;
        scanButton.innerText = isScanning ? tr("scanning", "Scanning...") : tr("scan_codes", "Scan Codes");
    }
}

function updateCodes(elementId, codes) {
    const container = byId(elementId);
    if (!container) return;

    const signature = JSON.stringify({
        has_scan: Boolean(lastDtcStatus.has_scan),
        codes: codes || []
    });
    if (signature === lastRenderedCodes[elementId]) {
        updateCountDisplays(elementId.replace("-codes", "-count"), codes ? codes.length : 0);
        return;
    }
    lastRenderedCodes[elementId] = signature;

    const countId = elementId.replace("-codes", "-count");
    const total = codes ? codes.length : 0;

    updateCountDisplays(countId, total);
    container.replaceChildren();

    if (!codes || codes.length === 0) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = lastDtcStatus.has_scan ? tr("fault_codes_empty", "No fault codes found.") : tr("fault_codes_scan_first", "Run a manual fault code scan first.");
        container.appendChild(empty);
        return;
    }

    codes.forEach((item, index) => {
        const isMisfire = item.misfire !== null && item.misfire !== undefined;
        const code = document.createElement("div");
        code.className = `code severity-${item.severity || "unknown"}${isMisfire ? " misfire" : ""}`;
        code.style.animationDelay = `${Math.min(index * 24, 260)}ms`;

        const title = document.createElement("strong");
        title.textContent = item.code;

        const description = document.createElement("p");
    description.textContent = item.description_en || item.description || tr("no_description", "No description available");

        const meta = document.createElement("span");
        meta.className = "code-meta";
    meta.textContent = `${item.system || tr("unknown_system", "Unknown system")} - ${severityLabel(item.severity)}`;

        const action = document.createElement("p");
        action.className = "code-action";
    action.textContent = item.action_hint || tr("inspect_code_hint", "Inspect this code before making a decision.");

        code.append(title, meta, description, action);

        if (item.code_type) {
            const typeBadge = document.createElement("span");
            typeBadge.className = "code-type-badge";
            typeBadge.textContent = item.code_type;
            code.appendChild(typeBadge);
        }

        if (isMisfire) {
            const misfire = document.createElement("p");
            misfire.className = "misfire-note";
            misfire.textContent = `Misfire detection: ${item.misfire}`;
            code.appendChild(misfire);
        }

        if (item.possible_causes && item.possible_causes.length > 0) {
            const causes = document.createElement("ul");
            causes.className = "cause-list";
            item.possible_causes.slice(0, 5).forEach((cause) => {
                const causeItem = document.createElement("li");
                causeItem.textContent = cause;
                causes.appendChild(causeItem);
            });
            code.appendChild(causes);
        }

        container.appendChild(code);
    });
}

function severityLabel(severity) {
    if (severity === "high") return "High";
    if (severity === "medium") return "Medium";
    if (severity === "low") return "Low";
    return tr("unknown", "Unknown");
}

function updateSafeModeUi() {
    const safeButton = byId("safe-mode-button");

    if (safeButton) {
        safeButton.classList.toggle("is-active", safeMode);
        safeButton.setAttribute("aria-pressed", String(safeMode));
        safeButton.innerText = safeMode ? tr("safe_mode_on", "SAFE Mode On") : tr("safe_mode_off", "SAFE Mode Off");
    }
    document.querySelectorAll("#clear-button, #clear-button-codes").forEach((button) => {
        button.disabled = safeMode;
    });

    setText("system-mode", safeMode ? tr("system_mode_safe", "SAFE") : tr("system_mode_service", "Service enabled"));

    lastSafeModeRendered = safeMode;
}

function updateFreezeUi() {
    const button = document.getElementById("freeze-button");
    const indicator = document.getElementById("freeze-indicator");

    button.classList.toggle("is-active", isFrozen);
    button.innerText = isFrozen ? tr("freeze_resume", "Resume Stream") : tr("freeze_pause", "Freeze Stream");
    indicator.innerText = isFrozen ? tr("freeze_frozen", "Live stream frozen for review") : tr("freeze_live", "Live stream active");
}

function toggleFreeze() {
    if (isFrozen) {
        isFrozen = false;
        frozenPayload = null;
    } else {
        const status = { connected: isConnected, safe_mode: safeMode };
        const rpmText = document.getElementById("rpm-value")?.innerText || "0";
        const speedText = document.getElementById("speed-value")?.innerText || "0";
        frozenPayload = {
            status,
            vehicle: {
                rpm: { value: rpmText },
                speed: { value: speedText }
            }
        };
        if (lastLivePayload) {
            frozenPayload = lastLivePayload;
            frozenPayload.vehicle = {
                ...(frozenPayload.vehicle || {}),
                rpm: { ...(frozenPayload.vehicle?.rpm || {}), value: `${rpmText} RPM` },
                speed: { ...(frozenPayload.vehicle?.speed || {}), value: `${speedText} km/h` }
            };
        }
        isFrozen = true;
    }

    updateFreezeUi();
}

async function toggleSafeMode() {
    safeMode = !safeMode;
    updateSafeModeUi();

    try {
        const response = await fetch("/api/safe-mode", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled: safeMode })
        });

        if (!response.ok) throw new Error(`Server gaf status ${response.status}`);

        const result = await response.json();
        safeMode = Boolean(result.safe_mode);
        updateSafeModeUi();
    } catch (error) {
        console.error(error);
        safeMode = true;
        updateSafeModeUi();
    }
}

async function reconnectObd() {
    const button = document.getElementById("reconnect-button");
    const resultElement = document.getElementById("port-result");

    button.disabled = true;
    button.classList.add("connecting");
        button.innerText = tr("reconnecting", "Reconnecting...");
    resultElement.innerText = tr("manual_reconnect_running", "Reconnecting to OBD adapter...");

    try {
        const response = await fetch("/api/reconnect", {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const result = await response.json();
        if (!response.ok || !result.success) throw new Error(result.message || `Server returned status ${response.status}`);

        vinRefreshPending = false;
        isFrozen = false;
        frozenPayload = null;
        updateFreezeUi();
    resultElement.innerText = result.message || tr("manual_reconnect_started", "Reconnect started.");
        fetchData();
    } catch (error) {
        console.error(error);
        resultElement.innerText = error.message || tr("manual_reconnect_failed", "Reconnect failed.");
        button.disabled = false;
        button.classList.remove("connecting");
        button.innerText = tr("retry_connection", "Retry Connection");
    }
}

async function fetchVehicleProfile(force = false) {
    if (vinRefreshPending && !force) return;

    vinRefreshPending = true;
    updateVehicleProfileView({ vin_status: "loading", vin_message: tr("vin_reading_vehicle", "Reading VIN from vehicle...") });

    try {
        const response = await fetch("/api/vehicle/refresh", {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const result = await response.json();
        updateVehicleProfileView(result.vehicle_profile || {});
        if (!response.ok || !result.success) throw new Error(result.message || `Server returned status ${response.status}`);
    } catch (error) {
        console.error(error);
        document.getElementById("vin-message").innerText = error.message || tr("vin_lookup_failed", "VIN lookup failed.");
    } finally {
        vinRefreshPending = false;
    }
}

async function savePlateLookup(event) {
    event.preventDefault();

    const plateInput = document.getElementById("plate-input");
    const resultElement = document.getElementById("plate-result");

    resultElement.innerText = tr("rdw_lookup_loading", "Looking up RDW vehicle data...");

    try {
        const response = await fetch("/api/vehicle/plate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ plate: plateInput.value.trim() })
        });
        const result = await response.json();
        updateVehicleProfileView(result.vehicle_profile || {});
        if (!response.ok || !result.success) throw new Error(result.message || `Server returned status ${response.status}`);
        saveVehicleLookupHistory({
            type: "plate",
            value: plateInput.value.trim().toUpperCase(),
            label: tr("history_type_plate", "Plate")
        });
    } catch (error) {
        console.error(error);
        resultElement.innerText = error.message || tr("rdw_lookup_failed", "RDW lookup failed.");
    }
}

async function saveManualVin(event) {
    event.preventDefault();

    if (vinRefreshPending) return;

    const vinInput = document.getElementById("manual-vin-input");
    const resultElement = document.getElementById("manual-vin-result");

    vinRefreshPending = true;
    resultElement.innerText = tr("vin_lookup_loading", "Looking up VIN...");
    updateVehicleProfileView({
        vin: vinInput.value.trim().toUpperCase(),
        vin_status: "loading",
        vin_message: tr("vin_processing", "Processing manual VIN...")
    });

    try {
        const response = await fetch("/api/vehicle/manual", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ vin: vinInput.value.trim() })
        });
        const result = await response.json();
        updateVehicleProfileView(result.vehicle_profile || {});
        if (!response.ok || !result.success) throw new Error(result.message || `Server returned status ${response.status}`);
        saveVehicleLookupHistory({
            type: "vin",
            value: vinInput.value.trim().toUpperCase(),
            label: tr("history_type_vin", "VIN")
        });
        resultElement.innerText = result.message || tr("vin_found", "VIN found.");
    } catch (error) {
        console.error(error);
        resultElement.innerText = error.message || tr("vin_lookup_failed", "VIN lookup failed.");
    } finally {
        vinRefreshPending = false;
        updateVehicleProfileView({});
    }
}

function clearManualVinInput() {
    const vinInput = document.getElementById("manual-vin-input");
    const resultElement = document.getElementById("manual-vin-result");

    if (vinRefreshPending || !vinInput) return;

    vinInput.value = "";
    if (resultElement) {
        resultElement.innerText = tr("vin_input_cleared", "VIN input cleared.");
    }
}

function loadVehicleLookupHistory() {
    try {
        const stored = window.localStorage.getItem(VEHICLE_LOOKUP_HISTORY_KEY);
        const items = stored ? JSON.parse(stored) : [];
        return Array.isArray(items) ? items : [];
    } catch {
        return [];
    }
}

function saveVehicleLookupHistory(entry) {
    const value = String(entry.value || "").trim();
    if (!value) return;

    const history = loadVehicleLookupHistory();
    const normalizedValue = value.toUpperCase();
    const existingIndex = history.findIndex((item) => item.type === entry.type && item.value === normalizedValue);
    if (existingIndex !== -1) {
        history.splice(existingIndex, 1);
    }

    history.unshift({
        type: entry.type,
        value: normalizedValue,
        label: entry.label,
        created_at: new Date().toISOString()
    });

    window.localStorage.setItem(VEHICLE_LOOKUP_HISTORY_KEY, JSON.stringify(history.slice(0, VEHICLE_LOOKUP_HISTORY_LIMIT)));
    renderVehicleLookupHistory();
}

function formatHistoryTimestamp(isoString) {
    try {
        const date = new Date(isoString);
        return date.toLocaleString();
    } catch {
        return String(isoString || "");
    }
}

function renderVehicleLookupHistory() {
    const historyElement = document.getElementById("vehicle-history");
    if (!historyElement) return;

    const historyItems = loadVehicleLookupHistory();
    historyElement.replaceChildren();

    if (!historyItems.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = tr("history_empty", "No lookup history yet.");
        historyElement.appendChild(empty);
        return;
    }

    historyItems.forEach((item) => {
        const row = document.createElement("div");
        row.className = "history-row";
        row.style.cursor = "pointer";
        row.innerHTML = `
            <div>
                <strong>${item.value}</strong>
                <p>${item.label}</p>
                <span>${formatHistoryTimestamp(item.created_at)}</span>
            </div>
        `;

        row.addEventListener("click", () => {
            if (item.type === "vin") {
                const vinInput = document.getElementById("manual-vin-input");
                if (vinInput) {
                    vinInput.value = item.value;
                    saveManualVin({ preventDefault: () => {} });
                }
                return;
            }

            const plateInput = document.getElementById("plate-input");
            if (plateInput) {
                plateInput.value = item.value;
                savePlateLookup({ preventDefault: () => {} });
            }
        });

        historyElement.appendChild(row);
    });
}

async function savePort(event) {
    event.preventDefault();

    const portInput = document.getElementById("port-input");
    const resultElement = document.getElementById("port-result");
    const port = portInput.value.trim();

    resultElement.innerText = tr("port_save_loading", "Saving COM port...");

    try {
        const response = await fetch("/api/config/port", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ port })
        });
        const result = await response.json();
        if (!response.ok || !result.success) throw new Error(result.message || `Server returned status ${response.status}`);

        portInput.value = result.obd_port || "";
        renderPortOptions(result.detected_ports || [], result.obd_port || "");
        resultElement.innerText = result.message || tr("port_saved", "COM port saved.");
        fetchData();
    } catch (error) {
        console.error(error);
        resultElement.innerText = error.message || tr("port_save_failed", "Could not save COM port.");
    }
}

async function toggleDemoMode() {
    const button = byId("demo-mode-button");
    if (button) {
        button.disabled = true;
    }

    try {
        const response = await fetch("/api/demo-mode", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled: !demoMode })
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || `Server returned status ${response.status}`);
        }

        demoMode = Boolean(result.demo_mode);
        updateDemoModeUi();
        await loadConfig();
        fetchData();
    } catch (error) {
        console.error(error);
    } finally {
        if (button) {
            button.disabled = false;
        }
    }
}

async function toggleLimitedMode() {
    const button = byId("limited-mode-button");
    if (button) {
        button.disabled = true;
    }

    limitedMode = !limitedMode;
    updateLimitedModeUi();

    try {
        const response = await fetch("/api/limited-mode", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enabled: limitedMode })
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || `Server returned status ${response.status}`);
        }

        limitedMode = Boolean(result.limited_mode);
        updateLimitedModeUi();
        fetchData();
    } catch (error) {
        console.error(error);
        limitedMode = !limitedMode;
        updateLimitedModeUi();
    } finally {
        if (button) {
            button.disabled = false;
        }
    }
}

async function setDemoPreset(preset) {
    if (demoPresetRequestPending) return;

    demoPresetRequestPending = true;
    updateDemoPresetUi();

    try {
        const response = await fetch("/api/demo-mode/preset", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ preset })
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error(result.message || `Server returned status ${response.status}`);
        }

        demoPreset = String(result.demo_preset || preset || "idle");
        storeDemoPresets(result.demo_presets || []);
        updateDemoModeUi();
        fetchData();
    } catch (error) {
        console.error(error);
    } finally {
        demoPresetRequestPending = false;
        updateDemoPresetUi();
    }
}

async function testConnection() {
    const button = byId("test-connection-button");
    const resultElement = byId("test-connection-result");
    const stepsContainer = byId("test-connection-steps");

    if (!button || !resultElement || !stepsContainer) return;

    button.disabled = true;
    button.innerText = tr("testing", "Testing...");
    resultElement.innerText = tr("connection_test_running", "Testing adapter and ECU connection...");
    stepsContainer.replaceChildren();

    try {
        const response = await fetch("/api/connection/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const result = await response.json();

        resultElement.innerText = result.phase || (result.success ? tr("connection_test_passed", "Connection test passed.") : tr("connection_test_failed", "Connection test failed."));

        const steps = result.steps || [];
        if (steps.length === 0) {
            const empty = document.createElement("div");
            empty.className = "empty";
            empty.textContent = tr("connection_test_empty", "No diagnostic steps returned.");
            stepsContainer.appendChild(empty);
        }

        steps.forEach((step, index) => {
            const row = document.createElement("div");
            row.className = `support-row ${step.ok ? "is-supported" : "is-unsupported"}`;
            row.style.animationDelay = `${Math.min(index * 18, 220)}ms`;
            row.innerHTML = `<div><strong>${step.name}</strong><p>${step.detail || ""}</p></div><span class="support-badge ${step.ok ? "status-good" : "status-warning"}">${step.ok ? "OK" : "Check"}</span>`;
            stepsContainer.appendChild(row);
        });
    } catch (error) {
        console.error(error);
        resultElement.innerText = tr("connection_test_failed", "Connection test failed.");
    } finally {
        button.disabled = false;
        button.innerText = tr("test_connection", "Test Connection");
    }
}

async function scanCodes() {
    if (codeScanPending) return;

    codeScanPending = true;
    updateDtcStatus({
        ...lastDtcStatus,
        scanning: true,
            message: tr("scanning_fault_codes", "Scanning fault codes...")
    });

    try {
        const response = await fetch("/api/codes/scan", {
            method: "POST",
            headers: { "Content-Type": "application/json" }
        });
        const result = await response.json();
        updateDtcStatus(result.dtc_status || {});
        updateCodes("stored-codes", result.dtc?.stored || []);
        updateCodes("pending-codes", result.dtc?.pending || []);
        updateCodes("permanent-codes", result.dtc?.permanent || []);
        updateHealth(result.health || {});
        updateFreezeFrame(result.freeze_frame || {});
        updateReadiness(result.readiness || {});
        updateReport(result.report || {});
        if (!response.ok || !result.success) {
            throw new Error(result.message || `Server returned status ${response.status}`);
        }
    } catch (error) {
        console.error(error);
        updateDtcStatus({
            ...lastDtcStatus,
            has_scan: false,
            scanning: false,
            message: error.message || tr("fault_code_scan_failed", "Fault code scan failed.")
        });
    } finally {
        codeScanPending = false;
        updateDtcStatus({});
    }
}

async function clearDTC() {
    const clearButton = this instanceof HTMLElement ? this : byId("clear-button");
    const resultTarget = clearButton?.dataset.resultTarget || "clear-result";
    const resultElement = byId(resultTarget);

    if (safeMode) {
        if (resultElement) {
            resultElement.innerText = tr("clear_codes_blocked", "SAFE Mode is on. Turn SAFE Mode off to clear fault codes.");
        }
        return;
    }

    const confirmed = await openConfirmDialog(
        tr("clear_codes_confirm_title", "Clear fault codes?"),
        tr("clear_codes_confirm_message", "Are you sure you want to clear all engine and ECU fault codes?")
    );
    if (!confirmed) {
        if (resultElement) {
        resultElement.innerText = tr("clear_cancelled", "Clear cancelled.");
        }
        return;
    }

    if (resultElement) {
    resultElement.innerText = tr("clear_sending", "Sending clear command...");
    }
    if (clearButton) {
        clearButton.disabled = true;
    }

    try {
        const response = await fetch("/api/clear", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ confirm: "YES" })
        });
        const result = await response.json();
        if (resultElement) {
        resultElement.innerText = result.message || tr("command_processed", "Command processed.");
        }
        updateDtcStatus({
            has_scan: lastDtcStatus.has_scan,
            scanning: false,
            last_scan: lastDtcStatus.last_scan || null,
            message: tr("clear_codes_sent_verify", "Clear command sent. Run a new scan to verify the ECU is clean.")
        });
        fetchData();
    } catch (error) {
        console.error(error);
        if (resultElement) {
        resultElement.innerText = tr("clear_command_failed", "Clear command failed. Check the connection.");
        }
    } finally {
        updateSafeModeUi();
    }
}

async function fetchSupportedSensors() {
    const supportedContainer = document.getElementById("supported-sensors");
    const unsupportedContainer = document.getElementById("unsupported-sensors");

    supportedContainer.innerHTML = `<p>${tr("supported_loading", "Loading supported sensors...")}</p>`;
    unsupportedContainer.innerHTML = `<p>${tr("unsupported_loading", "Loading unsupported sensors...")}</p>`;

    try {
        const response = await fetch("/api/supported");
        const result = await response.json();
        setText(
            "standard-obd-note",
            result.standard_obd_only
            ? tr("standard_obd_note", "Standard OBD only: engine and emission related ECU codes. ABS, airbag and body modules may require a brand-specific scanner.")
            : tr("enhanced_module_active", "Enhanced module support active.")
        );
        updatePidSupportSummary(result);
        renderSensorSupportList(supportedContainer, result.supported || [], true);
        renderSensorSupportList(unsupportedContainer, result.unsupported || [], false);
    } catch (error) {
        console.error(error);
        supportedContainer.innerHTML = `<p>${tr("supported_failed", "Could not load supported sensor list.")}</p>`;
        unsupportedContainer.innerHTML = `<p>${tr("unsupported_failed", "Could not load unsupported sensor list.")}</p>`;
    }
}

function renderSensorSupportList(container, items, supported) {
    container.replaceChildren();

    if (!items.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = supported ? tr("supported_empty", "No supported sensors detected yet.") : tr("unsupported_empty", "No unsupported sensor info yet.");
        container.appendChild(empty);
        return;
    }

    items.forEach((item, index) => {
        const row = document.createElement("div");
        row.className = `support-row ${supported ? "is-supported" : "is-unsupported"}`;
        row.style.animationDelay = `${Math.min(index * 18, 220)}ms`;

        const left = document.createElement("div");
        left.innerHTML = `<strong>${item.label}</strong><p>${item.command}</p>`;

        const badge = document.createElement("span");
        badge.className = `support-badge ${supported ? "status-good" : "status-warning"}`;
        badge.textContent = supported ? tr("available", "Available") : tr("not_supported", "Not supported");

        row.append(left, badge);
        container.appendChild(row);
    });
}

function openConfirmDialog(title, message) {
    const overlay = byId("confirm-overlay");
    const titleElement = byId("confirm-title");
    const messageElement = byId("confirm-message");
    const yesButton = byId("confirm-yes-button");
    const noButton = byId("confirm-no-button");

    if (!overlay || !titleElement || !messageElement || !yesButton || !noButton) {
        return Promise.resolve(window.confirm(message));
    }

    titleElement.innerText = title;
    messageElement.innerText = message;
    overlay.hidden = false;

    return new Promise((resolve) => {
        const cleanup = (result) => {
            overlay.hidden = true;
            yesButton.removeEventListener("click", handleYes);
            noButton.removeEventListener("click", handleNo);
            overlay.removeEventListener("click", handleBackdrop);
            resolve(result);
        };

        const handleYes = () => cleanup(true);
        const handleNo = () => cleanup(false);
        const handleBackdrop = (event) => {
            if (event.target === overlay) {
                cleanup(false);
            }
        };

        yesButton.addEventListener("click", handleYes);
        noButton.addEventListener("click", handleNo);
        overlay.addEventListener("click", handleBackdrop);
    });
}

async function fetchScanHistory() {
    const history = document.getElementById("scan-history");
    history.innerHTML = `<p>${tr("loading_saved_scans", "Loading saved scans...")}</p>`;

    try {
        const response = await fetch("/api/scans");
        const scans = await response.json();
        renderScanHistory(scans || []);
    } catch (error) {
        console.error(error);
        history.innerHTML = `<p>${tr("saved_scans_failed", "Could not load saved scan history.")}</p>`;
    }
}

function renderScanHistory(scans) {
    const history = document.getElementById("scan-history");
    history.replaceChildren();

    if (!scans.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = tr("no_scans_saved", "No scans saved yet.");
        history.appendChild(empty);
        return;
    }

    scans.forEach((scan, index) => {
        const row = document.createElement("div");
        row.className = "history-row";
        row.style.animationDelay = `${Math.min(index * 24, 260)}ms`;

        const meta = document.createElement("div");
        const scanStatus = scan.payload?.status || {};
        const connectionLabel = scanStatus.connected ? tr("history_connection_connected", "Connected") : tr("history_connection_offline", "Offline");
        meta.innerHTML = `<strong>${scan.label}</strong><p>${scan.created_at}</p><span>${scan.summary}</span><p>${connectionLabel} | ${scanStatus.protocol || "Unknown"} | ${scanStatus.current_port || tr("port_none_selected", "No COM port selected")}</p>`;

        const payload = scan.payload || {};
        const detail = document.createElement("div");
        detail.className = "history-health";
        detail.innerHTML = `<strong>${displayValue(payload.health?.score, "--")}</strong><p>${tr("history_health_score", "Health score")}</p>`;

        row.append(meta, detail);
        history.appendChild(row);
    });
}

async function saveScanToDatabase() {
    const resultElement = document.getElementById("save-scan-result") || document.getElementById("report-action-result");
    await saveScanSnapshotToResult(resultElement, tr("save_scan_label", "Manual dashboard snapshot"));
}

async function saveReportSnapshot() {
    const resultElement = document.getElementById("report-action-result");
    await saveScanSnapshotToResult(resultElement, tr("report_snapshot_label", "Manual report snapshot"));
}

async function saveScanSnapshotToResult(resultElement, label) {
    if (!resultElement) return;
    resultElement.innerText = tr("save_scan_saving", "Saving current scan to database...");

    try {
        const response = await fetch("/api/scans/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ label })
        });
        const result = await response.json();
        if (!response.ok || !result.success) throw new Error(result.message || `Server returned status ${response.status}`);

        resultElement.innerText = tr("scan_saved_at", "{label} saved at {time}.", { label: result.scan.label, time: result.scan.created_at });
        renderScanHistory(result.scans || []);
    } catch (error) {
        console.error(error);
        resultElement.innerText = error.message || tr("save_scan_failed", "Could not save the scan.");
    }
}

function setLanguageCookie(languageCode) {
    document.cookie = `obd_lang=${encodeURIComponent(languageCode)}; path=/; max-age=31536000; SameSite=Lax`;
}

function initLanguageSwitcher() {
    document.querySelectorAll("[data-language-code]").forEach((button) => {
        button.addEventListener("click", () => {
            const nextLanguage = String(button.dataset.languageCode || "en").toLowerCase();
            if (nextLanguage === String(window.APP_LANG || "en").toLowerCase()) {
                return;
            }
            setLanguageCookie(nextLanguage);
            window.location.reload();
        });
    });
}

document.getElementById("safe-mode-button").addEventListener("click", toggleSafeMode);
document.getElementById("freeze-button").addEventListener("click", toggleFreeze);
document.getElementById("clear-button").addEventListener("click", clearDTC);
document.getElementById("clear-button-codes").addEventListener("click", clearDTC);
document.getElementById("port-form").addEventListener("submit", savePort);
document.getElementById("port-input").addEventListener("change", savePort);
document.getElementById("reconnect-button").addEventListener("click", reconnectObd);
document.getElementById("refresh-vin-button").addEventListener("click", () => fetchVehicleProfile(true));
document.getElementById("manual-vin-form").addEventListener("submit", saveManualVin);
document.getElementById("clear-vin-button").addEventListener("click", clearManualVinInput);
document.getElementById("plate-form").addEventListener("submit", savePlateLookup);
document.getElementById("scan-codes-button").addEventListener("click", scanCodes);
document.getElementById("refresh-supported-button").addEventListener("click", fetchSupportedSensors);
document.getElementById("save-scan-button").addEventListener("click", saveScanToDatabase);
const reportExportButton = byId("report-export-button");
if (reportExportButton) {
    reportExportButton.addEventListener("click", exportScanReport);
}
const reportSaveSnapshotButton = byId("report-save-snapshot-button");
if (reportSaveSnapshotButton) {
    reportSaveSnapshotButton.addEventListener("click", saveReportSnapshot);
}
const simpleModeButton = byId("simple-mode-button");
if (simpleModeButton) {
    simpleModeButton.addEventListener("click", toggleSimpleMode);
}
const demoModeButton = byId("demo-mode-button");
if (demoModeButton) {
    demoModeButton.addEventListener("click", toggleDemoMode);
}
const limitedModeButton = byId("limited-mode-button");
if (limitedModeButton) {
    limitedModeButton.addEventListener("click", toggleLimitedMode);
}
document.querySelectorAll("[data-demo-preset]").forEach((button) => {
    button.addEventListener("click", () => {
        setDemoPreset(button.dataset.demoPreset || "idle");
    });
});
const testConnectionButton = byId("test-connection-button");
if (testConnectionButton) {
    testConnectionButton.addEventListener("click", testConnection);
}

initLanguageSwitcher();
initPortDropdown();
initNavigation();
initDashboardLauncher();
initPageFromHash();
updateFreezeUi();
requestAnimationFrame(renderGauges);
scheduleGaugePoll();
armStartupFallback();
loadConfig();
schedulePortPoll();
fetchSupportedSensors();
fetchScanHistory();
renderVehicleLookupHistory();
fetchData();
window.addEventListener("load", () => {
    positionGaugeTicks();
    window.requestAnimationFrame(positionGaugeTicks);
});
window.addEventListener("resize", positionGaugeTicks);
