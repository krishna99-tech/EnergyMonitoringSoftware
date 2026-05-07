from flask import Flask, render_template_string
import socket
import json
import threading
import time

app = Flask(__name__)

# ✅ Shared data (thread-safe simple use)
latest_data = {"device": "No Data", "meters": []}
last_update = "No Data"

# ================= UDP LISTENER =================
def udp_listener():
    global latest_data, last_update

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 6503))

    print("✅ UDP Server listening on port 6503...")

    while True:
        data, addr = sock.recvfrom(4096)

        try:
            decoded = data.decode()
            parsed = json.loads(decoded)

            latest_data = parsed
            last_update = time.strftime("%Y-%m-%d %H:%M:%S")

            print("\n📡 Received from:", addr)
            print(decoded)

        except Exception as e:
            print("❌ JSON Error:", e)


# ================= HTML TEMPLATE =================
HTML = """
<!DOCTYPE html>
<html>
<head>
<title>ESP32 Energy Dashboard</title>

<meta http-equiv="refresh" content="2">

<style>
body {
    font-family: Arial;
    background:#f4f6f9;
    padding:20px;
}

h1 {
    color:#333;
}

.grid {
    display:flex;
    flex-wrap:wrap;
}

.card {
    background:white;
    padding:15px;
    margin:10px;
    border-radius:10px;
    box-shadow:0 3px 6px rgba(0,0,0,0.2);
    width:250px;
}

.ok {
    color:green;
    font-weight:bold;
}

.offline {
    color:red;
    font-weight:bold;
}

.param {
    margin:3px 0;
}
</style>

</head>

<body>

<h1>⚡ ESP32 Energy Dashboard</h1>

<h3>Device: {{data.get('device', 'No Data')}}</h3>
<p>Last Update: {{timestamp}}</p>

<div class="grid">

{% for m in data.get('meters', []) %}

<div class="card">

<h2>Meter ID: {{m.get('id')}}</h2>

{% if m.get('status') == "OK" %}
<p class="ok">Status: OK</p>

<p class="param">Frequency: {{m.get('freq', 'N/A')}}</p>
<p class="param">Voltage: {{m.get('volt', 'N/A')}}</p>
<p class="param">Current: {{m.get('curr', 'N/A')}}</p>
<p class="param">Power Factor: {{m.get('pf') if m.get('pf') is not none else 'N/A'}}</p>
<p class="param">kW: {{m.get('kw', 'N/A')}}</p>
<p class="param">kVA: {{m.get('kva', 'N/A')}}</p>

{% else %}
<p class="offline">Status: OFFLINE</p>
<p>No Data Available</p>
{% endif %}

</div>

{% endfor %}

</div>

</body>
</html>
"""


# ================= ROUTE =================
@app.route("/")
def home():
    return render_template_string(
        HTML,
        data=latest_data,
        timestamp=last_update
    )


# ================= MAIN =================
if __name__ == "__main__":

    # ✅ Start UDP thread (same process)
    thread = threading.Thread(target=udp_listener)
    thread.daemon = True
    thread.start()

    # ❗ IMPORTANT: disable reloader
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)