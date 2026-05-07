# Energy Monitoring Software

FastAPI-based backend + web dashboard for multi-device, multi-meter energy monitoring.

## What This Project Does

- Receives meter snapshots over UDP (`port 6503`)
- Stores history in SQLite (`energy.db`)
- Serves a live dashboard (`dashboard.html`)
- Exposes REST APIs + SSE stream
- Calculates shift-wise energy consumption (A/B/C) and total
- Supports CSV export for historical data

---

## Project Files

- `app_fastapi.py`  
  Main backend (FastAPI), APIs, SSE stream, UDP listener, DB initialization.

- `app.py`  
  Entry launcher that starts FastAPI (`app_fastapi:app`) via Uvicorn.

- `dashboard.html`  
  Main UI markup.

- `static/styles_new.css`  
  Dashboard styling.

- `static/dashboard.js`  
  Dashboard logic (data fetch, SSE, rendering, shift summary, modal, download).

- `start_fastapi.bat` / `stop_fastapi.bat`  
  Windows scripts to start/stop backend with PID tracking.

---

## Requirements

Install Python dependencies:

```bash
pip install -r requirements.txt
```

`requirements.txt` includes:
- `fastapi`
- `uvicorn`
- `flask` (kept for compatibility/legacy file usage)

---

## Run the App

### Option 1: Direct

```bash
python app_fastapi.py
```

### Option 2: Using entry file

```bash
python app.py
```

### Option 3: Using BAT scripts (Windows)

Start:
```bat
start_fastapi.bat
```

Stop:
```bat
stop_fastapi.bat
```

PID is tracked at:
- `run/fastapi.pid`

---

## Dashboard

Open:
- `http://<server-ip>:5000`

### Dashboard Data Flow

- Live device/meter summary comes from:
  - `GET /api/v1/stream` (SSE, preferred)
  - plus safety sync fetch to keep UI fresh

- Shift summary comes from:
  - `GET /api/v1/shifts/summary`

### Key Dashboard Sections

- Current Shift Today card
- Device stats (Total Meters, Online, Offline, Total kW)
- Meter cards (click opens detail modal)
- Historical export panel
- Shift summary for selected date range

---

## API Endpoints

## v1 Routes (recommended)

- `GET /api/v1/health/ping`
- `GET /api/v1/devices`
- `GET /api/v1/devices/{device_id}`
- `GET /api/v1/devices/{device_id}/summary`
- `GET /api/v1/devices/{device_id}/meters/latest`
- `GET /api/v1/shifts/summary?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&device_id=<id>&shift=A|B|C`
- `GET /api/v1/reports/csv?...`
- `GET /api/v1/stream` (SSE)

### Legacy Routes (still present)

- `/api/summary`
- `/api/shift-summary`
- `/api/download`
- `/api/stream`

---

## Shift and Total Energy Calculation

Shift windows:
- Shift A: `06:00:00` to `13:59:59`
- Shift B: `14:00:00` to `21:59:59`
- Shift C: `22:00:00` to `05:59:59`

Calculation logic (`calculate_shift_summaries`):

1. Reads historical meter rows in date window (with small pre-window for previous reading)
2. Uses cumulative energy register:
   - `COALESCE(kwh_total, kw)` as `energy_total`
3. Computes per-meter delta:
   - normal: `delta = current - previous`
   - reset/rollover: `delta = current`
4. Adds positive delta to corresponding shift bucket (`A/B/C`)
5. `Total` = `A + B + C`

Notes:
- Dashboard `Total kW` is **instantaneous active power sum**, not kWh.
- Shift values are **energy consumption (kWh)** over selected date range.

---

## Why “Current Shift Today” and “Shift Summary” Can Differ

- `Current Shift Today` uses only **today + current shift**
- `Shift Summary (Selected Date Range)` uses **From/To date filters**

If From/To spans multiple days, values will differ by design.

---

## Troubleshooting

## 1) Data updates only after refresh

- Ensure backend is running and SSE endpoint reachable:
  - `GET /api/v1/stream`
- Hard refresh browser once (`Ctrl+F5`) after frontend changes.

## 2) CSP / `content.js` extension console errors

- Often caused by browser extensions injecting scripts.
- Test in Incognito or disable extension for this site.

## 3) Shift summary scope confusion

- Check summary scope label:
  - `Showing: All Devices` or selected device name.

## 4) Startup deprecation warning

- Already handled: FastAPI lifespan is used instead of deprecated `@app.on_event("startup")`.

---

## Deployment Notes

- Keep all project files together.
- Ensure virtual environment has dependencies from `requirements.txt`.
- Use `start_fastapi.bat` / `stop_fastapi.bat` on Windows for easy service control.
