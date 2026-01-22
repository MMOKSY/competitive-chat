import socketio
import requests

BASE_URL = "http://127.0.0.1:8000"

# 1) Login to get JWT
login = requests.post(f"{BASE_URL}/auth/login", json={
    "username": "abc",
    "password": "abc123"
})
login.raise_for_status()

TOKEN = login.json()["access_token"]
print("JWT:", TOKEN)

# 2) Connect to Socket.IO with JWT
sio = socketio.Client()

@sio.event
def connect():
    print("Connected to socket")
    sio.emit("subscribe", {"room": "group:1"})

@sio.event
def disconnect():
    print("Disconnected from socket")

@sio.on("subscribed")
def on_subscribed(data):
    print("SUBSCRIBED:", data)

@sio.on("unsubscribed")
def on_unsubscribed(data):
    print("UNSUBSCRIBED:", data)

@sio.on("message")
def on_message(data):
    print("MESSAGE:", data)

@sio.on("error")
def on_error(data):
    print("ERROR:", data)

sio.connect(BASE_URL, auth={"token": TOKEN})
sio.wait()
