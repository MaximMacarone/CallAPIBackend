from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import Dict
import sqlite3
import json

app = FastAPI()

# Хранилища
users: Dict[str, Dict] = {}  # id -> user info
connected_users: Dict[str, WebSocket] = {}  # phone -> WebSocket
active_calls: Dict[str, Dict] = {}  # call_id -> info

# ----------- Модели -----------
class LoginUser(BaseModel):
    name: str
    phone: str
    user_id: str

# ----------- Регистрация пользователя -----------
@app.post("/login")
def login_user(data: LoginUser):
    users[data.user_id] = {
        "name": data.name,
        "phone": data.phone,
        "user_id": data.user_id
    }
    return {"status": "ok", "message": "User registered"}

# ----------- WebSocket подключение -----------
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()

    connected_users[user_id] = websocket
    print("Connected user", user_id)

    await send_connected_users()

    try:
        while True:
            raw_message = await websocket.receive_text()
            print("received: ", raw_message)

            try:
                message = json.loads(raw_message)

                if isinstance(message, list):
                    action = message[0]
                    data = message[1] if len(message) > 1 else {}

                    if action == "make_call":
                        receiver_ws = connected_users[data["extra"]["remote_id"]]
                        print(receiver_ws)
                        await receiver_ws.send_json([
                            "incoming_call",
                            {
                                "id": data["id"],
                                "nameCaller": data["aurora"]["localName"],
                                "handle": data["aurora"]["localHandle"],
                                "extra": {
                                    "remote_id": data["extra"]["local_id"],
                                    "local_id": data["extra"]["remote_id"],
                                },
                                "aurora": {
                                    "localName": data["nameCaller"],
                                    "localHandle": data["handle"],
                                    "holdable": data["aurora"]["holdable"],
                                    "uri": data["aurora"]["uri"]
                                }
                            }
                        ])
                        active_calls[data["id"]] = data
                        continue
                    elif action == "answer_call":
                        print("answer_call action with data: ", data)
                        receiver_ws = connected_users[active_calls[data["id"]]["extra"]["local_id"]]
                        caller_ws = connected_users[active_calls[data["id"]]["extra"]["remote_id"]]
                        await receiver_ws.send_json([
                            "set_call_connected",
                            {
                               "id": active_calls[data["id"]]["id"],
                            }
                        ])
                        await caller_ws.send_json([
                            "set_call_connected",
                            {
                                "id": active_calls[data["id"]]["id"],
                            }
                        ])
                    elif action == "end_call":
                        receiver_ws = connected_users[active_calls[data["id"]]["extra"]["local_id"]]
                        caller_ws = connected_users[active_calls[data["id"]]["extra"]["remote_id"]]
                        await receiver_ws.send_json([
                            "disconnect",
                            {
                                "id": active_calls[data["id"]]["id"],
                            }
                        ])
                        await caller_ws.send_json([
                            "disconnect",
                            {
                                "id": active_calls[data["id"]]["id"],
                            }
                        ])
                        continue
                    elif action == "hold_call":
                        continue
                    else:
                        continue
            except json.JSONDecodeError:
                print("JSON Decode Error")
    except WebSocketDisconnect:

        connected_users.pop(user_id, None)
        await send_connected_users()

# ----------- Отправка списка подключенных пользователей -----------

async def send_connected_users():
    print("USERS: ", users)
    print("CONNECTED: ", connected_users)
    for user_id, ws in list(connected_users.items()):
        online = [
            {"id": u["user_id"], "name": u["name"], "phone": u["phone"]}
            for u in users.values()
            if u["user_id"] in connected_users and u["user_id"] != user_id
        ]
        print("online", online)
        await ws.send_json(["update_contacts", online])
