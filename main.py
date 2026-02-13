import sqlite3
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import List, Dict
import json

app = FastAPI()

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("aurora.db")
    cursor = conn.cursor()
    # Таблица пользователей
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, bio TEXT)''')
    # Таблица сообщений
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages 
                      (id INTEGER PRIMARY KEY, sender TEXT, receiver TEXT, text TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# --- МОДЕЛИ ДАННЫХ ---
class AuthData(BaseModel):
    username: str
    password: str
    bio: str = "Minimalist. Aurora User."

# --- Менеджер подключений (для Real-time) ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, username: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[username] = websocket

    def disconnect(self, username: str):
        if username in self.active_connections:
            del self.active_connections[username]

    async def send_personal_message(self, message: dict, receiver: str):
        if receiver in self.active_connections:
            await self.active_connections[receiver].send_text(json.dumps(message))

manager = ConnectionManager()

# --- API ЭНДПОИНТЫ ---

@app.post("/register")
def register(data: AuthData):
    conn = sqlite3.connect("aurora.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password, bio) VALUES (?, ?, ?)", 
                       (data.username, data.password, data.bio))
        conn.commit()
        return {"success": True}
    except:
        return {"success": False, "message": "User exists"}
    finally:
        conn.close()

@app.post("/login")
def login(data: AuthData):
    conn = sqlite3.connect("aurora.db")
    cursor = conn.cursor()
    user = cursor.execute("SELECT username, bio FROM users WHERE username=? AND password=?", 
                          (data.username, data.password)).fetchone()
    conn.close()
    if user:
        return {"success": True, "username": user[0], "bio": user[1]}
    return {"success": False}

@app.get("/search/{query}")
def search_users(query: str):
    conn = sqlite3.connect("aurora.db")
    cursor = conn.cursor()
    users = cursor.execute("SELECT username FROM users WHERE username LIKE ?", (f"%{query}%",)).fetchall()
    conn.close()
    return [u[0] for u in users]

# --- WEBSOCKET ДЛЯ ЧАТА И СТАТУСОВ ---
@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await manager.connect(username, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            target = message_data.get("to")
            msg_type = message_data.get("type") # "chat", "typing"
            
            if msg_type == "chat":
                # Сохраняем в БД
                conn = sqlite3.connect("aurora.db")
                cursor = conn.cursor()
                cursor.execute("INSERT INTO messages (sender, receiver, text) VALUES (?, ?, ?)", 
                               (username, target, message_data["text"]))
                conn.commit()
                conn.close()
                
            # Пересылаем сообщение или статус "печатает"
            await manager.send_personal_message(message_data, target)
            
    except WebSocketDisconnect:
        manager.disconnect(username)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)