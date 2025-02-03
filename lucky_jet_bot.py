import os
import ssl
import telebot
import sqlite3
import schedule
import requests
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor

# Установка токена и ID администратора
TOKEN = "7834804003:AAGN4HU4HXnhVxwF3AnrMDpnP7CoPTmt-xs"
CASINO_API_URL = "https://1wcneg.com/?p=7a4t"
REFERRAL_LINK = "https://1wcneg.com/?open=register&p=7a4t"
ADMIN_ID = "@SR1win"
SIGNAL_INTERVAL = 8  # Интервал сигналов в минутах

bot = telebot.TeleBot(TOKEN)

def get_db_connection():
    return sqlite3.connect("users.db", check_same_thread=False)

# Создание таблицы пользователей
with get_db_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        registered INTEGER DEFAULT 0,
        vip INTEGER DEFAULT 0
    )
    """)
    conn.commit()

def is_user_registered(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT registered FROM users WHERE user_id=?", (user_id,))
        result = cursor.fetchone()
        return result and result[0] == 1

def is_user_vip(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT vip FROM users WHERE user_id=?", (user_id,))
        result = cursor.fetchone()
        return result and result[0] == 1

@bot.message_handler(commands=["start"])
def send_welcome(message):
    user_id = message.chat.id
    username = message.chat.username
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        user = cursor.fetchone()
    
        if user:
            bot.send_message(user_id, "Вы уже зарегистрированы! Ожидайте сигналы.")
        else:
            cursor.execute("INSERT INTO users (user_id, username, registered) VALUES (?, ?, 0)", (user_id, username))
            conn.commit()
            bot.send_message(user_id, f"Привет! Чтобы получать сигналы, зарегистрируйтесь по ссылке: {REFERRAL_LINK}")

@bot.message_handler(commands=["register"])
def register_user(message):
    user_id = message.chat.id
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if is_user_registered(user_id):
            bot.send_message(user_id, "Вы уже зарегистрированы!")
        else:
            cursor.execute("UPDATE users SET registered=1 WHERE user_id=?", (user_id,))
            conn.commit()
            bot.send_message(user_id, "Поздравляю! Вы зарегистрированы и будете получать сигналы.")

@bot.message_handler(commands=["addvip"])
def add_vip(message):
    if message.chat.username != ADMIN_ID:
        bot.send_message(message.chat.id, "У вас нет доступа к этой команде.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.send_message(message.chat.id, "Используйте: /addvip @username")
        return
    
    username = args[1].replace("@", "")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET vip=1 WHERE username=?", (username,))
        conn.commit()
    
    bot.send_message(message.chat.id, f"Пользователь @{username} теперь VIP!")

def fetch_lucky_jet_data():
    try:
        response = requests.get(CASINO_API_URL, timeout=5)
        response.raise_for_status()
        data = response.json()
        multipliers = data.get("multipliers", [])
        return [round(float(x), 2) for x in multipliers[-20:]] if multipliers else None
    except Exception as e:
        print(f"Ошибка запроса к API казино: {e}")
        return None

lin_reg = None
forest = None

def update_ml_model():
    global lin_reg, forest
    history = fetch_lucky_jet_data()
    if history and len(history) >= 5:
        df = pd.DataFrame({"x": np.arange(len(history)), "y": history})
        X, y = df[["x"]], df["y"]
        lin_reg = LinearRegression().fit(X, y)
        forest = RandomForestRegressor(n_estimators=100).fit(X, y)

update_ml_model()
schedule.every(30).minutes.do(update_ml_model)

def predict_multiplier():
    if not lin_reg or not forest:
        return None
    next_x = np.array([[20]])
    lin_pred = lin_reg.predict(next_x)[0]
    forest_pred = forest.predict(next_x)[0]
    return round((lin_pred + forest_pred) / 2, 2)

def send_signal_to_users(signal_text, vip_only=False):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = "SELECT user_id FROM users WHERE registered=1"
        if vip_only:
            query += " AND vip=1"
        cursor.execute(query)
        users = cursor.fetchall()
        
        for user in users:
            try:
                bot.send_message(user[0], f"🎰 Новый сигнал: {signal_text}")
            except Exception as e:
                print(f"Ошибка отправки сообщения: {e}")

def auto_send_signals():
    predicted_multiplier = predict_multiplier()
    if predicted_multiplier:
        if predicted_multiplier > 5.0:
            send_signal_to_users(f"🔥 VIP-сигнал! Высокий шанс на X{predicted_multiplier}+. Попробуйте!", True)
        elif predicted_multiplier > 2.0:
            send_signal_to_users(f"📈 Обычный сигнал: Ожидается X{predicted_multiplier}.")

schedule.every(SIGNAL_INTERVAL).minutes.do(auto_send_signals)

bot.polling()
