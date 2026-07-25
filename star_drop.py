import os
import sys
import asyncio
import logging
import sqlite3
import random
import time
import string
from datetime import datetime
from typing import Optional, List, Dict
import json
import hashlib

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8988678866:AAHIWxUB8zKBCoF21g7OVYEEWnwEF_MpLmI"
ADMIN_ID = 8551946505  # Ваш ID

PAYMENT_LINKS = {
    100: "https://yookassa.ru/my/i/amMy2QzHTXRI/l",
    200: "https://yookassa.ru/my/i/amMzHkXK55Uk/l",
    500: "https://yookassa.ru/my/i/amMzSdZUSmIm/l",
    1000: "https://yookassa.ru/my/i/amMzbZDBr9y2/l"
}

RUB_TO_TOKEN = 1

SPIN_COSTS = {
    "light": 25,
    "normal": 50,
    "hard": 100
}

# ========= ЧЕРЕДУЮЩИЕСЯ ПРИЗЫ (выигрыш, проигрыш, ...) =========
PRIZES = {
    "light": [
        {"name": "❌", "value": 0},
        {"name": "🏷 10", "value": 10},
        {"name": "❌", "value": 0},
        {"name": "🏷 15", "value": 15},
        {"name": "❌", "value": 0},
        {"name": "🏷 20", "value": 20},
        {"name": "❌", "value": 0},
        {"name": "🏷 25", "value": 25},
        {"name": "❌", "value": 0},
        {"name": "🏷 30", "value": 30},
        {"name": "❌", "value": 0},
        {"name": "🏷 40", "value": 40},
    ],
    "normal": [
        {"name": "❌", "value": 0},
        {"name": "🎟 50", "value": 50},
        {"name": "❌", "value": 0},
        {"name": "🎟 70", "value": 70},
        {"name": "❌", "value": 0},
        {"name": "🎟 100", "value": 100},
        {"name": "❌", "value": 0},
        {"name": "🎟 120", "value": 120},
        {"name": "❌", "value": 0},
        {"name": "🎟 150", "value": 150},
        {"name": "❌", "value": 0},
        {"name": "🎟 200", "value": 200},
    ],
    "hard": [
        {"name": "❌", "value": 0},
        {"name": "🎫 300", "value": 300},
        {"name": "❌", "value": 0},
        {"name": "🎫 400", "value": 400},
        {"name": "❌", "value": 0},
        {"name": "🎫 500", "value": 500},
        {"name": "❌", "value": 0},
        {"name": "🎫 600", "value": 600},
        {"name": "❌", "value": 0},
        {"name": "🎫 800", "value": 800},
        {"name": "❌", "value": 0},
        {"name": "🎫 1000", "value": 1000},
    ]
}

SLOT_SYMBOLS = ['🍒', '🍋', '🍊', '🍇', '🍉', '🍓', '🍑', '🎰']
SLOT_WIN_MULTIPLIER = 2

PROMOCODES = {
    "rifleman": 50,
    "blant": 50
}

rocket_rounds = {}
round_counter = 0
DB_NAME = "star_drop.db"
WEBAPP_URL = "https://star-drop.onrender.com"
REFERRAL_BONUS = 50

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            phone TEXT UNIQUE,
            balance INTEGER DEFAULT 0,
            total_spent INTEGER DEFAULT 0,
            total_won INTEGER DEFAULT 0,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            referrer_id INTEGER,
            referral_code TEXT UNIQUE
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount INTEGER,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS wins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            prize_name TEXT,
            prize_value INTEGER,
            mode TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users(user_id),
            FOREIGN KEY (referred_id) REFERENCES users(user_id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS used_promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            code TEXT,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            UNIQUE(user_id, code)
        )
    ''')
    try:
        cur.execute("ALTER TABLE users ADD COLUMN phone TEXT UNIQUE")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def get_user(user_id: int) -> Optional[Dict]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(user_id: int, username: str = None, phone: str = None, referrer_code: str = None):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    code = hashlib.md5(str(user_id).encode()).hexdigest()[:8]
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, username, phone, referral_code) VALUES (?, ?, ?, ?)",
        (user_id, username, phone, code)
    )
    if phone:
        cur.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
    if username:
        cur.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    
    if referrer_code:
        cur.execute("SELECT user_id FROM users WHERE referral_code = ?", (referrer_code,))
        row = cur.fetchone()
        if row:
            referrer_id = row[0]
            if referrer_id != user_id:
                cur.execute("SELECT id FROM referrals WHERE referred_id = ?", (user_id,))
                if not cur.fetchone():
                    cur.execute(
                        "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                        (referrer_id, user_id)
                    )
                    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (REFERRAL_BONUS, referrer_id))
                    cur.execute(
                        "INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                        (referrer_id, "deposit", REFERRAL_BONUS, f"Бонус за приглашение пользователя {user_id}")
                    )
    conn.commit()
    conn.close()

def update_balance(user_id: int, delta: int, description: str = ""):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))
    t_type = "spin" if "спин" in description else "deposit" if delta > 0 else "withdraw"
    cur.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                (user_id, t_type, delta, description))
    conn.commit()
    conn.close()

def add_win(user_id: int, prize_name: str, prize_value: int, mode: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT INTO wins (user_id, prize_name, prize_value, mode) VALUES (?, ?, ?, ?)",
                (user_id, prize_name, prize_value, mode))
    cur.execute("UPDATE users SET total_won = total_won + ? WHERE user_id = ?", (prize_value, user_id))
    conn.commit()
    conn.close()

def get_recent_wins(limit: int = 10) -> List[Dict]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('''
        SELECT u.username, w.prize_name, w.prize_value, w.created_at
        FROM wins w
        JOIN users u ON w.user_id = u.user_id
        WHERE w.prize_value > 0
        ORDER BY w.created_at DESC
        LIMIT ?
    ''', (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_user_bets(user_id: int, limit: int = 20) -> List[Dict]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('''
        SELECT type, amount, description, created_at
        FROM transactions
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (user_id, limit))
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_withdraw_requests(status: str = "pending") -> List[Dict]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('''
        SELECT w.*, u.username 
        FROM withdraw_requests w
        JOIN users u ON w.user_id = u.user_id
        WHERE w.status = ?
        ORDER BY w.created_at ASC
    ''', (status,))
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def create_withdraw_request(user_id: int, amount: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT INTO withdraw_requests (user_id, amount) VALUES (?, ?)", (user_id, amount))
    conn.commit()
    conn.close()

def approve_withdraw(request_id: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE withdraw_requests SET status = 'approved' WHERE id = ?", (request_id,))
    cur.execute("SELECT user_id, amount FROM withdraw_requests WHERE id = ?", (request_id,))
    row = cur.fetchone()
    if row:
        user_id, amount = row
        cur.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        cur.execute("INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                    (user_id, "withdraw", -amount, f"Вывод {amount} токенов (одобрено)"))
    conn.commit()
    conn.close()

def reject_withdraw(request_id: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?", (request_id,))
    conn.commit()
    conn.close()

def get_referral_info(user_id: int) -> Dict:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    code = row["referral_code"] if row else None
    cur.execute("SELECT COUNT(*) as count FROM referrals WHERE referrer_id = ?", (user_id,))
    count = cur.fetchone()["count"]
    conn.close()
    return {"code": code, "count": count}

def get_referral_link(user_id: int) -> str:
    info = get_referral_info(user_id)
    if info["code"]:
        return f"https://t.me/StarDrop11_bot?start=ref_{info['code']}"
    return None

def is_promo_used(user_id: int, code: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT id FROM used_promocodes WHERE user_id = ? AND code = ?", (user_id, code))
    row = cur.fetchone()
    conn.close()
    return row is not None

def use_promo(user_id: int, code: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT INTO used_promocodes (user_id, code) VALUES (?, ?)", (user_id, code))
    conn.commit()
    conn.close()

init_db()

# ==================== УТИЛИТЫ ====================
def get_spin_result(mode: str):
    if mode == "light":
        win_chance = 30
    elif mode == "normal":
        win_chance = random.randint(20, 50)
    elif mode == "hard":
        win_chance = random.randint(30, 45)
    else:
        win_chance = 35

    win = random.randint(1, 100) <= win_chance
    if win:
        available_prizes = [p for p in PRIZES[mode] if p["value"] > 0]
        if available_prizes:
            prize = random.choice(available_prizes)
            return True, prize["name"], prize["value"]
    return False, "❌ Проигрыш", 0

def get_prizes_for_mode(mode: str):
    return PRIZES[mode]

def get_slot_result(bet: int):
    if bet == 20:
        chance = 10
    elif 40 <= bet <= 70:
        chance = 30
    elif 71 <= bet <= 100:
        chance = 15
    else:
        chance = 10

    if random.randint(1, 100) <= chance:
        symbol = random.choice(SLOT_SYMBOLS)
        symbols = [symbol, symbol, symbol]
        win_amount = bet * SLOT_WIN_MULTIPLIER
        return True, symbols, win_amount
    else:
        symbols = random.choices(SLOT_SYMBOLS, k=3)
        if len(set(symbols)) == 1:
            other_symbols = [s for s in SLOT_SYMBOLS if s != symbols[0]]
            if other_symbols:
                symbols[0] = random.choice(other_symbols)
            else:
                symbols = random.choices(SLOT_SYMBOLS, k=3)
                while len(set(symbols)) == 1:
                    symbols = random.choices(SLOT_SYMBOLS, k=3)
        return False, symbols, 0

# ==================== ТЕЛЕГРАМ БОТ ====================
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_start_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🎰 Открыть рулетку", web_app=WebAppInfo(url=WEBAPP_URL))]],
        resize_keyboard=True
    )

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    args = message.text.split()
    referrer_code = None
    if len(args) > 1 and args[1].startswith("ref_"):
        referrer_code = args[1][4:]
    
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    user = get_user(user_id)
    if user and user.get("phone"):
        await message.answer(
            f"🎉 С возвращением, {username}!\n"
            "Добро пожаловать в **Star Drop** – розыгрыш подарков Telegram!\n\n"
            "Нажми кнопку ниже, чтобы открыть наше мини-приложение и испытать удачу! 🍀",
            reply_markup=get_start_keyboard()
        )
    else:
        if not user:
            create_user(user_id, username, referrer_code=referrer_code)
        await message.answer(
            f"👋 Привет, {username}!\n\n"
            "Для доступа к нашему сервису необходимо поделиться номером телефона.\n"
            "Нажмите кнопку ниже, чтобы отправить контакт.",
            reply_markup=get_phone_keyboard()
        )

@dp.message(F.contact)
async def handle_contact(message: types.Message):
    contact = message.contact
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    if contact.user_id != user_id:
        await message.answer("⛔ Пожалуйста, отправьте свой собственный номер.", reply_markup=get_phone_keyboard())
        return
    
    phone = contact.phone_number
    create_user(user_id, username, phone)
    
    await message.answer(
        "✅ Регистрация успешно завершена!\n\n"
        "Теперь вы можете пользоваться нашим сервисом. 🎉",
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer(
        "Нажмите кнопку ниже, чтобы открыть **Star Drop** и начать игру!",
        reply_markup=get_start_keyboard()
    )

@dp.message(Command("give"))
async def give_tokens(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: /give <user_id> <количество>")
        return
    try:
        target_id = int(args[1])
        amount = int(args[2])
        if amount <= 0:
            await message.answer("Сумма должна быть положительной.")
            return
        user = get_user(target_id)
        if not user:
            await message.answer(f"Пользователь с ID {target_id} не найден.")
            return
        update_balance(target_id, amount, f"Администратор выдал {amount} токенов")
        new_balance = get_user(target_id)['balance']
        await message.answer(
            f"✅ Пользователю @{user['username']} (ID: {target_id}) начислено {amount} токенов.\n"
            f"Новый баланс: {new_balance}"
        )
    except ValueError:
        await message.answer("ID и сумма должны быть числами.")

# ==================== ВЕБ-СЕРВЕР (FASTAPI) ====================
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import uvicorn
import aiofiles
import aiohttp

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = "static"
AVATARS_DIR = os.path.join(STATIC_DIR, "avatars")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(AVATARS_DIR, exist_ok=True)

@app.get("/api/avatar/{user_id}")
async def get_avatar(user_id: int):
    avatar_path = os.path.join(AVATARS_DIR, f"{user_id}.jpg")
    if os.path.exists(avatar_path):
        return {"url": f"/static/avatars/{user_id}.jpg"}
    
    try:
        photos = await bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count == 0:
            return {"url": "/static/default_avatar.png"}
        
        file_id = photos.photos[0][-1].file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        async with aiohttp.ClientSession() as session:
            url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    async with aiofiles.open(avatar_path, "wb") as f:
                        await f.write(await resp.read())
                    return {"url": f"/static/avatars/{user_id}.jpg"}
                else:
                    return {"url": "/static/default_avatar.png"}
    except Exception as e:
        logging.error(f"Avatar error: {e}")
        return {"url": "/static/default_avatar.png"}

STATIC_FILES = {
    "index.html": """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Star Drop</title>
    <link rel="stylesheet" href="/static/style.css?v=4">
</head>
<body class="theme-light">
    <div class="stars-background">
        <span>⭐</span><span>✨</span><span>🌟</span><span>💫</span>
        <span>🎁</span><span>🧸</span><span>💎</span><span>🧢</span>
        <span>🚀</span><span>💍</span><span>🧁</span><span>🎈</span>
        <span>👑</span><span>🛸</span><span>💎</span><span>🎁</span>
        <span>🎰</span><span>💵</span><span>⌚</span><span>👟</span>
        <span>📱</span><span>💻</span><span>🖥️</span><span>⌨️</span>
        <span>🕹️</span><span>🎮</span><span>🏆</span><span>🎖️</span>
        <span>💎</span><span>👑</span><span>🚀</span><span>🛸</span>
    </div>

    <div id="app-content" style="width:100%; max-width:400px;">
        <div id="top-bar">
            <div id="user-info" style="display:flex; align-items:center; gap:10px; cursor:pointer;">
                <div id="avatar-container" style="width:32px; height:32px; border-radius:50%; overflow:hidden; background:var(--accent-color);">
                    <img id="avatar-img" src="" alt="avatar" style="width:100%; height:100%; object-fit:cover; display:none;">
                    <span id="avatar-placeholder" style="display:flex; align-items:center; justify-content:center; width:100%; height:100%; font-weight:bold; font-size:16px; color:#0a0a0a;">U</span>
                </div>
                <span id="username">@user</span>
            </div>
            <div id="balance">
                <span id="balance-amount">0</span> 🎫
                <button id="deposit-btn">+</button>
                <button id="bets-btn">Мои ставки</button>
            </div>
        </div>

        <div id="deposit-menu" style="display: none;">
            <div style="width:100%; text-align:center; margin-bottom:10px; font-weight:bold; color:var(--accent-color);">Пополнить баланс</div>
            <button class="deposit-option" data-amount="100">100₽</button>
            <button class="deposit-option" data-amount="200">200₽</button>
            <button class="deposit-option" data-amount="500">500₽</button>
            <button class="deposit-option" data-amount="1000">1000₽</button>
            <button id="close-deposit">✖</button>
        </div>

        <div id="referral-modal" style="display: none; position: fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); justify-content:center; align-items:center; z-index:1000;">
            <div style="background:#1a1a1a; padding:20px; border-radius:12px; max-width:300px; width:90%; text-align:center; border:1px solid var(--accent-color);">
                <h3 style="color:var(--accent-color); margin-bottom:10px;">Реферальная система</h3>
                <p style="color:#ccc; font-size:14px;">Приведи друга и получи <b>+50 токенов</b> на баланс!</p>
                <p style="color:#fff; word-break:break-all; background:#222; padding:10px; border-radius:6px; margin:10px 0;" id="ref-link">Загрузка...</p>
                <button id="copy-ref-link" style="background:var(--accent-color); border:none; padding:8px 20px; border-radius:6px; font-weight:bold; cursor:pointer;">Копировать ссылку</button>
                <br><br>
                <span style="color:#aaa;">Приглашено друзей: <b id="ref-count">0</b></span>
                <br><br>
                <button id="close-ref-modal" style="background:#333; border:none; color:#fff; padding:8px 20px; border-radius:6px; cursor:pointer;">Закрыть</button>
            </div>
        </div>

        <div id="bets-modal" style="display: none; position: fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); justify-content:center; align-items:center; z-index:1000;">
            <div style="background:#1a1a1a; padding:20px; border-radius:12px; max-width:400px; width:90%; max-height:80%; overflow-y:auto; border:1px solid var(--accent-color);">
                <h3 style="color:var(--accent-color); margin-bottom:10px;">Мои ставки</h3>
                <ul id="bets-list" style="list-style:none; padding:0; margin:0;"></ul>
                <button id="close-bets-modal" style="background:#333; border:none; color:#fff; padding:8px 20px; border-radius:6px; margin-top:10px; cursor:pointer;">Закрыть</button>
            </div>
        </div>

        <div id="roulette-page">
            <div id="main-title">
                <h1>РУЛЕТКА STAR DROP</h1>
                <p>Испытай удачу и выиграй Telegram-подарки!</p>
            </div>
            <div id="prizes-list">
                <div class="prize-item">🧸 Мишка</div>
                <div class="prize-item">💎 Бриллиант</div>
                <div class="prize-item">💍 Кольцо</div>
                <div class="prize-item">🧁 Торт</div>
                <div class="prize-item">🧢 Кепка Дурова</div>
                <div class="prize-item">🚀 Ракета</div>
            </div>
            <div id="mode-selector">
                <button class="mode-btn active" data-mode="light">Low</button>
                <button class="mode-btn" data-mode="normal">Normal</button>
                <button class="mode-btn" data-mode="hard">Hard</button>
            </div>

            <div id="wheel-container">
                <div id="wheel-pointer">▼</div>
                <div class="wheel" id="wheel">
                    <div class="sector s1" data-win-index="-1"><div class="sector-content"><span class="icon icon-cross">✕</span></div></div>
                    <div class="sector s2" data-win-index="0"><div class="sector-content"><span class="icon icon-gift">🎁</span><span class="number">10</span></div></div>
                    <div class="sector s3" data-win-index="-1"><div class="sector-content"><span class="icon icon-cross">✕</span></div></div>
                    <div class="sector s4" data-win-index="1"><div class="sector-content"><span class="icon icon-gift">🎁</span><span class="number">15</span></div></div>
                    <div class="sector s5" data-win-index="-1"><div class="sector-content"><span class="icon icon-cross">✕</span></div></div>
                    <div class="sector s6" data-win-index="2"><div class="sector-content"><span class="icon icon-gift">🎁</span><span class="number">20</span></div></div>
                    <div class="sector s7" data-win-index="-1"><div class="sector-content"><span class="icon icon-cross">✕</span></div></div>
                    <div class="sector s8" data-win-index="3"><div class="sector-content"><span class="icon icon-gift">🎁</span><span class="number">25</span></div></div>
                    <div class="sector s9" data-win-index="-1"><div class="sector-content"><span class="icon icon-cross">✕</span></div></div>
                    <div class="sector s10" data-win-index="4"><div class="sector-content"><span class="icon icon-gift">🎁</span><span class="number">30</span></div></div>
                    <div class="sector s11" data-win-index="-1"><div class="sector-content"><span class="icon icon-cross">✕</span></div></div>
                    <div class="sector s12" data-win-index="5"><div class="sector-content"><span class="icon icon-gift">🎁</span><span class="number">40</span></div></div>
                    <div class="wheel-center"></div>
                </div>
            </div>

            <div id="spin-area">
                <div id="spin-info">1 спин = <span id="spin-cost">25</span> монет</div>
                <button id="spin-btn">КРУТИТЬ <span id="spin-cost-label">25 Токенов</span></button>
            </div>
            <div id="result-message"></div>
        </div>

        <div id="slot-page" style="display:none;">
            <div id="main-title">
                <h1>ИГРОВОЙ АВТОМАТ 🎰</h1>
                <p>Дёрни рычаг и удвой ставку!</p>
            </div>
            <div id="slot-machine">
                <div id="reels">
                    <div class="reel" id="reel1">🍒</div>
                    <div class="reel" id="reel2">🍋</div>
                    <div class="reel" id="reel3">🍊</div>
                </div>
                <div id="slot-controls">
                    <div class="bet-control">
                        <label>Ставка: <span id="bet-display">20</span> токенов</label>
                        <input type="range" id="bet-range" min="20" max="100" step="10" value="20">
                        <div id="slot-multiplier">При выигрыше: <b>x2</b> от ставки</div>
                    </div>
                    <button id="spin-slot-btn">Дёрнуть рычаг 🎰</button>
                </div>
                <div id="slot-result"></div>
            </div>
        </div>

        <div id="rocket-page" style="display:none;">
            <div id="main-title">
                <h1>🚀 РАКЕТКА</h1>
                <p>Лови момент и умножай ставку до x100!</p>
            </div>
            <div id="rocket-game">
                <div id="rocket-display">
                    <div id="rocket-multiplier">0.00</div>
                    <div id="rocket-status">Ожидание</div>
                </div>
                <div id="rocket-canvas-container">
                    <canvas id="rocketCanvas" width="300" height="200"></canvas>
                </div>
                <div id="rocket-bet-control">
                    <label>Ставка: <span id="rocket-bet-display">500</span> токенов</label>
                    <input type="range" id="rocket-bet-range" min="500" max="5000" step="100" value="500">
                </div>
                <div id="rocket-buttons">
                    <button id="rocket-start-btn">🚀 Старт</button>
                    <button id="rocket-cashout-btn" disabled>💰 Стоп</button>
                </div>
                <div id="rocket-timer">Следующий взлёт через: <span id="rocket-countdown">5</span>с</div>
                <div id="rocket-result"></div>
            </div>
        </div>

        <div id="notification-feed">
            <h3>Последние выигрыши</h3>
            <ul id="feed-list"></ul>
        </div>

        <button id="withdraw-btn">Вывести токены</button>

        <div id="promo-area">
            <input type="text" id="promo-input" placeholder="Введите промокод" maxlength="20">
            <button id="promo-btn">Активировать</button>
            <div id="promo-message" style="color: var(--accent-color); font-size: 14px; margin-top: 5px; text-align:center;"></div>
        </div>

        <div id="bottom-nav">
            <button class="nav-btn active" data-tab="roulette">Рулетка</button>
            <button class="nav-btn" data-tab="slot">Барабан</button>
            <button class="nav-btn" data-tab="rocket">Ракетка</button>
        </div>
    </div>

    <script src="/static/script.js?v=4"></script>
</body>
</html>""",
    "style.css": """* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
}

:root {
    --accent-color: #ffd700;
    --accent-glow: #ffd70066;
    --bg-dark: #0a0a0a;
    --text-light: #fff;
    --card-bg: #111;
    --border-color: #333;
    --wheel-size: 280px;
    --gold-color: #e6c65c;
    --red-sector: #ab2b44;
    --green-sector: #2b805e;
    --metal-rim: linear-gradient(145deg, #4a4f64, #1a1d2a, #4a4f64);
}

body {
    background: var(--bg-dark);
    color: var(--text-light);
    padding: 16px 16px 70px 16px;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    overflow-x: hidden;
    position: relative;
}

body.theme-light { --accent-color: #ffd700; --accent-glow: #ffd70066; }
body.theme-normal { --accent-color: #2196F3; --accent-glow: #2196F366; }
body.theme-hard { --accent-color: #f44336; --accent-glow: #f4433666; }

.stars-background {
    position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: -1; overflow: hidden;
}
.stars-background span {
    position: absolute; display: block; opacity: 0.5; color: var(--accent-color); text-shadow: 0 0 10px var(--accent-glow); font-size: 18px;
}
#top-bar {
    display: flex; justify-content: space-between; width: 100%; padding: 10px 0; border-bottom: 1px solid var(--border-color); z-index: 2;
}
#user-info { display: flex; align-items: center; gap: 10px; cursor: pointer; }
#avatar-container { width: 32px; height: 32px; border-radius: 50%; overflow: hidden; background: var(--accent-color); flex-shrink: 0; }
#avatar-img { width: 100%; height: 100%; object-fit: cover; display: none; }
#avatar-placeholder { display: flex; align-items: center; justify-content: center; width: 100%; height: 100%; font-weight: bold; font-size: 16px; color: #0a0a0a; }
#username { font-size: 18px; font-weight: 600; color: var(--accent-color); transition: color 0.3s; }
#balance { font-size: 18px; display: flex; align-items: center; gap: 8px; color: var(--accent-color); }
#balance-amount { font-weight: 700; }
#deposit-btn, #bets-btn {
    background: var(--accent-color); border: none; border-radius: 8px; padding: 4px 10px; font-weight: bold; color: #0a0a0a; cursor: pointer; font-size: 12px;
}
#deposit-btn { border-radius: 50%; width: 28px; height: 28px; font-size: 20px; padding: 0; }
#deposit-menu {
    background: var(--card-bg); border: 1px solid var(--accent-color); border-radius: 12px; padding: 16px; margin: 10px 0; display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; z-index: 10;
}
.deposit-option { background: var(--accent-color); color: #0a0a0a; border: none; padding: 10px 20px; border-radius: 8px; font-weight: 600; cursor: pointer; }
#close-deposit { background: transparent; color: var(--accent-color); border: none; font-size: 20px; cursor: pointer; }
#main-title { text-align: center; margin: 20px 0 10px; z-index: 2; }
#main-title h1 { font-size: 24px; font-weight: 900; color: var(--accent-color); letter-spacing: 2px; text-shadow: 0 0 10px var(--accent-glow); }
#main-title p { color: #aaa; font-size: 14px; margin-top: 4px; }
#prizes-list { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin: 15px 0; width: 100%; max-width: 400px; z-index: 2; }
.prize-item { background: #1a1a1a; border: 1px solid var(--border-color); border-radius: 20px; padding: 6px 14px; font-size: 13px; color: #ccc; }
#mode-selector { display: flex; gap: 12px; margin: 10px 0; z-index: 2; }
.mode-btn { background: #222; color: #aaa; border: none; padding: 6px 18px; border-radius: 20px; font-weight: 600; cursor: pointer; font-size: 13px; }
.mode-btn.active { background: var(--accent-color); color: #0a0a0a; box-shadow: 0 0 15px var(--accent-glow); }
#wheel-container { position: relative; width: var(--wheel-size); height: var(--wheel-size); margin: 15px auto; z-index: 2; }
#wheel-pointer {
    position: absolute; top: -20px; left: 50%; transform: translateX(-50%); width: 0; height: 0; border-left: 15px solid transparent; border-right: 15px solid transparent; border-top: 40px solid var(--gold-color); z-index: 10;
}
.wheel {
    width: 100%; height: 100%; border-radius: 50%; position: relative; overflow: hidden; box-shadow: 0 0 0 15px var(--metal-rim), 0 0 30px 20px rgba(0, 0, 0, 0.3); background: #000; transition: transform 4s cubic-bezier(0.25, 0.1, 0.25, 1);
}
.sector {
    position: absolute; width: 50%; height: 50%; transform-origin: 100% 100%; display: flex; flex-direction: column; justify-content: flex-start; align-items: center; box-sizing: border-box; padding-top: 10%; backface-visibility: hidden;
}
.sector:nth-child(odd) { background-color: var(--red-sector); }
.sector:nth-child(even) { background-color: var(--green-sector); }
.s1 { transform: rotate(0deg) skewY(-60deg); }
.s2 { transform: rotate(30deg) skewY(-60deg); }
.s3 { transform: rotate(60deg) skewY(-60deg); }
.s4 { transform: rotate(90deg) skewY(-60deg); }
.s5 { transform: rotate(120deg) skewY(-60deg); }
.s6 { transform: rotate(150deg) skewY(-60deg); }
.s7 { transform: rotate(180deg) skewY(-60deg); }
.s8 { transform: rotate(210deg) skewY(-60deg); }
.s9 { transform: rotate(240deg) skewY(-60deg); }
.s10 { transform: rotate(270deg) skewY(-60deg); }
.s11 { transform: rotate(300deg) skewY(-60deg); }
.s12 { transform: rotate(330deg) skewY(-60deg); }
.sector-content { transform: skewY(60deg); display: flex; flex-direction: column; align-items: center; width: 100%; position: absolute; top: 30px; }
.icon { font-size: 28px; margin-bottom: 4px; }
.number { font-weight: bold; font-size: 22px; color: #fff; text-shadow: 0 2px 4px rgba(0,0,0,0.5); }
.wheel-center {
    position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); width: 20%; height: 20%; background: radial-gradient(circle, #1a1d2a 40%, #000 70%); border-radius: 50%; border: 4px solid var(--gold-color); z-index: 5;
}
#spin-area { display: flex; flex-direction: column; align-items: center; margin: 15px 0; z-index: 2; }
#spin-info { font-size: 14px; color: #aaa; margin-bottom: 8px; }
#spin-btn {
    background: var(--accent-color); color: #0a0a0a; border: none; padding: 14px 40px; border-radius: 30px; font-weight: 700; font-size: 18px; cursor: pointer; box-shadow: 0 0 20px var(--accent-glow); display: flex; flex-direction: column; align-items: center; line-height: 1.2;
}
#spin-btn span { font-size: 14px; font-weight: 400; }
#result-message { margin: 10px 0; font-size: 18px; font-weight: 600; min-height: 40px; text-align: center; z-index: 2; color: var(--accent-color); }
#slot-machine, #rocket-game {
    background: var(--card-bg); border-radius: 20px; padding: 20px; margin: 10px 0; border: 2px solid var(--accent-color); box-shadow: 0 0 30px var(--accent-glow); width: 100%; max-width: 400px;
}
#reels { display: flex; justify-content: center; gap: 15px; padding: 15px 0; }
.reel { width: 70px; height: 80px; background: #222; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 48px; border: 2px solid var(--border-color); }
#slot-controls, .bet-control, #rocket-bet-control { display: flex; flex-direction: column; align-items: center; gap: 12px; margin-top: 10px; width: 100%; }
.bet-control label, #rocket-bet-control label { font-size: 14px; color: #ccc; }
#bet-range, #rocket-bet-range { width: 80%; max-width: 250px; margin-top: 5px; accent-color: var(--accent-color); }
#spin-slot-btn, #rocket-start-btn, #rocket-cashout-btn, #withdraw-btn, #promo-btn {
    background: var(--accent-color); color: #0a0a0a; border: none; padding: 12px 30px; border-radius: 30px; font-weight: 700; font-size: 18px; cursor: pointer; box-shadow: 0 0 20px var(--accent-glow);
}
#slot-result, #rocket-result { margin-top: 15px; font-size: 18px; font-weight: 600; text-align: center; color: var(--accent-color); min-height: 30px; }
#rocket-display { text-align: center; padding: 10px 0; }
#rocket-multiplier { font-size: 48px; font-weight: 900; color: var(--accent-color); text-shadow: 0 0 20px var(--accent-glow); }
#rocket-status { font-size: 16px; color: #aaa; margin-top: 5px; }
#rocketCanvas { width: 100%; height: auto; background: #0a0a0a; border-radius: 12px; }
#rocket-buttons { display: flex; justify-content: center; gap: 12px; margin: 15px 0; width: 100%; }
#rocket-start-btn, #rocket-cashout-btn { flex: 1; max-width: 150px; }
#rocket-timer { font-size: 14px; color: #aaa; text-align: center; }
#notification-feed { width: 100%; max-width: 400px; background: var(--card-bg); border-radius: 12px; padding: 12px; margin: 20px 0; border: 1px solid var(--border-color); }
#notification-feed h3 { color: var(--accent-color); margin-bottom: 8px; font-size: 16px; }
#feed-list { list-style: none; max-height: 150px; overflow-y: auto; }
#feed-list li { padding: 6px 0; border-bottom: 1px solid var(--border-color); font-size: 13px; color: #ddd; }
#promo-area { display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 8px; margin: 10px 0; width: 100%; max-width: 400px; }
#promo-input { flex: 1; min-width: 140px; padding: 8px 14px; border-radius: 20px; border: 1px solid var(--accent-color); background: #222; color: #fff; text-align: center; outline: none; }
#bottom-nav { position: fixed; bottom: 0; left: 0; width: 100%; background: #111; display: flex; justify-content: space-around; padding: 10px 0; border-top: 1px solid var(--border-color); z-index: 10; }
.nav-btn { background: transparent; color: #888; border: none; font-size: 14px; font-weight: 600; padding: 6px 20px; border-radius: 20px; cursor: pointer; }
.nav-btn.active { color: var(--accent-color); background: rgba(255,215,0,0.1); }
""",
    "script.js": """const BASE_URL = window.location.origin;
let user_id = null;
let balance = 0;
let currentMode = 'light';
let isSpinning = false;
let currentRotation = 0;

function showAuthError(message) {
    document.body.innerHTML = `
        <div style="display:flex; justify-content:center; align-items:center; height:100vh; flex-direction:column; background:#0a0a0a; color:#fff; text-align:center; padding:20px;">
            <h1 style="color:var(--accent-color);">⛔ Ошибка авторизации</h1>
            <p style="color:#ccc; margin:20px 0;">${message}</p>
            <button onclick="window.location.href='https://t.me/StarDrop11_bot'" style="background:var(--accent-color); border:none; padding:12px 30px; border-radius:8px; font-weight:bold; cursor:pointer; margin-top:10px;">Открыть бота</button>
        </div>
    `;
    throw new Error('Auth error');
}

if (window.Telegram && window.Telegram.WebApp) {
    window.Telegram.WebApp.ready();
    const tgUser = window.Telegram.WebApp.initDataUnsafe?.user;
    if (tgUser && tgUser.id) {
        user_id = tgUser.id;
        localStorage.setItem('starDrop_userId', user_id);
        const username = tgUser.username || tgUser.first_name || 'User';
        document.getElementById('username').textContent = '@' + username;
        loadAvatar(user_id);
        document.getElementById('avatar-placeholder').textContent = (tgUser.first_name || 'U').charAt(0).toUpperCase();
    } else {
        showAuthError('Не удалось получить данные пользователя из Telegram.');
    }
} else {
    const savedId = localStorage.getItem('starDrop_userId');
    if (savedId) {
        user_id = parseInt(savedId);
        document.getElementById('username').textContent = '@user_' + user_id;
        document.getElementById('avatar-placeholder').textContent = 'U';
    } else {
        showAuthError('Это приложение работает только в Telegram.');
    }
}

async function loadAvatar(userId) {
    try {
        const resp = await fetch(`/api/avatar/${userId}`);
        const data = await resp.json();
        if (data.url) {
            const img = document.getElementById('avatar-img');
            img.src = data.url;
            img.style.display = 'block';
            document.getElementById('avatar-placeholder').style.display = 'none';
        }
    } catch (e) { console.error(e); }
}

fetchUserData().then(() => initGames()).catch(() => initGames());

async function fetchUserData() {
    if (!user_id) return;
    try {
        const resp = await fetch(`/api/user/${user_id}`);
        if (!resp.ok) throw new Error();
        const data = await resp.json();
        balance = data.balance;
        document.getElementById('balance-amount').textContent = balance;
        if (data.username) document.getElementById('username').textContent = '@' + data.username;
    } catch (e) { console.error(e); }
}

function updateBalanceUI(newBalance) {
    balance = newBalance;
    document.getElementById('balance-amount').textContent = newBalance;
}

document.getElementById('user-info').addEventListener('click', async () => {
    if (!user_id) return;
    try {
        const resp = await fetch(`/api/referral/${user_id}`);
        const data = await resp.json();
        document.getElementById('ref-link').textContent = data.link;
        document.getElementById('ref-count').textContent = data.count;
        document.getElementById('referral-modal').style.display = 'flex';
    } catch (e) { alert('Ошибка загрузки реферальной информации'); }
});

document.getElementById('close-ref-modal').addEventListener('click', () => {
    document.getElementById('referral-modal').style.display = 'none';
});

document.getElementById('copy-ref-link').addEventListener('click', () => {
    navigator.clipboard.writeText(document.getElementById('ref-link').textContent).then(() => alert('Ссылка скопирована!'));
});

document.getElementById('bets-btn').addEventListener('click', async () => {
    if (!user_id) return;
    try {
        const resp = await fetch(`/api/user_bets/${user_id}`);
        const bets = await resp.json();
        const list = document.getElementById('bets-list');
        list.innerHTML = '';
        if (bets.length === 0) list.innerHTML = '<li style="color:#aaa;">Ставок пока нет</li>';
        else bets.forEach(b => {
            const li = document.createElement('li');
            let sign = b.amount > 0 ? '+' : '';
            let cls = b.amount > 0 ? 'positive' : (b.amount < 0 ? 'negative' : '');
            li.innerHTML = `<span class="${cls}">${sign}${b.amount}</span> ${b.description} <span style="color:#888;font-size:12px;">${new Date(b.created_at).toLocaleString()}</span>`;
            list.appendChild(li);
        });
        document.getElementById('bets-modal').style.display = 'flex';
    } catch (e) { alert('Ошибка загрузки ставок'); }
});

document.getElementById('close-bets-modal').addEventListener('click', () => {
    document.getElementById('bets-modal').style.display = 'none';
});

document.getElementById('promo-btn').addEventListener('click', async () => {
    if (!user_id) return;
    const input = document.getElementById('promo-input');
    const code = input.value.trim();
    const msg = document.getElementById('promo-message');
    if (!code) { msg.textContent = 'Введите промокод'; return; }
    try {
        const resp = await fetch('/api/activate_promo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id, code })
        });
        const data = await resp.json();
        if (resp.ok) {
            msg.textContent = '✅ ' + data.message;
            input.value = '';
            updateBalanceUI(data.new_balance);
        } else msg.textContent = '❌ ' + data.detail;
    } catch (e) { msg.textContent = 'Ошибка соединения'; }
});

function initGames() {
    updateSpinCost();
    document.getElementById('bet-display').textContent = document.getElementById('bet-range').value;
}

document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (isSpinning) return;
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentMode = btn.dataset.mode;
        updateSpinCost();
    });
});

function updateSpinCost() {
    const costs = { light: 25, normal: 50, hard: 100 };
    const cost = costs[currentMode];
    document.getElementById('spin-cost').textContent = cost;
    document.getElementById('spin-cost-label').textContent = cost + ' Токенов';
}

document.getElementById('spin-btn').addEventListener('click', async () => {
    if (!user_id || isSpinning) return;
    isSpinning = true;
    const btn = document.getElementById('spin-btn');
    btn.disabled = true;
    document.getElementById('result-message').textContent = '';
    
    try {
        const resp = await fetch('/api/spin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id, mode: currentMode })
        });
        const data = await resp.json();
        if (resp.ok) {
            updateBalanceUI(data.new_balance);
            const targetRotation = currentRotation + 1800 + Math.random() * 360;
            currentRotation = targetRotation;
            document.getElementById('wheel').style.transform = `rotate(${targetRotation}deg)`;
            
            setTimeout(() => {
                document.getElementById('result-message').textContent = data.message;
                document.getElementById('result-message').style.color = data.win ? '#4CAF50' : '#f44336';
                isSpinning = false;
                btn.disabled = false;
            }, 4000);
        } else {
            document.getElementById('result-message').textContent = '❌ ' + data.detail;
            isSpinning = false;
            btn.disabled = false;
        }
    } catch (e) {
        isSpinning = false;
        btn.disabled = false;
    }
});

document.getElementById('bet-range').addEventListener('input', function() {
    document.getElementById('bet-display').textContent = this.value;
});

document.getElementById('withdraw-btn').addEventListener('click', async () => {
    if (!user_id) return;
    const amount = prompt('Введите сумму вывода (минимум 500 токенов):');
    if (!amount || isNaN(amount) || amount < 500) {
        alert('Введите корректное число не менее 500');
        return;
    }
    try {
        const resp = await fetch('/api/withdraw', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id, amount: parseInt(amount) })
        });
        const data = await resp.json();
        if (resp.ok) alert('✅ Заявка на вывод отправлена!');
        else alert('❌ ' + data.detail);
    } catch (e) { alert('Ошибка соединения'); }
});

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.dataset.tab;
        document.getElementById('roulette-page').style.display = tab==='roulette' ? 'block' : 'none';
        document.getElementById('slot-page').style.display = tab==='slot' ? 'block' : 'none';
        document.getElementById('rocket-page').style.display = tab==='rocket' ? 'block' : 'none';
    });
});
"""
}

for filename, content in STATIC_FILES.items():
    filepath = os.path.join(STATIC_DIR, filename)
    if not os.path.exists(filepath):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")

@app.post("/webhook")
async def webhook(request: Request):
    update = types.Update(**(await request.json()))
    await dp.feed_update(bot, update)
    return {"status": "ok"}

class SpinRequest(BaseModel):
    user_id: int
    mode: str

class WithdrawRequest(BaseModel):
    user_id: int
    amount: int

class PromoRequest(BaseModel):
    user_id: int
    code: str

class SlotSpinRequest(BaseModel):
    user_id: int
    bet: int

class RocketStartRequest(BaseModel):
    user_id: int
    bet: int

class RocketCashoutRequest(BaseModel):
    round_id: int
    user_id: int

@app.get("/api/user/{user_id}")
async def api_get_user(user_id: int):
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"balance": user["balance"], "username": user["username"]}

@app.get("/api/user_bets/{user_id}")
async def api_user_bets(user_id: int):
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return get_user_bets(user_id, 50)

@app.post("/api/spin")
async def api_spin(data: SpinRequest):
    user_id = data.user_id
    mode = data.mode
    cost = SPIN_COSTS.get(mode, 25)
    user = get_user(user_id)
    if not user or user["balance"] < cost:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    update_balance(user_id, -cost, f"Спин в режиме {mode}")
    win, prize_name, prize_value = get_spin_result(mode)
    if win:
        update_balance(user_id, prize_value, f"Выигрыш: {prize_name}")
        add_win(user_id, prize_name, prize_value, mode)
        message = f"🎉 Вы выиграли {prize_name} (+{prize_value} токенов)!"
    else:
        message = "😞 К сожалению, вы проиграли."
    return {"win": win, "prize_name": prize_name if win else None, "prize_value": prize_value if win else 0, "new_balance": get_user(user_id)["balance"], "message": message}

@app.post("/api/slot_spin")
async def api_slot_spin(data: SlotSpinRequest):
    user_id = data.user_id
    bet = data.bet
    user = get_user(user_id)
    if not user or user["balance"] < bet:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    update_balance(user_id, -bet, f"Ставка {bet}")
    win, symbols, win_amount = get_slot_result(bet)
    if win:
        update_balance(user_id, win_amount, f"Выигрыш {win_amount}")
        add_win(user_id, f"🎰 {symbols[0]}", win_amount, "slot")
    return {"win": win, "symbols": symbols, "win_amount": win_amount, "new_balance": get_user(user_id)["balance"]}

@app.post("/api/withdraw")
async def api_withdraw(data: WithdrawRequest):
    user = get_user(data.user_id)
    if not user or user["balance"] < data.amount or data.amount < 500:
        raise HTTPException(status_code=400, detail="Неверная сумма или недостаточно средств")
    create_withdraw_request(data.user_id, data.amount)
    return {"status": "success"}

@app.get("/api/recent_wins")
async def api_recent_wins():
    return get_internal_recent_wins() if 'get_internal_recent_wins' in globals() else get_recent_wins()

@app.get("/api/referral/{user_id}")
async def api_referral(user_id: int):
    info = get_referral_info(user_id)
    return {"link": get_referral_link(user_id), "count": info["count"]}

# ==================== ЗАПУСК ПРИЛОЖЕНИЯ ДЛЯ RENDER ====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
