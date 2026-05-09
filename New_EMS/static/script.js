const plantSelect = document.getElementById("plantSelect");
const meterSelect = document.getElementById("meterSelect");

const cardsContainer =
    document.getElementById("cardsContainer");

const dashboardTitle =
    document.getElementById("dashboardTitle");

const navbar = document.querySelector(".navbar");

const themeToggle = document.getElementById("themeToggle");
const themeIcon = document.getElementById("themeIcon");
const moonIcon = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>';
const sunIcon = '<circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="4.22" x2="19.78" y2="5.64"></line>';

const plantThemes = {
    "Automotive": {
        primaryColor: "#3b82f6", // Blue
        darkBgGradient: "linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #3b82f61a 100%)", // Dark base with a hint of blue
        lightBgGradient: "linear-gradient(135deg, #f1f5f9 0%, #cbd5e1 50%, #3b82f61a 100%)" // Light base with a hint of blue
    },
    "IG Plant": {
        primaryColor: "#22c55e",    // Green
        darkBgGradient: "linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #22c55e1a 100%)", // Dark base with a hint of green
        lightBgGradient: "linear-gradient(135deg, #f1f5f9 0%, #cbd5e1 50%, #22c55e1a 100%)" // Light base with a hint of green
    }
};

// ================= TIME =================

const iconMap = {
    "Voltage": '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"></path>', // Bolt
    "Current": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"></path>', // Activity
    "Frequency": '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7zm10-3a3 3 0 100 6 3 3 0 000-6z"></path>', // Wave
    "PF": '<path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10zm0-2a8 8 0 100-16 8 8 0 000 16z"></path><path d="M12 8v4l3 3"></path>', // Gauge
    "KW": '<path d="M18.36 6.64a9 9 0 11-12.73 0M12 2v10"></path>', // Power
    "KVA": '<path d="M23 6l-9.5 9.5-5-5L1 18"></path>', // Trending Up
    "Energy Consumption": '<path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"></path>' // Database/Storage
};

/**
 * Helper to generate the HTML for a single parameter card
 */
function getCardHTML(label, value, unit, status, isEnergy = false) {
    const icon = isEnergy ? iconMap["Energy Consumption"] : (iconMap[label] || iconMap["Voltage"]);
    const cardClass = status !== 'OK' ? 'card-container error-status' : 'card-container';
    const btnText = status === 'OK' ? (isEnergy ? 'Operational' : 'Device Online') : 'Check Device';
    const titleLabel = isEnergy ? 'CONSUMPTION' : 'LIVE DATA';
    const displayTitle = isEnergy ? 'Energy Consumption' : label;
    const description = isEnergy ? 'Cumulative meter reading' : 'Real-time monitoring active';

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
    document.getElementById("currentTime").innerText = now.toLocaleString();
}

setInterval(updateTime,1000);

updateTime();

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

    const res =
    await fetch(`/meters?plant=${plant}`);

    const meters = await res.json();

    meters.forEach(m=>{

        const option = document.createElement("option");

        option.value = m.id;
        option.textContent = m.name;

        meterSelect.appendChild(option);
    });

    // Add "All Devices" option
    const allOption = document.createElement("option");
    allOption.value = "all";
    allOption.textContent = "All Devices (Excluding Main Incomer)";
    meterSelect.appendChild(allOption);
}

// ================= CREATE CARDS =================

function createCards(data){

    cardsContainer.innerHTML = "";

    // Add timestamp info
    const timeInfo = document.createElement("div");
    timeInfo.style.gridColumn = "1 / -1";
    timeInfo.innerHTML = `<p style="color: var(--text-sub); font-size: 14px; margin: 0 0 10px 5px;">Last Updated: ${data.timestamp}</p>`;
    cardsContainer.appendChild(timeInfo);

    // Incomer meter
    if(data.meter_type === "incomer"){

        const params = [
            ["Voltage", data.volt, "V"],
            ["Current", data.curr, "A"],
            ["Frequency", data.freq, "Hz"],
            ["PF", data.pf, ""],
            ["KW", data.kw, "kW"],
            ["KVA", data.kva, "kVA"]
        ];

        params.forEach(p=>{
            cardsContainer.insertAdjacentHTML('beforeend', getCardHTML(p[0], p[1], p[2], data.status));
        });
    }

    // Submeter KWH
    if(data.meter_type === "submeter"){
        cardsContainer.insertAdjacentHTML('beforeend', getCardHTML("Energy", data.kwh, "kWh", data.status, true));
    }
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
            <h3 style="margin-bottom: 5px; color: var(--text-main);">${d.meter_name}</h3>
            <p style="font-size: 12px; color: var(--text-sub); margin: 0 0 15px 0;">Last Updated: ${d.timestamp}</p>
        `;

        // Incomer meter
        if(d.meter_type === "incomer"){

            const params = [
                ["Voltage", d.volt, "V"],
                ["Current", d.curr, "A"],
                ["Frequency", d.freq, "Hz"],
                ["PF", d.pf, ""],
                ["KW", d.kw, "kW"],
                ["KVA", d.kva, "kVA"]
            ];

            params.forEach(p => {
                cardGrid.insertAdjacentHTML('beforeend', getCardHTML(p[0], p[1], p[2], d.status));
            });
        }

        // Submeter KWH
        if(d.meter_type === "submeter"){
            cardGrid.insertAdjacentHTML('beforeend', getCardHTML("Energy", d.kwh, "kWh", d.status, true));
        }

        meterDiv.appendChild(cardGrid);
        cardsContainer.appendChild(meterDiv);
    });
}

// ================= LOAD DATA =================

async function loadData(){

    const plant = plantSelect.value;
    const meter = meterSelect.value;

    if(!plant || !meter) return;

    dashboardTitle.innerText = `${plant} Dashboard`;
    const theme = plantThemes[plant];
    if (theme) {
        plantSelect.style.color = theme.primaryColor;
        dashboardTitle.style.color = theme.primaryColor;
        dashboardTitle.style.setProperty('--title-glow', `0 0 15px ${theme.primaryColor}88`);
        navbar.style.setProperty('--nav-border-bottom-color', theme.primaryColor);

        const isLightMode = document.body.classList.contains("light-mode");
        document.body.style.setProperty('--dynamic-bg-gradient', isLightMode ? theme.lightBgGradient : theme.darkBgGradient);
    } else {
        plantSelect.style.color = "inherit";
        dashboardTitle.style.color = "var(--text-main)";
        dashboardTitle.style.removeProperty('--title-glow');
        navbar.style.setProperty('--nav-border-bottom-color', 'transparent');
        document.body.style.setProperty('--dynamic-bg-gradient', 'var(--bg-gradient)');
    }

    document.getElementById("liveStatus").style.display = "flex";

    if(meter === "all"){

        const res = await fetch(`/latest?plant=${plant}&meter=all`);

        const allData = await res.json();

        const filteredData = allData.filter(d => d.meter_name !== "Main Incomer");

        createCardsForAll(filteredData);

    } else {

        const res = await fetch(`/latest?plant=${plant}&meter=${meter}`);

        const data = await res.json();

        if(data.length > 0){
            createCards(data[0]);
        } else {
            cardsContainer.innerHTML = 
                `<div style="color: var(--text-sub); padding: 20px;">No data recorded yet for this meter.</div>`;
        }
    }
}

// ================= EVENTS =================

plantSelect.addEventListener("change", async ()=>{

    const plant = plantSelect.value;
    if (plant) {
        dashboardTitle.innerText = `${plant} Dashboard`;
        const theme = plantThemes[plant];
        plantSelect.style.color = theme.primaryColor || "inherit";
        dashboardTitle.style.color = theme.primaryColor || "var(--text-main)";
        dashboardTitle.style.setProperty('--title-glow', theme.primaryColor ? `0 0 15px ${theme.primaryColor}88` : 'none');
        navbar.style.setProperty('--nav-border-bottom-color', theme.primaryColor);

        const isLightMode = document.body.classList.contains("light-mode");
        document.body.style.setProperty('--dynamic-bg-gradient', isLightMode ? theme.lightBgGradient : theme.darkBgGradient);
    } else {
        plantSelect.style.color = "inherit";
        dashboardTitle.innerText = "Energy Monitoring Dashboard";
        dashboardTitle.style.color = "var(--text-main)";
        dashboardTitle.style.removeProperty('--title-glow');
        navbar.style.setProperty('--nav-border-bottom-color', 'transparent');
        document.body.style.setProperty('--dynamic-bg-gradient', 'var(--bg-gradient)');
    }

    await loadMeters(plantSelect.value);

    cardsContainer.innerHTML = "";

    document.getElementById("liveStatus").style.display = "none";
});

meterSelect.addEventListener("change", loadData);

// ================= THEME TOGGLE =================

function toggleTheme() {
    const isLight = document.body.classList.toggle("light-mode");
    localStorage.setItem("theme", isLight ? "light" : "dark");
    updateThemeIcon(isLight);
}

function updateThemeIcon(isLight) {
    themeIcon.innerHTML = isLight ? moonIcon : sunIcon;
}

themeToggle.addEventListener("click", toggleTheme);

// ================= INIT =================

loadPlants();

// Set initial theme
const savedTheme = localStorage.getItem("theme");
if (savedTheme === "light") {
    document.body.classList.add("light-mode");
    updateThemeIcon(true);
} else { // Default to dark if no theme saved or saved as dark
    updateThemeIcon(false);
}

// Apply dynamic background if a plant is already selected on load
const initialPlant = plantSelect.value;
if (initialPlant && plantThemes[initialPlant]) {
    const theme = plantThemes[initialPlant];
    document.body.style.setProperty('--dynamic-bg-gradient', savedTheme === "light" ? theme.lightBgGradient : theme.darkBgGradient);
} else {
    updateThemeIcon(false);
}

setInterval(loadData,3000);