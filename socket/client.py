import socketio

sio = socketio.Client()

@sio.event
def connect():
    print("Connected to server")

@sio.event
def message(data):
    print("Received from server:", data)

@sio.event
def disconnect():
    print("Disconnected from server")

sio.connect('http://localhost:5000')
sio.wait()