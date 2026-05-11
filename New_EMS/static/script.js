const plantSelect = document.getElementById("plantSelect");
const meterSelect = document.getElementById("meterSelect");

const cardsContainer =
    document.getElementById("cardsContainer");

const dashboardTitle =
    document.getElementById("dashboardTitle");

const navbar = document.querySelector(".navbar");

const themeToggle = document.getElementById("themeToggle");
const themeIcon = document.getElementById("themeIcon");
const shiftSelect = document.getElementById("shiftSelect");
const fromDateTime = document.getElementById("fromDateTime");
const toDateTime = document.getElementById("toDateTime");
const submitFiltersBtn = document.getElementById("submitFiltersBtn");
const shiftAnalysisToggle = document.getElementById("shiftAnalysisToggle");
const barGraphToggle = document.getElementById("barGraphToggle");
const shiftDisabledNote = document.getElementById("shiftDisabledNote");
const moonIcon = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>';
const sunIcon = '<circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="4.22" x2="19.78" y2="5.64"></line>';

const plantThemes = {
    "Automotive": {
        primaryColor: "#3b82f6", // Blue
        darkBgGradient: "linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #1e293b 100%)",
        lightBgGradient: "linear-gradient(135deg, #f1f5f9 0%, #dbeafe 50%, #e0e7ff 100%)"
    },
    "Lamination": {
        primaryColor: "#06b6d4", // Cyan
        darkBgGradient: "linear-gradient(135deg, #0f172a 0%, #112a2a 50%, #1e293b 100%)",
        lightBgGradient: "linear-gradient(135deg, #f1f5f9 0%, #cffafe 50%, #e0e7ff 100%)"
    },
    "Machining": {
        primaryColor: "#8b5cf6", // Purple
        darkBgGradient: "linear-gradient(135deg, #0f172a 0%, #221c35 50%, #1e293b 100%)",
        lightBgGradient: "linear-gradient(135deg, #f1f5f9 0%, #f5f3ff 50%, #e0e7ff 100%)"
    },
    "IG Plant": {
        primaryColor: "#10b981", // Green
        darkBgGradient: "linear-gradient(135deg, #0f172a 0%, #0d221c 50%, #1e293b 100%)",
        lightBgGradient: "linear-gradient(135deg, #f1f5f9 0%, #d1fae5 50%, #e0e7ff 100%)"
    },
    "Foundry": {
        primaryColor: "#f59e0b", // Amber
        darkBgGradient: "linear-gradient(135deg, #0f172a 0%, #2b2211 50%, #1e293b 100%)",
        lightBgGradient: "linear-gradient(135deg, #f1f5f9 0%, #fef3c7 50%, #e0e7ff 100%)"
    }
};
let meterMetaById = {};
let liveEventSource = null;
let pendingStreamRefreshTimer = null;
let streamRefreshInProgress = false;

function hexToRgba(hex, alpha) {
    const safeHex = (hex || "").replace("#", "");
    if (safeHex.length !== 6) return `rgba(47, 124, 248, ${alpha})`;
    const r = parseInt(safeHex.substring(0, 2), 16);
    const g = parseInt(safeHex.substring(2, 4), 16);
    const b = parseInt(safeHex.substring(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function applyThemeState() {
    const plant = plantSelect.value;
    const isLightMode = document.body.classList.contains("light-mode");
    const plantTheme = plantThemes[plant];

    let activeGradient = isLightMode
        ? "linear-gradient(135deg, #eef2ff 0%, #dbeafe 45%, #e0e7ff 100%)"
        : "linear-gradient(135deg, #0f172a 0%, #1e1b4b 45%, #1e293b 100%)";

    if (plantTheme) {
        plantSelect.style.color = plantTheme.primaryColor;
        dashboardTitle.style.color = plantTheme.primaryColor;
        dashboardTitle.style.setProperty("--title-glow", `0 0 15px ${plantTheme.primaryColor}88`);
        navbar.style.setProperty("--nav-border-bottom-color", plantTheme.primaryColor);
        activeGradient = isLightMode ? plantTheme.lightBgGradient : plantTheme.darkBgGradient;

        document.body.style.setProperty("--accent-1", hexToRgba(plantTheme.primaryColor, isLightMode ? 0.13 : 0.25));
        document.body.style.setProperty("--accent-2", hexToRgba(plantTheme.primaryColor, isLightMode ? 0.1 : 0.2));
    } else {
        plantSelect.style.color = "inherit";
        dashboardTitle.style.color = "var(--text-main)";
        dashboardTitle.style.removeProperty("--title-glow");
        navbar.style.setProperty("--nav-border-bottom-color", "transparent");
    }

    document.body.style.setProperty("--dynamic-bg-gradient", activeGradient);
}

// ================= TIME =================

const iconMap = {
    "Voltage": '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"></path>', // Bolt
    "Current": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>', // Activity
    "Frequency": '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7zm10-3a3 3 0 100 6 3 3 0 000-6z"></path>', // Wave
    "PF": '<path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10zm0-2a8 8 0 100-16 8 8 0 000 16z"></path><path d="M12 8v4l3 3"></path>', // Gauge
    "KW": '<path d="M18.36 6.64a9 9 0 11-12.73 0M12 2v10"></path>', // Power
    "KVA": '<path d="M23 6l-9.5 9.5-5-5L1 18"></path>', // Trending Up
    "Line Voltage": '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"></path>',
    "Line-to-Line Voltage": '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"></path>',
    "Average Voltage": '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"></path>',
    "Voltage Unbalance": '<path d="M3 12h18M12 3v18"></path>',
    "Line Current": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>',
    "Phase-wise Current L1": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>',
    "Phase-wise Current L2": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>',
    "Phase-wise Current L3": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>',
    "Average Current": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>',
    "Neutral Line Current": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>',
    "Active Power kW L1": '<path d="M18.36 6.64a9 9 0 11-12.73 0M12 2v10"></path>',
    "Active Power kW L2": '<path d="M18.36 6.64a9 9 0 11-12.73 0M12 2v10"></path>',
    "Active Power kW L3": '<path d="M18.36 6.64a9 9 0 11-12.73 0M12 2v10"></path>',
    "Cumulative kW": '<path d="M18.36 6.64a9 9 0 11-12.73 0M12 2v10"></path>',
    "Apparent Power kVA L1": '<path d="M23 6l-9.5 9.5-5-5L1 18"></path>',
    "Apparent Power kVA L2": '<path d="M23 6l-9.5 9.5-5-5L1 18"></path>',
    "Apparent Power kVA L3": '<path d="M23 6l-9.5 9.5-5-5L1 18"></path>',
    "Cumulative kVA": '<path d="M23 6l-9.5 9.5-5-5L1 18"></path>',
    "Power Factor": '<path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10zm0-2a8 8 0 100-16 8 8 0 000 16z"></path><path d="M12 8v4l3 3"></path>',
    "Frequency": '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7zm10-3a3 3 0 100 6 3 3 0 000-6z"></path>',
    "kVA Maximum Demand": '<path d="M23 6l-9.5 9.5-5-5L1 18"></path>',
    "Energy Consumption": '<path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"></path>' // Database/Storage
};

/**
 * Helper to generate the HTML for a single parameter card
 */
function getCardHTML(label, value, unit, status, isEnergy = false, meterName = "", overrides = {}) {
    const icon = isEnergy ? iconMap["Energy Consumption"] : (iconMap[label] || iconMap["Voltage"]);
    const cardClass = status !== 'OK' ? 'card-container error-status' : 'card-container';
    const btnText = overrides.btnText || (status === 'OK' ? (isEnergy ? 'Operational' : 'Device Online') : 'Check Device');
    const normalizedMeterName = meterName || "Meter";
    const titleLabel = overrides.titleLabel || (isEnergy ? `${normalizedMeterName} - Operational` : `${normalizedMeterName} - Live Data`);
    const displayTitle = overrides.displayTitle || (isEnergy ? 'Energy Consumption' : label);
    const description = overrides.description || (isEnergy ? 'Cumulative meter reading' : 'Real-time monitoring active');

    return `
        <div class="${cardClass}">
            <div class="title-card">
                <p>${titleLabel}</p>
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    ${icon}
                </svg>
            </div>
            <div class="card-content">
                <p class="title">${displayTitle}</p>
                <p class="plain">
                    <span>${value ?? 0}</span>
                    <span>${unit}</span>
                </p>
                <p class="description">${description}</p>
                <button class="card-btn">${btnText}</button>
            </div>
        </div>`;
}

function updateTime(){
    const now = new Date();
    const shiftName = getShiftName(now);
    document.getElementById("currentTime").innerText = `${now.toLocaleString()} | ${shiftName}`;
}

setInterval(updateTime,1000);

updateTime();

function getShiftName(dt) {
    const hour = dt.getHours();
    if (hour >= 6 && hour < 14) return "Shift A";
    if (hour >= 14 && hour < 22) return "Shift B";
    return "Shift C";
}

function toLocalInputValue(dt) {
    const pad = n => String(n).padStart(2, "0");
    return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}T${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
}

function setDefaultDateRange() {
    const now = new Date();
    const y = new Date(now);
    y.setDate(now.getDate() - 1);
    const start = new Date(y.getFullYear(), y.getMonth(), y.getDate(), 0, 0, 0);
    const end = new Date(y.getFullYear(), y.getMonth(), y.getDate(), 23, 59, 0);
    fromDateTime.value = toLocalInputValue(start);
    toDateTime.value = toLocalInputValue(end);
}

function updateInsightCardsMeta(_extra = {}) {}

function closeLiveStream() {
    if (liveEventSource) {
        liveEventSource.close();
        liveEventSource = null;
    }
}

function scheduleRefreshFromStream() {
    if (pendingStreamRefreshTimer) return;
    pendingStreamRefreshTimer = setTimeout(async () => {
        pendingStreamRefreshTimer = null;
        if (streamRefreshInProgress) return;
        streamRefreshInProgress = true;
        try {
            if (!plantSelect.value || !meterSelect.value) return;
            if (shiftAnalysisToggle.checked && !shiftSelect.disabled) {
                await loadData();
            } else {
                await loadBaseCardsOnMeterSelection();
            }
        } catch (_e) {
            // no-op: stream should continue even if one refresh fails
        } finally {
            streamRefreshInProgress = false;
        }
    }, 300);
}

function setupLiveStream() {
    closeLiveStream();
    const plant = plantSelect.value;
    const meter = meterSelect.value;
    if (!plant || !meter) return;

    const streamUrl = `/stream_latest?plant=${encodeURIComponent(plant)}&meter=${encodeURIComponent(meter)}`;
    liveEventSource = new EventSource(streamUrl);

    liveEventSource.addEventListener("latest", () => {
        scheduleRefreshFromStream();
    });

    liveEventSource.addEventListener("error", () => {
        // Browser auto-reconnects EventSource by default.
    });
}

function setShiftControlsEnabled(enabled) {
    shiftSelect.disabled = !enabled;
    fromDateTime.disabled = !enabled;
    toDateTime.disabled = !enabled;
    submitFiltersBtn.disabled = !enabled;
    shiftSelect.closest(".select-card")?.classList.toggle("disabled-control", !enabled);
    fromDateTime.closest(".select-card")?.classList.toggle("disabled-control", !enabled);
    toDateTime.closest(".select-card")?.classList.toggle("disabled-control", !enabled);
    submitFiltersBtn.classList.toggle("disabled-control", !enabled);
}

function syncShiftUiForMeter() {
    shiftAnalysisToggle.disabled = false;
    setShiftControlsEnabled(shiftAnalysisToggle.checked);
    shiftDisabledNote.style.display = "none";
}

// ================= LOAD PLANTS =================

async function loadPlants(){

    const res = await fetch("/plants");

    const plants = await res.json();

    plants.forEach(p=>{

        const option = document.createElement("option");
        option.value = p;

        const theme = plantThemes[p];
        if (theme) {
            option.textContent = `● ${p}`;
            option.style.color = theme.primaryColor;
        } else {
            option.textContent = p;
        }

        plantSelect.appendChild(option);
    });
}

// ================= LOAD METERS =================

async function loadMeters(plant){

    meterSelect.innerHTML =
    `<option value="">Select Meter</option>`;
    meterMetaById = {};

    const res =
    await fetch(`/meters?plant=${plant}`);

    const meters = await res.json();

    meters.forEach(m=>{

        const option = document.createElement("option");

        option.value = m.id;
        option.textContent = m.name;
        meterMetaById[m.id] = m;

        meterSelect.appendChild(option);
    });

    // Add "All Devices" option
    const allOption = document.createElement("option");
    allOption.value = "all";
    allOption.textContent = "All Devices (Excluding Main Incomer)";
    meterSelect.appendChild(allOption);
}

// ================= BAR CHART HELPER =================

function getBarChartHTML(title, dataPoints, isFullWidth = false) {
    if (!dataPoints || dataPoints.length === 0) return `<div style="color: var(--text-sub); padding: 20px;">No bar data available.</div>`;
    
    const maxVal = Math.max(...dataPoints.map(b => b.value), 0.01);
    
    let rowsHtml = dataPoints.map(b => {
        const percent = (b.value / maxVal) * 100;
        return `
        <div class="fallback-chart-row">
            <div class="fallback-chart-value">${b.value} ${b.unit || ''}</div>
            <div class="fallback-chart-track">
                <div class="fallback-chart-fill" style="height: ${percent}%;"></div>
            </div>
            <div class="fallback-chart-label">${b.label}</div>
        </div>`;
    }).join('');

    const yAxisHtml = `
    <div style="display: flex; flex-direction: column; justify-content: space-between; height: 180px; margin-bottom: 26px; padding-right: 8px; font-size: 11px; color: var(--text-sub); text-align: right;">
        <span>${maxVal >= 10 ? Math.round(maxVal) : maxVal.toFixed(1)}</span>
        <span>${maxVal >= 10 ? Math.round(maxVal * 0.75) : (maxVal * 0.75).toFixed(1)}</span>
        <span>${maxVal >= 10 ? Math.round(maxVal * 0.5) : (maxVal * 0.5).toFixed(1)}</span>
        <span>${maxVal >= 10 ? Math.round(maxVal * 0.25) : (maxVal * 0.25).toFixed(1)}</span>
        <span>0</span>
    </div>`;

    const containerStyle = isFullWidth ? 'style="grid-column: 1 / -1; width: 100%;"' : '';

    return `
    <div class="graph-container" ${containerStyle}>
        <h4 class="graph-title">${title}</h4>
        <div style="display: flex; align-items: flex-end; width: 100%; overflow-x: auto;">
            ${yAxisHtml}
            <div class="fallback-chart" style="flex: 1; margin-top: 0; min-height: 240px; border-left: 2px solid rgba(148, 163, 184, 0.5); border-bottom: 2px solid rgba(148, 163, 184, 0.5);">
                ${rowsHtml}
            </div>
        </div>
    </div>`;
}

// ================= CREATE CARDS =================

function createCards(data){

    cardsContainer.innerHTML = "";
    const selectedMeterName = meterSelect.options[meterSelect.selectedIndex]?.text || "Meter";

    // Add timestamp info
    const timeInfo = document.createElement("div");
    timeInfo.style.gridColumn = "1 / -1";
    timeInfo.className = "last-updated-info";
    timeInfo.innerHTML = `<p>Last Updated: ${data.timestamp}</p>`;
    cardsContainer.appendChild(timeInfo);

    // Incomer meter
    if(data.meter_type === "incomer"){

        const params = [
            ["Line Voltage", data.line_voltage ?? data.volt, "V"],
            ["Line-to-Line Voltage", data.line_to_line_voltage ?? data.volt, "V"],
            ["Average Voltage", data.avg_voltage ?? data.volt, "V"],
            ["Voltage Unbalance", data.voltage_unbalance, "%"],
            ["Line Current", data.line_current ?? data.curr, "A"],
            ["Phase-wise Current L1", data.current_l1, "A"],
            ["Phase-wise Current L2", data.current_l2, "A"],
            ["Phase-wise Current L3", data.current_l3, "A"],
            ["Average Current", data.avg_current ?? data.curr, "A"],
            ["Neutral Line Current", data.neutral_line_current, "A"],
            ["Active Power kW L1", data.kw_l1, "kW"],
            ["Active Power kW L2", data.kw_l2, "kW"],
            ["Active Power kW L3", data.kw_l3, "kW"],
            ["Cumulative kW", data.kw_total ?? data.kw, "kW"],
            ["Apparent Power kVA L1", data.kva_l1, "kVA"],
            ["Apparent Power kVA L2", data.kva_l2, "kVA"],
            ["Apparent Power kVA L3", data.kva_l3, "kVA"],
            ["Cumulative kVA", data.kva_total ?? data.kva, "kVA"],
            ["Power Factor", data.pf, ""],
            ["Frequency", data.freq, "Hz"],
            ["kVA Maximum Demand", data.kva_max_demand, "kVA"]
        ];

        if (barGraphToggle.checked) {
            params.forEach(p => {
                cardsContainer.insertAdjacentHTML('beforeend', getBarChartHTML(p[0], [{label: "Current", value: p[1] ?? 0, unit: p[2]}]));
            });
        } else {
            params.forEach(p=>{
                cardsContainer.insertAdjacentHTML('beforeend', getCardHTML(p[0], p[1], p[2], data.status, false, selectedMeterName));
            });
        }
    }

    // Submeter KWH (fallback live card)
    if(data.meter_type === "submeter"){
        if (barGraphToggle.checked) {
            const dataPoints = [{label: "Current Energy", value: data.kwh ?? 0, unit: "kWh"}];
            cardsContainer.insertAdjacentHTML('beforeend', getBarChartHTML("Energy Consumption", dataPoints));
        } else {
            cardsContainer.insertAdjacentHTML('beforeend', getCardHTML("Energy", data.kwh, "kWh", data.status, true, selectedMeterName));
        }
    }
}

function renderEnergySummaryCard(summary) {
    const meterName = summary.meter_name || "Meter";
    const startKwh = summary.range_start_kwh ?? 0;
    const endKwh = summary.range_end_kwh ?? 0;
    const selectedTotal = summary.selected_total_kwh ?? 0;
    const selectedShift = summary.selected_shift || shiftSelect.value || "all";
    const valueUnit = summary.value_unit || "kWh";
    const metricName = summary.metric_name || "Energy Consumption";
    const rangeLabel = `${summary.from_dt || "-"} to ${summary.to_dt || "-"}`;

    cardsContainer.innerHTML = "";
    if (barGraphToggle.checked && summary.bars && summary.bars.length > 0) {
        const dataPoints = summary.bars.map(b => ({
            label: b.label,
            value: b.consumption,
            unit: valueUnit
        }));
        const title = `${metricName} - ${summary.selected_shift === 'all' ? 'All Shifts' : summary.selected_shift}`;
        cardsContainer.insertAdjacentHTML('beforeend', getBarChartHTML(title, dataPoints, true));
    } else {
        cardsContainer.insertAdjacentHTML("beforeend", getCardHTML("Selected Range Consumption", selectedTotal, valueUnit, "OK", true, meterName, {
            description: `Matches graph total | ${rangeLabel}`
        }));
        cardsContainer.insertAdjacentHTML("beforeend", getCardHTML("Shift Start", startKwh, valueUnit, "OK", false, meterName, {
            btnText: "Operational",
            description: `Range: ${rangeLabel}`
        }));
        cardsContainer.insertAdjacentHTML("beforeend", getCardHTML("Shift End", endKwh, valueUnit, "OK", false, meterName, {
            btnText: "Operational",
            description: `Range: ${rangeLabel}`
        }));
    }
}

async function loadEnergySummary(plant, meter) {
    const from_dt = fromDateTime.value;
    const to_dt = toDateTime.value;
    const shift = shiftSelect.value || "all";
    const res = await fetch(`/energy_summary?plant=${encodeURIComponent(plant)}&meter=${encodeURIComponent(meter)}&mode=shiftwise&shift=${encodeURIComponent(shift)}&from_dt=${encodeURIComponent(from_dt)}&to_dt=${encodeURIComponent(to_dt)}`);
    if (!res.ok) {
        const errText = await res.text();
        return { error: `Energy summary failed (${res.status}).`, details: errText.slice(0, 180) };
    }
    return res.json();
}

async function loadIncomerShiftSummary(plant, meter) {
    const from_dt = fromDateTime.value;
    const to_dt = toDateTime.value;
    const shift = shiftSelect.value || "all";
    const res = await fetch(`/incomer_shift_summary?plant=${encodeURIComponent(plant)}&meter=${encodeURIComponent(meter)}&shift=${encodeURIComponent(shift)}&from_dt=${encodeURIComponent(from_dt)}&to_dt=${encodeURIComponent(to_dt)}`);
    if (!res.ok) {
        const errText = await res.text();
        return { error: `Incomer summary failed (${res.status}).`, details: errText.slice(0, 180) };
    }
    return res.json();
}

function renderIncomerShiftGraphs(summary) {
    cardsContainer.innerHTML = "";
    const rangeLabel = `${summary.from_dt || "-"} to ${summary.to_dt || "-"}`;
    cardsContainer.insertAdjacentHTML(
        "beforeend",
        `<div style="grid-column:1 / -1; color: var(--text-sub); font-size: 13px; margin: 0 0 8px 4px;">
            Shift: ${summary.selected_shift === "all" ? "All Shifts" : summary.selected_shift} | Range: ${rangeLabel}
        </div>`
    );

    if (!summary.series || summary.series.length === 0) {
        cardsContainer.insertAdjacentHTML("beforeend", `<div style="color: var(--text-sub); padding: 20px;">No incomer range data available for the selected shift/date range.</div>`);
        return;
    }

    summary.series.forEach(s => {
        const points = (s.bars || []).map(b => ({
            label: b.label,
            value: b.value ?? 0,
            unit: s.unit || ""
        }));
        cardsContainer.insertAdjacentHTML("beforeend", getBarChartHTML(s.label, points));
    });
}

// ================= CREATE CARDS FOR ALL =================

function createCardsForAll(dataArray){

    cardsContainer.innerHTML = "";

    dataArray.forEach(d => {

        const meterDiv = document.createElement("div");

        meterDiv.className = "meter-section";
        
        // Create a container for the cards within this section to keep them organized
        const cardGrid = document.createElement("div");
        cardGrid.className = "cards"; // Reuse the grid styling

        meterDiv.innerHTML = `
            <h3 class="meter-section-title">${d.meter_name}</h3>
            <p class="last-updated-info">Last Updated: ${d.timestamp}</p>
        `;

        // Incomer meter
        if(d.meter_type === "incomer"){

            const params = [
                ["Line Voltage", d.line_voltage ?? d.volt, "V"],
                ["Line-to-Line Voltage", d.line_to_line_voltage ?? d.volt, "V"],
                ["Average Voltage", d.avg_voltage ?? d.volt, "V"],
                ["Voltage Unbalance", d.voltage_unbalance, "%"],
                ["Line Current", d.line_current ?? d.curr, "A"],
                ["Phase-wise Current L1", d.current_l1, "A"],
                ["Phase-wise Current L2", d.current_l2, "A"],
                ["Phase-wise Current L3", d.current_l3, "A"],
                ["Average Current", d.avg_current ?? d.curr, "A"],
                ["Neutral Line Current", d.neutral_line_current, "A"],
                ["Active Power kW L1", d.kw_l1, "kW"],
                ["Active Power kW L2", d.kw_l2, "kW"],
                ["Active Power kW L3", d.kw_l3, "kW"],
                ["Cumulative kW", d.kw_total ?? d.kw, "kW"],
                ["Apparent Power kVA L1", d.kva_l1, "kVA"],
                ["Apparent Power kVA L2", d.kva_l2, "kVA"],
                ["Apparent Power kVA L3", d.kva_l3, "kVA"],
                ["Cumulative kVA", d.kva_total ?? d.kva, "kVA"],
                ["Power Factor", d.pf, ""],
                ["Frequency", d.freq, "Hz"],
                ["kVA Maximum Demand", d.kva_max_demand, "kVA"]
            ];

            if (barGraphToggle.checked) {
                params.forEach(p => {
                    cardGrid.insertAdjacentHTML('beforeend', getBarChartHTML(p[0], [{label: "Current", value: p[1] ?? 0, unit: p[2]}]));
                });
            } else {
                params.forEach(p => {
                    cardGrid.insertAdjacentHTML('beforeend', getCardHTML(p[0], p[1], p[2], d.status, false, d.meter_name));
                });
            }
        }

        // Submeter KWH
        if(d.meter_type === "submeter"){
            if (barGraphToggle.checked) {
                const dataPoints = [{label: "Current Energy", value: d.kwh ?? 0, unit: "kWh"}];
                cardGrid.insertAdjacentHTML('beforeend', getBarChartHTML("Energy Consumption", dataPoints));
            } else {
                cardGrid.insertAdjacentHTML('beforeend', getCardHTML("Energy", d.kwh, "kWh", d.status, true, d.meter_name));
            }
        }

        meterDiv.appendChild(cardGrid);
        cardsContainer.appendChild(meterDiv);
    });
}

// ================= LOAD DATA =================

async function loadData(){
    if (shiftSelect.disabled) return;

    const plant = plantSelect.value;
    const meter = meterSelect.value;
    const shift = shiftSelect.value;

    // Show data only after required selections.
    if(!plant || !meter || !shift){
        cardsContainer.innerHTML = "";
        updateInsightCardsMeta({ barCount: 0 });
        return;
    }

    const fromValue = fromDateTime.value;
    const toValue = toDateTime.value;
    if (!fromValue || !toValue) {
        cardsContainer.innerHTML = `<div style="color: var(--text-sub); padding: 20px;">Please select both From and To date-time, then click Submit.</div>`;
        updateInsightCardsMeta({ barCount: 0 });
        return;
    }
    const fromTs = new Date(fromValue).getTime();
    const toTs = new Date(toValue).getTime();
    if (Number.isNaN(fromTs) || Number.isNaN(toTs) || toTs <= fromTs) {
        cardsContainer.innerHTML = `<div style="color: var(--text-sub); padding: 20px;">Invalid range: To date-time must be greater than From date-time.</div>`;
        updateInsightCardsMeta({ barCount: 0 });
        return;
    }

    dashboardTitle.innerText = `${plant} Dashboard`;
    applyThemeState();

    document.getElementById("liveStatus").style.display = "flex";

    if(meter === "all"){
        const resMeters = await fetch(`/meters?plant=${encodeURIComponent(plant)}`);
        const allMeters = await resMeters.json();
        const submeters = allMeters.filter(m => m.type === "submeter");
        const summaries = await Promise.all(submeters.map(m => loadEnergySummary(plant, m.id)));
        const validSummaries = summaries.filter(s => !s.error);
        createSummaryCardsForAll(validSummaries);
        updateInsightCardsMeta({ barCount: 0 });

    } else {
        const selectedMeta = meterMetaById[meter];
        if (selectedMeta && selectedMeta.type === "incomer" && barGraphToggle.checked) {
            const incomerSummary = await loadIncomerShiftSummary(plant, meter);
            if (incomerSummary.error) {
                cardsContainer.innerHTML = `<div style="color: var(--text-sub); padding: 20px;">${incomerSummary.error}</div>`;
                return;
            }
            renderIncomerShiftGraphs(incomerSummary);
            updateInsightCardsMeta({ barCount: (incomerSummary.series || []).length });
            return;
        }
        if (selectedMeta && (selectedMeta.type === "submeter" || selectedMeta.type === "incomer")) {
            const summary = await loadEnergySummary(plant, meter);
            if (summary.error) {
                cardsContainer.innerHTML = `<div style="color: var(--text-sub); padding: 20px;">${summary.error}</div>`;
                return;
            }
            renderEnergySummaryCard(summary);
            updateInsightCardsMeta({ barCount: (summary.bars || []).length });
            return;
        }

        const res = await fetch(`/latest?plant=${plant}&meter=${meter}`);

        const data = await res.json();

        if(data.length > 0){
            createCards(data[0]);
            updateInsightCardsMeta({ barCount: 0 });
        } else {
            cardsContainer.innerHTML = 
                `<div style="color: var(--text-sub); padding: 20px;">No data recorded yet for this meter.</div>`;
            updateInsightCardsMeta({ barCount: 0 });
        }
    }
}

async function loadBaseCardsOnMeterSelection() {
    const plant = plantSelect.value;
    const meter = meterSelect.value;
    if (!plant || !meter) {
        cardsContainer.innerHTML = "";
        return;
    }

    dashboardTitle.innerText = `${plant} Dashboard`;
    applyThemeState();
    document.getElementById("liveStatus").style.display = "flex";

    if (meter === "all") {
        const res = await fetch(`/latest?plant=${plant}&meter=all`);
        const allData = await res.json();
        const filteredData = allData.filter(d => d.meter_name !== "Main Incomer");
        createCardsForAll(filteredData);
        return;
    }

    const res = await fetch(`/latest?plant=${plant}&meter=${meter}`);
    const data = await res.json();
    if (data.length > 0) {
        if (data[0].meter_type === "submeter") {
            const meterName = meterSelect.options[meterSelect.selectedIndex]?.text || "Meter";
            cardsContainer.innerHTML = "";
            const yesterdayRes = await fetch(`/energy_summary?plant=${encodeURIComponent(plant)}&meter=${encodeURIComponent(meter)}&mode=shiftwise&shift=all`);
            const yesterdaySummary = await yesterdayRes.json();
            const yVal = yesterdaySummary.yesterday_total_kwh ?? data[0].kwh ?? 0;
            const baseDateRaw = (yesterdaySummary.from_dt || "").slice(0, 10);
            let baseDate = "-";
            if (baseDateRaw) {
                const d = new Date(`${baseDateRaw}T00:00:00`);
                if (!Number.isNaN(d.getTime())) {
                    baseDate = d.toLocaleDateString("en-GB", {
                        day: "2-digit",
                        month: "short",
                        year: "numeric"
                    });
                }
            }
            cardsContainer.insertAdjacentHTML(
                "beforeend",
                `<div style="grid-column:1 / -1; color: var(--text-sub); font-size: 13px; margin: 0 0 8px 4px;">
                    Data Date: ${baseDate} (Yesterday)
                </div>`
            );
            if (barGraphToggle.checked) {
                const dataPoints = [{label: "Yesterday Total", value: yVal, unit: "kWh"}];
                cardsContainer.insertAdjacentHTML("beforeend", getBarChartHTML("Energy Consumption", dataPoints, true));
            } else {
                cardsContainer.insertAdjacentHTML("beforeend", getCardHTML("Yesterday Total Consumption", yVal, "kWh", data[0].status || "OK", true, meterName));
            }
        } else {
            createCards(data[0]);
        }
    } else {
        cardsContainer.innerHTML = `<div style="color: var(--text-sub); padding: 20px;">No data recorded yet for this meter.</div>`;
    }
}

function createSummaryCardsForAll(summaries) {
    cardsContainer.innerHTML = "";
    summaries.forEach(summary => {
        const meterDiv = document.createElement("div");
        meterDiv.className = "meter-section";
        meterDiv.innerHTML = `<h3 style="margin-bottom: 10px; color: var(--text-main);">${summary.meter_name}</h3>`;
        const cardGrid = document.createElement("div");
        cardGrid.className = "cards";
        if (barGraphToggle.checked && summary.bars && summary.bars.length > 0) {
            const dataPoints = summary.bars.map(b => ({
                label: b.label,
                value: b.consumption,
                unit: "kWh"
            }));
            cardGrid.insertAdjacentHTML("beforeend", getBarChartHTML("Energy Consumption", dataPoints, true));
        } else {
            cardGrid.insertAdjacentHTML("beforeend", getCardHTML("Energy", summary.yesterday_total_kwh ?? 0, "kWh", "OK", true, summary.meter_name));
            cardGrid.insertAdjacentHTML("beforeend", getCardHTML("Shift Start", summary.current_shift_start_kwh ?? 0, "kWh", "OK", false, summary.meter_name));
            cardGrid.insertAdjacentHTML("beforeend", getCardHTML("Shift End", summary.current_shift_end_kwh ?? 0, "kWh", "OK", false, summary.meter_name));
            cardGrid.insertAdjacentHTML("beforeend", getCardHTML("Shift Consumption", summary.current_shift_consumption_kwh ?? 0, "kWh", "OK", false, summary.meter_name));
        }
        meterDiv.appendChild(cardGrid);
        cardsContainer.appendChild(meterDiv);
    });
}

// ================= EVENTS =================

plantSelect.addEventListener("change", async ()=>{
    const plant = plantSelect.value;
    const landingView = document.getElementById("landingView");
    const dashboardView = document.getElementById("dashboardView");

    if (plant) {
        dashboardTitle.innerText = `${plant} Dashboard`;
        if (landingView) landingView.style.display = "none";
        if (dashboardView) dashboardView.style.display = "block";
    } else {
        plantSelect.style.color = "inherit";
        dashboardTitle.innerText = "Energy Monitoring System";
        if (landingView) landingView.style.display = "block";
        if (dashboardView) dashboardView.style.display = "none";
    }
    applyThemeState();

    await loadMeters(plantSelect.value);
    syncShiftUiForMeter();

    cardsContainer.innerHTML = "";

    document.getElementById("liveStatus").style.display = "none";
    setupLiveStream();
});

meterSelect.addEventListener("change", loadBaseCardsOnMeterSelection);
meterSelect.addEventListener("change", syncShiftUiForMeter);
meterSelect.addEventListener("change", setupLiveStream);
submitFiltersBtn.addEventListener("click", loadData);
shiftAnalysisToggle.addEventListener("change", () => {
    syncShiftUiForMeter();
    scheduleRefreshFromStream();
});
barGraphToggle.addEventListener("change", () => {
    if (meterSelect.value && !shiftSelect.disabled && fromDateTime.value && toDateTime.value) {
        loadData();
    } else {
        loadBaseCardsOnMeterSelection();
    }
});
plantSelect.addEventListener("change", () => updateInsightCardsMeta({ barCount: 0 }));
shiftSelect.addEventListener("change", () => updateInsightCardsMeta({ barCount: 0 }));
fromDateTime.addEventListener("change", () => updateInsightCardsMeta({ barCount: 0 }));
toDateTime.addEventListener("change", () => updateInsightCardsMeta({ barCount: 0 }));

// ================= SCROLL LISTENER =================
window.addEventListener("scroll", () => {
    if (window.scrollY > 20) {
        navbar.classList.add("is-sticky");
        document.body.style.paddingTop = `${navbar.offsetHeight}px`;
    } else {
        navbar.classList.remove("is-sticky");
        document.body.style.paddingTop = "0px";
    }
});

// ================= THEME TOGGLE =================

function toggleTheme() {
    const isLight = document.body.classList.toggle("light-mode");
    localStorage.setItem("theme", isLight ? "light" : "dark");
    updateThemeIcon(isLight);
    applyThemeState();
}

function updateThemeIcon(isLight) {
    themeIcon.innerHTML = isLight ? moonIcon : sunIcon;
}

themeToggle.addEventListener("click", toggleTheme);

// ================= INIT =================

loadPlants();
setDefaultDateRange();

// Set initial theme
const savedTheme = localStorage.getItem("theme");
if (savedTheme === "light") {
    document.body.classList.add("light-mode");
    updateThemeIcon(true);
} else { // Default to dark if no theme saved or saved as dark
    updateThemeIcon(false);
}

applyThemeState();
updateInsightCardsMeta({ barCount: 0 });
syncShiftUiForMeter();
window.addEventListener("beforeunload", closeLiveStream);
