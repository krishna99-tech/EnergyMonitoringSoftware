from flask import Flask, render_template
import socketio

# Use gevent for real WebSocket support
sio = socketio.Server(cors_allowed_origins='*', async_mode='threading')

flask_app = Flask(__name__)

# Store users
users = {}   # username -> sid
sid_map = {} # sid -> username

# ===================== SOCKET EVENTS =====================

@sio.event
def connect(sid, environ):
    print("Client connected:", sid)

@sio.event
def register(sid, data):
    username = data.get('username')

    if not username:
        sio.emit('message', "Username required!", to=sid)
        return

    if username in users:
        sio.emit('message', "Username already taken!", to=sid)
        return

    users[username] = sid
    sid_map[sid] = username

    print(f"{username} registered")

    sio.emit('message', f"{username} joined the chat")

@sio.event
def broadcast(sid, data):
    username = sid_map.get(sid)
    message = data.get('message')

    if not username or not message:
        return

    msg = f"{username}: {message}"
    print("Broadcast:", msg)

    sio.emit('message', msg)

@sio.event
def private_message(sid, data):
    sender = sid_map.get(sid)
    target = data.get('to')
    message = data.get('message')

    if not sender or not target or not message:
        return

    msg = f"(Private) {sender}: {message}"

    if target in users:
        sio.emit('message', msg, to=users[target])
    else:
        sio.emit('message', "User not found", to=sid)

@sio.event
def disconnect(sid):
    username = sid_map.get(sid)

    if username:
        print(f"{username} disconnected")
        del users[username]
        del sid_map[sid]

        sio.emit('message', f"{username} left the chat")

# ===================== ROUTES =====================

@flask_app.route('/')
def index():
    return render_template('index.html')

# ===================== RUN SERVER =====================

if __name__ == '__main__':
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler

    app = socketio.WSGIApp(sio, flask_app)

    print("🚀 Server running at http://localhost:5000")

    pywsgi.WSGIServer(
        ("0.0.0.0", 5000),
        app,
        handler_class=WebSocketHandler
    ).serve_forever()