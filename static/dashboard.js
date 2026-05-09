/* ────────────────────────────────────────────────────────────────
   CONFIG
   Change API_BASE if Flask runs on a different host/port.
   ──────────────────────────────────────────────────────────────── */
// ── API base: auto-detects Flask server origin ──────────────────
// If you open this file directly (file://) it falls back to localhost:5000
const API_BASE = (location.protocol === 'file:')
  ? 'http://127.0.0.1:5000'   // opened as a local file — point at Flask
  : '';                         // served by Flask — same origin, no prefix needed

const POLL_MS     = 3000;        // fallback poll interval if SSE is unavailable
const SHIFT_POLL_MS = 300000;    // shift summary refresh (5 minutes)
const SHIFT_SYNC_MS = 60000;     // auto sync shift summary at most once per minute during live updates
const SAFETY_SYNC_MS = 10000;    // hard safety sync so UI updates even if SSE stalls
const LIVE_WINDOW = 6 * 60 * 1000;   // 6 min => LIVE
const STALE_WIN   = 12 * 60 * 1000;  // 12 min => DELAYED, then OFFLINE

/* ────────────────────────────────────────────────────────────────
   STATE
   ──────────────────────────────────────────────────────────────── */
let activeId    = null;
let allDevices  = [];
let shiftNowState = { label: 'Current Shift', value: '-- kWh' };
let liveSource = null;
let fallbackPollTimer = null;
let lastShiftSyncTs = 0;
let safetySyncTimer = null;

/* ────────────────────────────────────────────────────────────────
   CLOCK
   ──────────────────────────────────────────────────────────────── */
function updateClock() {
  const now = new Date();
  document.getElementById('hdr-clock').textContent =
    now.toLocaleTimeString('en-GB');
  document.getElementById('hdr-date').textContent =
    now.toLocaleDateString('en-GB', { weekday:'short', day:'numeric', month:'short', year:'numeric' }).toUpperCase();
}
setInterval(updateClock, 1000);
updateClock();

/* ────────────────────────────────────────────────────────────────
   HELPERS
   ──────────────────────────────────────────────────────────────── */
function fmt(v, decimals = 2) {
  if (v === null || v === undefined) return '—';
  return parseFloat(v).toFixed(decimals);
}

function deviceStatus(lastSeen) {
  if (!lastSeen) return 'dead';
  const age = Date.now() - new Date(lastSeen).getTime();
  if (age < LIVE_WINDOW)  return 'live';
  if (age < STALE_WIN)    return 'stale';
  return 'dead';
}

function statusLabel(s) {
  return { live: 'LIVE', stale: 'DELAYED', dead: 'OFFLINE' }[s] || 'UNKNOWN';
}

/* ────────────────────────────────────────────────────────────────
   TABS
   ──────────────────────────────────────────────────────────────── */
function renderTabs() {
  const bar = document.getElementById('tab-bar');
  bar.innerHTML = allDevices.map(d => {
    const st = deviceStatus(d.last_seen);
    return `
      <div class="tab ${d.id === activeId ? 'active' : ''} ${st}"
           data-device-id="${d.id}" title="${d.name}">
        <span class="tab-dot"></span>
        ${d.name}
      </div>`;
  }).join('');
}

function selectDevice(id) {
  activeId = id;
  // Reset the download device dropdown to "All Devices" when switching tabs
  // This ensures the summary logic falls back to the active tab ID.
  const devSel = document.getElementById('dl-device');
  if (devSel) devSel.value = "";

  renderTabs();
  renderPanel();
  updateShiftSummary(); // Refresh shift stats for the new device
}

/* ────────────────────────────────────────────────────────────────
   PANEL
   ──────────────────────────────────────────────────────────────── */
function renderPanel() {
  const dev = allDevices.find(d => d.id === activeId);
  if (!dev) {
    document.getElementById('panel-title').textContent = 'No Device Selected';
    document.getElementById('panel-meta').innerHTML = '';
    document.getElementById('stats-bar').innerHTML = '';
    shiftNowState = { label: 'Current Shift', value: '-- kWh' };
    document.getElementById('meter-area').innerHTML =
      '<div class="empty-state">// SELECT A DEVICE //</div>';
    return;
  }

  const st = deviceStatus(dev.last_seen);
  document.getElementById('panel-title').textContent = dev.name;
  document.getElementById('panel-meta').innerHTML =
    `IP: ${dev.ip || 'N/A'} &nbsp;·&nbsp; Last seen: ${dev.last_seen || '—'}
     <span class="live-chip ${st}">${statusLabel(st)}</span>`;

  const meters = dev.meters || [];

  /* ── Stats bar ── */
  const onlineCount  = meters.filter(m => m.status === 'OK').length;
  const offlineCount = meters.length - onlineCount;

  document.getElementById('stats-bar').innerHTML = `
    <div class="stat-card shift-now-card">
      <div class="stat-lbl" id="shift-now-label">Current Shift</div>
      <div class="stat-val" id="shift-now-value">-- kWh</div>
    </div>
    <div class="stat-card">
      <div class="stat-val">${meters.length}</div>
      <div class="stat-lbl">Total Meters</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" style="color:var(--ok)">${onlineCount}</div>
      <div class="stat-lbl">Online</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" style="color:var(--offline)">${offlineCount}</div>
      <div class="stat-lbl">Offline</div>
    </div>
  `;
  setShiftNowCard(shiftNowState.label, shiftNowState.value);

  /* ── Meter cards ── */
  if (!meters.length) {
    document.getElementById('meter-area').innerHTML =
      '<div class="empty-state">// NO METER DATA RECEIVED YET //</div>';
    return;
  }

  document.getElementById('meter-area').innerHTML = `
    <div class="meter-grid">
      ${meters.map((m, idx) => renderMeterCard(m, idx)).join('')}
    </div>`;
  bindMeterCardClicks(meters);
}

function renderMeterCard(m, idx) {
  const isOk = m.status === 'OK';
  const cls  = isOk ? 'ok' : 'off';
  const statusText = isOk ? '● ONLINE' : '✕ OFFLINE';

  const params = isOk ? `
    <div class="param-row">
      <span class="param-lbl">Frequency</span>
      <span class="param-val">${fmt(m.freq)}<span class="param-unit">Hz</span></span>
    </div>
    <div class="param-row">
      <span class="param-lbl">Voltage</span>
      <span class="param-val">${fmt(m.volt)}<span class="param-unit">V</span></span>
    </div>
    <div class="param-row">
      <span class="param-lbl">Current</span>
      <span class="param-val">${fmt(m.curr)}<span class="param-unit">A</span></span>
    </div>
    <div class="param-row">
      <span class="param-lbl">Power Factor</span>
      <span class="param-val">${fmt(m.pf, 3)}</span>
    </div>
    <div class="param-row">
      <span class="param-lbl">Active Power</span>
      <span class="param-val">${fmt(m.kw)}<span class="param-unit">kW</span></span>
    </div>
    <div class="param-row">
      <span class="param-lbl">Apparent Pwr</span>
      <span class="param-val">${fmt(m.kva)}<span class="param-unit">kVA</span></span>
    </div>
  ` : `<div class="offline-msg">// NO DATA RECEIVED //</div>`;

  return `
    <div class="meter-card ${cls}" data-meter-index="${idx}" title="Click to view details">
      <div class="meter-id">METER · ${String(m.meter_id || m.id || '?').padStart(2, '0')}</div>
      <div class="meter-status">${statusText}</div>
      ${params}
    </div>`;
}

function bindMeterCardClicks(meters) {
  document.querySelectorAll('.meter-card').forEach(card => {
    card.addEventListener('click', () => {
      const idx = Number(card.dataset.meterIndex);
      const meter = meters[idx];
      if (meter) openMeterModal(meter);
    });
  });
}

function openMeterModal(m) {
  const isOk = m.status === 'OK';
  const statusText = isOk ? 'ONLINE' : 'OFFLINE';
  const content = `
    <div class="meter-modal-title">Meter ${String(m.meter_id || m.id || '?').padStart(2, '0')}</div>
    <div class="meter-modal-sub ${isOk ? 'ok' : 'off'}">${statusText}</div>
    <table class="meter-modal-table">
      <tbody>
        <tr><th>Frequency</th><td>${fmt(m.freq)} Hz</td></tr>
        <tr><th>Voltage</th><td>${fmt(m.volt)} V</td></tr>
        <tr><th>Current</th><td>${fmt(m.curr)} A</td></tr>
        <tr><th>Power Factor</th><td>${fmt(m.pf, 3)}</td></tr>
        <tr><th>Active Power</th><td>${fmt(m.kw)} kW</td></tr>
        <tr><th>Apparent Power</th><td>${fmt(m.kva)} kVA</td></tr>
      </tbody>
    </table>
  `;
  document.getElementById('meter-modal-content').innerHTML = content;
  document.getElementById('meter-modal').style.display = 'flex';
}

function closeMeterModal(e) {
  if (e && e.target && e.target.closest('.meter-modal-card')) return;
  document.getElementById('meter-modal').style.display = 'none';
}

function bindUIEvents() {
  const themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) themeBtn.addEventListener('click', toggleTheme);

  const dlPanelTitle = document.querySelector('.dl-panel-title');
  if (dlPanelTitle) dlPanelTitle.addEventListener('click', toggleDlPanel);

  const dlBtn = document.getElementById('dl-btn');
  if (dlBtn) dlBtn.addEventListener('click', downloadCSV);

  const modal = document.getElementById('meter-modal');
  if (modal) modal.addEventListener('click', closeMeterModal);

  const modalCard = document.querySelector('.meter-modal-card');
  if (modalCard) modalCard.addEventListener('click', (evt) => evt.stopPropagation());

  const modalClose = document.querySelector('.meter-modal-close');
  if (modalClose) modalClose.addEventListener('click', () => closeMeterModal());

  const tabBar = document.getElementById('tab-bar');
  if (tabBar) {
    tabBar.addEventListener('click', (evt) => {
      const tab = evt.target.closest('.tab[data-device-id]');
      if (!tab) return;
      selectDevice(Number(tab.dataset.deviceId));
    });
  }
}

/* ────────────────────────────────────────────────────────────────
   DATA FETCHING
   ──────────────────────────────────────────────────────────────── */
async function fetchData() {
  try {
    const res  = await fetch(`${API_BASE}/api/v1/devices`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload = await res.json();
    applySummaryData(payload?.data || []);
  } catch (err) {
    console.error('Fetch error:', err);
    document.getElementById('meter-area').innerHTML =
      `<div class="empty-state">⚠ CANNOT REACH SERVER<br>
       <span style="font-size:.65rem;margin-top:8px;display:block">${err.message}</span>
       </div>`;
  }
}

function applySummaryData(devices) {
  allDevices = devices || [];

  if (!activeId && allDevices.length) {
    activeId = allDevices[0].id;
    // Initialize default dates and dropdowns immediately so the
    // shift summary has valid parameters to query from the start.
    populateDlDropdowns();
    // Fetch the initial shift summary for the first active device.
    updateShiftSummary();
  }

  // If selected tab device vanished, pick first available.
  if (activeId && !allDevices.some(d => d.id === activeId)) {
    activeId = allDevices.length ? allDevices[0].id : null;
  }

  renderTabs();
  renderPanel();
  maybeUpdateShiftSummaryFromLive();
}

function maybeUpdateShiftSummaryFromLive() {
  const now = Date.now();
  if (now - lastShiftSyncTs < SHIFT_SYNC_MS) return;
  lastShiftSyncTs = now;
  updateShiftSummary();
}

function startFallbackPolling() {
  if (fallbackPollTimer) return;
  fallbackPollTimer = setInterval(fetchData, POLL_MS);
}

function stopFallbackPolling() {
  if (!fallbackPollTimer) return;
  clearInterval(fallbackPollTimer);
  fallbackPollTimer = null;
}

function startLiveStream() {
  // Immediate snapshot so UI never waits for first SSE event.
  fetchData();

  if (!window.EventSource) {
    startFallbackPolling();
    return;
  }

  if (liveSource) liveSource.close();
  liveSource = new EventSource(`${API_BASE}/api/v1/stream`);

  liveSource.onmessage = (evt) => {
    try {
      const data = JSON.parse(evt.data);
      stopFallbackPolling();
      applySummaryData(data);
    } catch (e) {
      console.error('SSE parse error:', e);
    }
  };

  liveSource.onerror = () => {
    console.warn('SSE connection lost. Switching to fallback polling.');
    // Close the current instance to prevent overlapping retry loops
    if (liveSource) {
      liveSource.close();
      liveSource = null;
    }
    startFallbackPolling();
    // Attempt to restart the stream after a delay
    setTimeout(startLiveStream, 10000);
  };
}

function startSafetySync() {
  if (safetySyncTimer) return;
  safetySyncTimer = setInterval(fetchData, SAFETY_SYNC_MS);
}

/* ────────────────────────────────────────────────────────────────
   THEME TOGGLE
   ──────────────────────────────────────────────────────────────── */
function toggleTheme() {
  const isLight = document.body.classList.toggle('light-theme');
  localStorage.setItem('pgrid-theme', isLight ? 'light' : 'dark');
  updateThemeIcons(isLight);
}

function updateThemeIcons(isLight) {
  document.getElementById('sun-icon').style.display = isLight ? 'block' : 'none';
  document.getElementById('moon-icon').style.display = isLight ? 'none' : 'block';
}

// Initialization
(function initTheme() {
  const saved = localStorage.getItem('pgrid-theme');
  if (saved === 'light') {
    document.body.classList.add('light-theme');
    updateThemeIcons(true);
  }
})();

/* ────────────────────────────────────────────────────────────────
   BOOT
   ──────────────────────────────────────────────────────────────── */
bindUIEvents();
startLiveStream();
startSafetySync();
setInterval(updateShiftSummary, SHIFT_POLL_MS); // Auto-refresh shift data

/* ────────────────────────────────────────────────────────────────
   DOWNLOAD PANEL
   ──────────────────────────────────────────────────────────────── */

function toggleDlPanel() {
  const panel   = document.getElementById('dl-panel');
  const chevron = panel.querySelector('.dl-chevron');
  const isOpen  = panel.classList.toggle('open');
  chevron.style.transform = isOpen ? 'rotate(180deg)' : '';
  if (isOpen) populateDlDropdowns();
}

function populateDlDropdowns() {
  // Device dropdown
  const devSel = document.getElementById('dl-device');
  const curDev = devSel.value;
  devSel.innerHTML = '<option value="">All Devices</option>' +
    allDevices.map(d => `<option value="${d.id}" ${d.id == curDev ? 'selected' : ''}>${d.name}</option>`).join('');

  // Meter dropdown — 1-18
  const mtrSel  = document.getElementById('dl-meter');
  const curMtr  = mtrSel.value;
  mtrSel.innerHTML = '<option value="">All Meters</option>' +
    Array.from({length: 18}, (_, i) => i + 1)
      .map(n => `<option value="${n}" ${n == curMtr ? 'selected' : ''}>Meter ${String(n).padStart(2,'0')}</option>`)
      .join('');

  // Default dates: today and 7 days ago
  const today = new Date();
  const week  = new Date(today);
  week.setDate(week.getDate() - 7);

  if (!document.getElementById('dl-from').value)
    document.getElementById('dl-from').value = getLocalISODate(week);
  if (!document.getElementById('dl-to').value)
    document.getElementById('dl-to').value   = getLocalISODate(today);

  // Keep single handlers (avoid stacking listeners on repeated calls)
  document.getElementById('dl-from').onchange = updateShiftSummary;
  document.getElementById('dl-to').onchange = updateShiftSummary;
  document.getElementById('dl-shift').onchange = updateShiftSummary;
  document.getElementById('dl-device').onchange = updateShiftSummary;
  document.getElementById('dl-meter').onchange = updateShiftSummary;

  // Initial shift summary update
  updateShiftSummary();
}

function getCurrentShiftMeta() {
  const now = new Date();
  const hhmmss = now.toTimeString().slice(0, 8);
  if (hhmmss >= '06:00:00' && hhmmss <= '13:59:59') {
    return { key: 'A', label: 'Shift A (06:00-13:59)' };
  }
  if (hhmmss >= '14:00:00' && hhmmss <= '21:59:59') {
    return { key: 'B', label: 'Shift B (14:00-21:59)' };
  }
  return { key: 'C', label: 'Shift C (22:00-05:59)' };
}

function getLocalISODate(date = new Date()) {
  const z = n => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${z(date.getMonth() + 1)}-${z(date.getDate())}`;
}

function setShiftNowCard(label, value) {
  shiftNowState = { label, value };
  const labelEl = document.getElementById('shift-now-label');
  const valueEl = document.getElementById('shift-now-value');
  if (!labelEl || !valueEl) return;
  labelEl.textContent = label;
  valueEl.textContent = value;
}

async function updateShiftSummary() {
  const dateFrom = document.getElementById('dl-from').value;
  const dateTo   = document.getElementById('dl-to').value;
  const shift    = document.getElementById('dl-shift').value;
  const selectedDevice = document.getElementById('dl-device').value;
  const selectedDeviceId = selectedDevice ? Number(selectedDevice) : null;
  // If dropdown is "All Devices", aggregate across all devices.
  // If a device is selected in dropdown, use that device filter.
  const rangeDeviceId = selectedDeviceId;
  // Current shift card should follow active tab device.
  const currentShiftDeviceId = activeId || null;
  const devSelEl = document.getElementById('dl-device');
  const selectedDeviceName = selectedDeviceId && devSelEl
    ? (devSelEl.options[devSelEl.selectedIndex]?.text || `Device ${selectedDevice}`)
    : "All Devices";
  const scopeEl = document.getElementById('shift-scope');
  if (scopeEl) scopeEl.textContent = `Showing: ${selectedDeviceName}`;

  if (!dateFrom || !dateTo) {
    document.getElementById('shift-a').textContent = '0.00 kWh';
    document.getElementById('shift-b').textContent = '0.00 kWh';
    document.getElementById('shift-c').textContent = '0.00 kWh';
    document.getElementById('shift-total').textContent = '0.00 kWh';
    return;
  }

  try {
    let url = `${API_BASE}/api/v1/shifts/summary?date_from=${dateFrom}&date_to=${dateTo}`;
    if (shift) url += `&shift=${shift}`;
    if (rangeDeviceId !== null) url += `&device_id=${rangeDeviceId}`;

    const res = await fetch(url);
    if (res.ok) {
      const payload = await res.json();
      const summaries = payload?.data?.consumption_kwh || payload || {};
      document.getElementById('shift-a').textContent = `${(summaries.A || 0).toFixed(2)} kWh`;
      document.getElementById('shift-b').textContent = `${(summaries.B || 0).toFixed(2)} kWh`;
      document.getElementById('shift-c').textContent = `${(summaries.C || 0).toFixed(2)} kWh`;
      const total = (summaries.A || 0) + (summaries.B || 0) + (summaries.C || 0);
      document.getElementById('shift-total').textContent = `${total.toFixed(2)} kWh`;

      // Show running shift + present shift total for today.
      const currentShift = getCurrentShiftMeta();
      const today = getLocalISODate();
      let currentUrl = `${API_BASE}/api/v1/shifts/summary?date_from=${today}&date_to=${today}&shift=${currentShift.key}`;
      if (currentShiftDeviceId !== null) {
        currentUrl += `&device_id=${currentShiftDeviceId}`;
      }
      const currentRes = await fetch(currentUrl);
      if (currentRes.ok) {
        const currentPayload = await currentRes.json();
        const currentData = currentPayload?.data?.consumption_kwh || currentPayload || {};
        const presentShiftKwh = Number(currentData[currentShift.key] || 0).toFixed(2);
        setShiftNowCard(`Current Shift Today: ${currentShift.label}`, `${presentShiftKwh} kWh`);
      } else {
        setShiftNowCard(`Current Shift Today: ${currentShift.label}`, 'N/A');
      }
    } else {
      document.getElementById('shift-a').textContent = 'N/A';
      document.getElementById('shift-b').textContent = 'N/A';
      document.getElementById('shift-c').textContent = 'N/A';
      document.getElementById('shift-total').textContent = 'N/A';
      setShiftNowCard('Current Shift', 'N/A');
    }
  } catch (err) {
    console.error('Shift summary error:', err);
    document.getElementById('shift-a').textContent = 'Error';
    document.getElementById('shift-b').textContent = 'Error';
    document.getElementById('shift-c').textContent = 'Error';
    document.getElementById('shift-total').textContent = 'Error';
    setShiftNowCard('Current Shift', 'Error');
  }
}

function downloadCSV() {
  const dateFrom = document.getElementById('dl-from').value;
  const dateTo   = document.getElementById('dl-to').value;
  const deviceId = document.getElementById('dl-device').value;
  const meterId  = document.getElementById('dl-meter').value;
  const hint     = document.getElementById('dl-hint');
  const btn      = document.getElementById('dl-btn');

  if (!dateFrom || !dateTo) {
    hint.textContent = '⚠ Please select both From and To dates.';
    hint.className   = 'dl-hint error';
    return;
  }

  if (dateFrom > dateTo) {
    hint.textContent = '⚠ From date must be before To date.';
    hint.className   = 'dl-hint error';
    return;
  }

  const shift = document.getElementById('dl-shift').value;
  let url = `${API_BASE}/api/v1/reports/csv?date_from=${dateFrom}&date_to=${dateTo}`;
  if (deviceId) url += `&device_id=${deviceId}`;
  if (meterId)  url += `&meter_id=${meterId}`;
  if (shift)    url += `&shift=${shift}`;

  hint.textContent = '⏳ Preparing download…';
  hint.className   = 'dl-hint';
  btn.disabled     = true;

  // Trigger browser download
  const a = document.createElement('a');
  a.href  = url;
  a.click();

  setTimeout(() => {
    btn.disabled     = false;
    hint.textContent = `✔ Download started: ${dateFrom} → ${dateTo}`;
    hint.className   = 'dl-hint ok';
  }, 1200);
}
