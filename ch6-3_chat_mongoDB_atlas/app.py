import os
from datetime import datetime
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from pymongo import MongoClient

# ====== 讀取 .env 環境變數（部署 Atlas 時才需要啟用）======
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ====== MongoDB 連線 ======
# 本地：mongodb://localhost:27017/   雲端 Atlas：由 .env / Render 的 MONGO_URI 提供
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
client = MongoClient(MONGO_URI)
db = client["chatapp"]          # 資料庫：chatapp
messages = db["messages"]       # 資料表(collection)：messages


def load_history():
    """從 MongoDB 取出所有訊息（依時間排序）"""
    return [
        {"username": m["username"], "content": m["content"], "time": m["time"]}
        for m in messages.find().sort("created_at", 1)
    ]


@app.route("/")
def index():
    return render_template("index.html")


clients = {}


def broadcast_user_count():
    emit("user_count",
         {"count": len([c for c in clients.values() if c["username"]])},
         broadcast=True)


@socketio.on("connect")
def on_connect():
    clients[request.sid] = {"username": None}
    print("Client connect:", request.sid)


@socketio.on("disconnect")
def on_disconnect(*args):
    info = clients.pop(request.sid, None)
    if info and info["username"]:
        emit("user_left", {"username": info["username"]}, broadcast=True)
        broadcast_user_count()
    print("Client disconnect:", request.sid)


@socketio.on("join")
def on_join(data):
    username = data.get("username", "匿名")
    clients[request.sid] = {"username": username}
    emit("history", load_history())
    emit("user_joined", {"username": username}, broadcast=True)
    broadcast_user_count()
    print(username, "joined")


@socketio.on("send_message")
def on_message(data):
    # 寫入 MongoDB
    messages.insert_one({
        "username": data.get("username", "匿名"),
        "content": data.get("content", ""),
        "time": datetime.now().strftime("%H:%M"),
        "created_at": datetime.now(),
    })
    emit("chat_message", data, broadcast=True, include_self=False)


@socketio.on("clear_chat")
def on_clear():
    # 刪除 MongoDB 中所有歷史記錄
    messages.delete_many({})
    emit("chat_cleared", broadcast=True)


@socketio.on("typing")
def on_typing(data):
    emit("typing", data, broadcast=True, include_self=False)


@socketio.on("change_username")
def on_change(data):
    old = data.get("oldUsername")
    new = data.get("newUsername")
    if request.sid in clients:
        clients[request.sid]["username"] = new
    emit("user_changed_name",
         {"oldUsername": old, "newUsername": new},
         broadcast=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=True)
