from flask import Flask
import socketio

# Create server
sio = socketio.Server(cors_allowed_origins='*', async_mode='threading')
app = Flask(__name__)
app = socketio.WSGIApp(sio, app)

clients = set()

@sio.event
def connect(sid, environ):
    print("Client connected:", sid)
    clients.add(sid)

@sio.event
def disconnect(sid):
    print("Client disconnected:", sid)
    clients.discard(sid)

# Function to take input and send to all clients
def send_input():
    while True:
        msg = input("Enter message to send: ")
        sio.emit('message', msg)

if __name__ == '__main__':
    from threading import Thread
    from werkzeug.serving import run_simple

    # Run input thread
    Thread(target=send_input, daemon=True).start()

    print("Server running on http://localhost:5000")
    run_simple("0.0.0.0", 5000, app)