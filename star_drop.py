import os
import sys
import asyncio
import logging
import sqlite3
import random
import time
from datetime import datetime
from typing import Optional, List, Dict
import hashlib
import math

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8988678866:AAHIWxUB8zKBCoF21g7OVYEEWnwEF_MpLmI"
ADMIN_ID = 8551946505

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

PRIZE_RANGES = {
    "light": {"min": 10, "max": 100, "win_chance": 40},
    "normal": {"min": 50, "max": 200, "win_chance": 45},
    "hard": {"min": 10, "max": 500, "win_chance": 50}
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
START_BALANCE = 50

last_spin_result = {}

def get_next_spin_result(user_id: int, mode: str):
    ranges = PRIZE_RANGES.get(mode, PRIZE_RANGES["light"])
    if user_id not in last_spin_result:
        win = random.randint(1, 100) <= ranges["win_chance"]
    else:
        win = not last_spin_result[user_id]
    last_spin_result[user_id] = win

    if win:
        prize_value = random.randint(ranges["min"], ranges["max"])
        icon = "🏷️" if mode == "light" else "🎟️" if mode == "normal" else "🎫"
        prize_name = f"{icon} {prize_value}"
    else:
        prize_value = 0
        prize_name = "❌ Проигрыш"
    return win, prize_name, prize_value

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            telegram_id INTEGER,
            balance INTEGER DEFAULT 50,
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
            username TEXT,
            type TEXT,
            amount INTEGER,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS wins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            prize_name TEXT,
            prize_value INTEGER,
            mode TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users(id),
            FOREIGN KEY (referred_id) REFERENCES users(id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS used_promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            code TEXT,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, code)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            payment_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    conn.close()

def get_user_by_username(username: str) -> Optional[Dict]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_id(user_id: int) -> Optional[Dict]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(username: str, password: str, telegram_id: int = None) -> Optional[Dict]:
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM users WHERE username = ?", (username,))
    if cur.fetchone():
        conn.close()
        return None
    
    code = hashlib.md5(username.encode()).hexdigest()[:8]
    cur.execute(
        "INSERT INTO users (username, password, telegram_id, referral_code, balance) VALUES (?, ?, ?, ?, ?)",
        (username, password, telegram_id, code, START_BALANCE)
    )
    user_id = cur.lastrowid
    
    cur.execute(
        "INSERT INTO transactions (user_id, username, type, amount, description) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, "deposit", START_BALANCE, "Стартовый бонус 50 токенов")
    )
    
    conn.commit()
    conn.close()
    return get_user_by_id(user_id)

def login_user(username: str, password: str) -> Optional[Dict]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def update_balance(user_id: int, delta: int, description: str = ""):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (delta, user_id))
    cur.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    username = row[0] if row else None
    t_type = "spin" if "спин" in description else "deposit" if delta > 0 else "withdraw"
    cur.execute("INSERT INTO transactions (user_id, username, type, amount, description) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, t_type, delta, description))
    conn.commit()
    conn.close()

def add_win(user_id: int, prize_name: str, prize_value: int, mode: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    username = row[0] if row else None
    cur.execute("INSERT INTO wins (user_id, username, prize_name, prize_value, mode) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, prize_name, prize_value, mode))
    cur.execute("UPDATE users SET total_won = total_won + ? WHERE id = ?", (prize_value, user_id))
    conn.commit()
    conn.close()

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

def create_withdraw_request(user_id: int, amount: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    username = row[0] if row else None
    cur.execute("INSERT INTO withdraw_requests (user_id, username, amount) VALUES (?, ?, ?)", (user_id, username, amount))
    conn.commit()
    conn.close()

def get_withdraw_requests(status: str = "pending") -> List[Dict]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('''
        SELECT * FROM withdraw_requests
        WHERE status = ?
        ORDER BY created_at ASC
    ''', (status,))
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def approve_withdraw(request_id: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE withdraw_requests SET status = 'approved' WHERE id = ?", (request_id,))
    cur.execute("SELECT user_id, amount FROM withdraw_requests WHERE id = ?", (request_id,))
    row = cur.fetchone()
    if row:
        user_id, amount = row
        cur.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, user_id))
        cur.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        username_row = cur.fetchone()
        username = username_row[0] if username_row else None
        cur.execute("INSERT INTO transactions (user_id, username, type, amount, description) VALUES (?, ?, ?, ?, ?)",
                    (user_id, username, "withdraw", -amount, f"Вывод {amount} токенов (одобрено)"))
    conn.commit()
    conn.close()

def reject_withdraw(request_id: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?", (request_id,))
    conn.commit()
    conn.close()

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

def get_referral_info(user_id: int) -> Dict:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT referral_code FROM users WHERE id = ?", (user_id,))
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

def get_recent_wins(limit: int = 10) -> List[Dict]:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute('''
        SELECT username, prize_name, prize_value, created_at
        FROM wins
        WHERE prize_value > 0
        ORDER BY created_at DESC
        LIMIT ?
    ''', (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

init_db()

def get_slot_result(bet: int):
    chance = 50
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

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, ReplyKeyboardRemove

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
    
    await message.answer(
        "👋 Добро пожаловать в **Star Drop**!\n\n"
        "Для входа в игру используйте наше мини-приложение.\n"
        "Нажмите кнопку ниже, чтобы открыть приложение и войти в свой аккаунт.",
        reply_markup=get_start_keyboard()
    )

@dp.message(F.contact)
async def handle_contact(message: types.Message):
    await message.answer(
        "📱 Для входа используйте мини-приложение.\n"
        "Нажмите кнопку '🎰 Открыть рулетку' ниже.",
        reply_markup=get_start_keyboard()
    )

@dp.message(Command("give"))
async def give_tokens(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет прав для этой команды.")
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Использование: /give <username> <количество>")
        return
    try:
        target_username = args[1]
        amount = int(args[2])
        if amount <= 0:
            await message.answer("Сумма должна быть положительной.")
            return
        user = get_user_by_username(target_username)
        if not user:
            await message.answer(f"Пользователь с именем {target_username} не найден.")
            return
        update_balance(user['id'], amount, f"Администратор выдал {amount} токенов")
        new_balance = get_user_by_id(user['id'])['balance']
        await message.answer(
            f"✅ Пользователю @{target_username} начислено {amount} токенов.\n"
            f"Новый баланс: {new_balance}"
        )
    except ValueError:
        await message.answer("Сумма должна быть числом.")

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

# СОЗДАНИЕ СТАТИЧЕСКИХ ФАЙЛОВ
with open(os.path.join(STATIC_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write("""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Star Drop</title>
    <link rel="stylesheet" href="/static/style.css?v=24">
</head>
<body>
    <!-- ЭКРАН ВХОДА -->
    <div id="login-screen" style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; width:100%; max-width:400px; padding:20px; background:#0a0a0a;">
        <h1 style="color:var(--accent-color, #ffd700); font-size:28px; margin-bottom:10px;">⭐ STAR DROP</h1>
        <p style="color:#aaa; margin-bottom:30px;">Войдите в свой аккаунт</p>
        <div style="width:100%; max-width:300px;">
            <input id="login-username" type="text" placeholder="Имя пользователя" style="width:100%; padding:12px; border-radius:8px; border:1px solid #333; background:#111; color:#fff; margin-bottom:10px; font-size:16px;">
            <input id="login-password" type="password" placeholder="Пароль" style="width:100%; padding:12px; border-radius:8px; border:1px solid #333; background:#111; color:#fff; margin-bottom:15px; font-size:16px;">
            <button id="login-btn" style="width:100%; padding:14px; background:#ffd700; color:#0a0a0a; border:none; border-radius:8px; font-weight:bold; font-size:18px; cursor:pointer;">Войти</button>
            <div id="login-error" style="color:#ff1744; margin-top:10px; text-align:center; font-size:14px;"></div>
        </div>
    </div>

    <!-- ОСНОВНОЕ ПРИЛОЖЕНИЕ -->
    <div id="app-content" style="display:none; width:100%; max-width:400px;">
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

        <div id="top-bar">
            <div id="user-info" style="display:flex; align-items:center; gap:10px; cursor:pointer;">
                <div id="avatar-container" style="width:32px; height:32px; border-radius:50%; overflow:hidden; background:var(--accent-color);">
                    <img id="avatar-img" src="" alt="avatar" style="width:100%; height:100%; object-fit:cover; display:none;">
                    <span id="avatar-placeholder" style="display:flex; align-items:center; justify-content:center; width:100%; height:100%; font-weight:bold; font-size:16px; color:#0a0a0a;">U</span>
                </div>
                <span id="username-display" style="color:var(--accent-color); font-weight:600; font-size:14px;"></span>
            </div>
            <div id="balance">
                <span id="balance-amount">0</span> 🎫
                <button id="deposit-btn">+</button>
                <button id="bets-btn">Ставки</button>
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

        <!-- РУЛЕТКА -->
        <div id="roulette-page">
            <div id="main-title">
                <h1>⭐ STAR DROP</h1>
                <p>Выбери режим и испытай удачу!</p>
            </div>
            <div id="mode-selector">
                <button class="mode-btn active" data-mode="light">Low</button>
                <button class="mode-btn" data-mode="normal">Normal</button>
                <button class="mode-btn" data-mode="hard">Hard</button>
            </div>

            <div id="key-container">
                <div id="key-display">🔑</div>
            </div>

            <div id="wheel-wrapper" style="display:none;">
                <div id="wheel-container">
                    <div id="wheel-strip"></div>
                    <div id="wheel-arrow">▼</div>
                </div>
            </div>

            <div id="spin-area">
                <div id="spin-info">1 спин = <span id="spin-cost">25</span> монет</div>
                <button id="spin-btn">КРУТИТЬ <span id="spin-cost-label">25 Токенов</span></button>
            </div>
            <div id="result-message"></div>
        </div>

        <!-- СЛОТ -->
        <div id="slot-page" style="display:none;">
            <div id="main-title">
                <h1>⭐ STAR DROP</h1>
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

        <!-- РАКЕТКА -->
        <div id="rocket-page" style="display:none;">
            <div id="main-title">
                <h1>⭐ STAR DROP</h1>
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
                    <input type="range" id="rocket-bet-range" min="100" max="1000" step="10" value="500">
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
            <h3>Последние события</h3>
            <ul id="feed-list"></ul>
        </div>

        <button id="withdraw-btn">Вывести токены</button>

        <div id="promo-area">
            <input type="text" id="promo-input" placeholder="Введите промокод" maxlength="20">
            <button id="promo-btn">Активировать</button>
            <div id="promo-message" style="color: var(--accent-color); font-size: 14px; margin-top: 5px; text-align:center;"></div>
        </div>

        <div id="bottom-nav">
            <div style="display:flex; gap:4px; flex:1; justify-content:center;">
                <button class="nav-btn active" data-tab="roulette">Рулетка</button>
                <button class="nav-btn" data-tab="slot">Барабан</button>
                <button class="nav-btn" data-tab="rocket">Ракетка</button>
            </div>
            <button id="logout-btn" style="background:transparent; color:#888; border:none; font-size:13px; font-weight:600; padding:6px 12px; border-radius:20px; cursor:pointer; flex-shrink:0; margin-left:4px;">🚪Выход</button>
        </div>
    </div>

    <script src="/static/script.js?v=24"></script>
</body>
</html>""")

# CSS
with open(os.path.join(STATIC_DIR, "style.css"), "w", encoding="utf-8") as f:
    f.write("""* {
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
    --key-color: #ffd700;
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

body.theme-light {
    --accent-color: #ffd700;
    --accent-glow: #ffd70066;
    --key-color: #ffd700;
}
body.theme-normal {
    --accent-color: #ff69b4;
    --accent-glow: #ff69b466;
    --key-color: #ff69b4;
}
body.theme-hard {
    --accent-color: #ff1744;
    --accent-glow: #ff174466;
    --key-color: #ff1744;
}

.stars-background {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: -1;
    overflow: hidden;
}
.stars-background span {
    position: absolute;
    display: block;
    opacity: 0.5;
    color: var(--accent-color);
    text-shadow: 0 0 10px var(--accent-glow);
    font-size: 18px;
    animation: float var(--duration) ease-in-out infinite alternate;
    animation-delay: var(--delay);
}
.stars-background span:nth-child(1) { left: 5%; top: 10%; --duration: 12s; --delay: 0s; animation: float1 12s ease-in-out infinite alternate; }
.stars-background span:nth-child(2) { left: 15%; top: 20%; --duration: 15s; --delay: 2s; animation: float2 15s ease-in-out infinite alternate; }
.stars-background span:nth-child(3) { left: 25%; top: 5%; --duration: 10s; --delay: 1s; animation: float3 10s ease-in-out infinite alternate; }
.stars-background span:nth-child(4) { left: 35%; top: 40%; --duration: 18s; --delay: 3s; animation: float4 18s ease-in-out infinite alternate; }
.stars-background span:nth-child(5) { left: 45%; top: 15%; --duration: 13s; --delay: 0.5s; animation: float5 13s ease-in-out infinite alternate; }
.stars-background span:nth-child(6) { left: 55%; top: 30%; --duration: 11s; --delay: 4s; animation: float6 11s ease-in-out infinite alternate; }
.stars-background span:nth-child(7) { left: 65%; top: 50%; --duration: 16s; --delay: 1.5s; animation: float7 16s ease-in-out infinite alternate; }
.stars-background span:nth-child(8) { left: 75%; top: 8%; --duration: 14s; --delay: 2.5s; animation: float8 14s ease-in-out infinite alternate; }
.stars-background span:nth-child(9) { left: 85%; top: 25%; --duration: 9s; --delay: 0.8s; animation: float9 9s ease-in-out infinite alternate; }
.stars-background span:nth-child(10) { left: 92%; top: 60%; --duration: 17s; --delay: 3.5s; animation: float10 17s ease-in-out infinite alternate; }
.stars-background span:nth-child(11) { left: 10%; top: 70%; --duration: 19s; --delay: 5s; animation: float11 19s ease-in-out infinite alternate; }
.stars-background span:nth-child(12) { left: 40%; top: 80%; --duration: 12s; --delay: 1.2s; animation: float12 12s ease-in-out infinite alternate; }
.stars-background span:nth-child(13) { left: 70%; top: 75%; --duration: 14s; --delay: 2.8s; animation: float13 14s ease-in-out infinite alternate; }
.stars-background span:nth-child(14) { left: 20%; top: 90%; --duration: 11s; --delay: 4.5s; animation: float14 11s ease-in-out infinite alternate; }
.stars-background span:nth-child(15) { left: 60%; top: 85%; --duration: 13s; --delay: 0.2s; animation: float15 13s ease-in-out infinite alternate; }
.stars-background span:nth-child(16) { left: 80%; top: 95%; --duration: 16s; --delay: 3.8s; animation: float16 16s ease-in-out infinite alternate; }
.stars-background span:nth-child(17) { left: 5%; top: 45%; --duration: 10s; --delay: 1.8s; animation: float17 10s ease-in-out infinite alternate; }
.stars-background span:nth-child(18) { left: 50%; top: 10%; --duration: 15s; --delay: 4.2s; animation: float18 15s ease-in-out infinite alternate; }
.stars-background span:nth-child(19) { left: 30%; top: 55%; --duration: 12s; --delay: 0.3s; animation: float19 12s ease-in-out infinite alternate; }
.stars-background span:nth-child(20) { left: 90%; top: 35%; --duration: 14s; --delay: 2.2s; animation: float20 14s ease-in-out infinite alternate; }
.stars-background span:nth-child(21) { left: 15%; top: 60%; --duration: 11s; --delay: 3.1s; animation: float21 11s ease-in-out infinite alternate; }
.stars-background span:nth-child(22) { left: 75%; top: 70%; --duration: 13s; --delay: 0.7s; animation: float22 13s ease-in-out infinite alternate; }
.stars-background span:nth-child(23) { left: 45%; top: 20%; --duration: 16s; --delay: 4.8s; animation: float23 16s ease-in-out infinite alternate; }
.stars-background span:nth-child(24) { left: 60%; top: 45%; --duration: 10s; --delay: 1.3s; animation: float24 10s ease-in-out infinite alternate; }

@keyframes float1 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(30px, -20px) rotate(30deg); } }
@keyframes float2 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(-20px, 40px) rotate(-20deg); } }
@keyframes float3 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(40px, -10px) rotate(45deg); } }
@keyframes float4 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(-30px, -30px) rotate(-35deg); } }
@keyframes float5 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(20px, 20px) rotate(25deg); } }
@keyframes float6 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(-40px, 10px) rotate(-40deg); } }
@keyframes float7 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(25px, -35px) rotate(35deg); } }
@keyframes float8 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(-15px, 30px) rotate(-15deg); } }
@keyframes float9 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(45px, -5px) rotate(50deg); } }
@keyframes float10 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(-25px, -25px) rotate(-25deg); } }
@keyframes float11 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(10px, 50px) rotate(15deg); } }
@keyframes float12 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(-35px, -15px) rotate(-30deg); } }
@keyframes float13 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(35px, 15px) rotate(40deg); } }
@keyframes float14 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(-10px, -40px) rotate(-10deg); } }
@keyframes float15 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(50px, 5px) rotate(55deg); } }
@keyframes float16 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(-45px, -20px) rotate(-45deg); } }
@keyframes float17 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(15px, -45px) rotate(20deg); } }
@keyframes float18 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(-20px, 35px) rotate(-20deg); } }
@keyframes float19 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(30px, -30px) rotate(30deg); } }
@keyframes float20 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(-30px, 45px) rotate(-30deg); } }
@keyframes float21 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(20px, -15px) rotate(25deg); } }
@keyframes float22 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(-40px, 25px) rotate(-40deg); } }
@keyframes float23 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(25px, 10px) rotate(35deg); } }
@keyframes float24 { 0% { transform: translate(0, 0) rotate(0deg); } 100% { transform: translate(-15px, -10px) rotate(-15deg); } }

#top-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    padding: 10px 0;
    border-bottom: 1px solid var(--border-color);
    z-index: 2;
}
#user-info {
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
}
#avatar-container {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    overflow: hidden;
    background: var(--accent-color);
    flex-shrink: 0;
}
#avatar-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: none;
}
#avatar-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    font-weight: bold;
    font-size: 16px;
    color: #0a0a0a;
}
#username-display {
    color: var(--accent-color);
    font-weight: 600;
    font-size: 14px;
}
#balance {
    font-size: 18px;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--accent-color);
    transition: color 0.3s;
}
#balance-amount {
    font-weight: 700;
}
#deposit-btn, #bets-btn {
    background: var(--accent-color);
    border: none;
    border-radius: 8px;
    padding: 4px 10px;
    font-weight: bold;
    color: #0a0a0a;
    cursor: pointer;
    font-size: 12px;
    transition: background 0.3s;
}
#deposit-btn {
    border-radius: 50%;
    width: 28px;
    height: 28px;
    font-size: 20px;
    padding: 0;
}
#deposit-menu {
    background: var(--card-bg);
    border: 1px solid var(--accent-color);
    border-radius: 12px;
    padding: 16px;
    margin: 10px 0;
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    justify-content: center;
    z-index: 10;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    transition: border-color 0.3s;
}
.deposit-option {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 10px 20px;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.3s, filter 0.2s;
}
.deposit-option:hover { filter: brightness(1.1); }
#close-deposit {
    background: transparent;
    color: var(--accent-color);
    border: none;
    font-size: 20px;
    cursor: pointer;
    transition: color 0.3s;
}

#main-title {
    text-align: center;
    margin: 20px 0 10px;
    z-index: 2;
}
#main-title h1 {
    font-size: 24px;
    font-weight: 900;
    color: var(--accent-color);
    letter-spacing: 2px;
    text-shadow: 0 0 10px var(--accent-glow);
    transition: color 0.3s, text-shadow 0.3s;
}
#main-title p {
    color: #aaa;
    font-size: 14px;
    margin-top: 4px;
}

#mode-selector {
    display: flex;
    gap: 12px;
    margin: 10px 0 20px;
    justify-content: center;
    z-index: 2;
}
.mode-btn {
    background: #222;
    color: #aaa;
    border: none;
    padding: 6px 18px;
    border-radius: 20px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
    font-size: 13px;
}
.mode-btn.active {
    background: var(--accent-color);
    color: #0a0a0a;
    box-shadow: 0 0 15px var(--accent-glow);
}

#key-container {
    display: flex;
    justify-content: center;
    align-items: center;
    margin: 10px 0 20px;
}
#key-display {
    font-size: 80px;
    color: var(--key-color);
    text-shadow: 0 0 30px var(--accent-glow);
    transition: color 0.3s, text-shadow 0.3s;
}

#spin-area {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin: 15px 0;
    z-index: 2;
}
#spin-info {
    font-size: 14px;
    color: #aaa;
    margin-bottom: 8px;
}
#spin-btn {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 14px 40px;
    border-radius: 30px;
    font-weight: 700;
    font-size: 18px;
    cursor: pointer;
    box-shadow: 0 0 20px var(--accent-glow);
    transition: transform 0.1s, box-shadow 0.3s, background 0.3s;
    display: flex;
    flex-direction: column;
    align-items: center;
    line-height: 1.2;
}
#spin-btn:active {
    transform: scale(0.95);
}
#spin-btn span {
    font-size: 14px;
    font-weight: 400;
}
#result-message {
    margin: 10px 0;
    font-size: 18px;
    font-weight: 600;
    min-height: 40px;
    text-align: center;
    z-index: 2;
    color: var(--accent-color);
    text-shadow: 0 0 10px var(--accent-glow);
    transition: color 0.3s, text-shadow 0.3s;
}

#slot-machine {
    background: var(--card-bg);
    border-radius: 20px;
    padding: 20px;
    margin: 10px 0;
    border: 2px solid var(--accent-color);
    box-shadow: 0 0 30px var(--accent-glow);
    width: 100%;
    max-width: 400px;
}
#reels {
    display: flex;
    justify-content: center;
    gap: 20px;
    padding: 20px 0;
}
.reel {
    width: 85px;
    height: 100px;
    background: #222;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 56px;
    border: 2px solid var(--border-color);
    box-shadow: inset 0 0 15px rgba(0,0,0,0.5);
    transition: transform 0.1s;
}
.reel.spinning {
    animation: spin 0.2s steps(1) infinite;
}
@keyframes spin {
    0% { transform: rotate(0deg); }
    25% { transform: rotate(90deg); }
    50% { transform: rotate(180deg); }
    75% { transform: rotate(270deg); }
    100% { transform: rotate(360deg); }
}
#slot-controls {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    margin-top: 10px;
}
.bet-control {
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
}
.bet-control label {
    font-size: 14px;
    color: #ccc;
}
#bet-range {
    width: 80%;
    max-width: 250px;
    margin-top: 5px;
    accent-color: var(--accent-color);
}
#slot-multiplier {
    font-size: 14px;
    color: #aaa;
    margin-top: 4px;
}
#slot-multiplier b {
    color: var(--accent-color);
}
#spin-slot-btn {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 14px 30px;
    border-radius: 30px;
    font-weight: 700;
    font-size: 18px;
    cursor: pointer;
    box-shadow: 0 0 20px var(--accent-glow);
    transition: transform 0.1s, box-shadow 0.3s, background 0.3s;
    width: 100%;
    max-width: 280px;
}
#spin-slot-btn:active {
    transform: scale(0.95);
}
#slot-result {
    margin-top: 15px;
    font-size: 18px;
    font-weight: 600;
    text-align: center;
    color: var(--accent-color);
    min-height: 30px;
}

#rocket-game {
    background: var(--card-bg);
    border-radius: 20px;
    padding: 20px;
    margin: 10px 0;
    border: 2px solid var(--accent-color);
    box-shadow: 0 0 30px var(--accent-glow);
    width: 100%;
    max-width: 400px;
}
#rocket-display {
    text-align: center;
    padding: 10px 0;
}
#rocket-multiplier {
    font-size: 48px;
    font-weight: 900;
    color: var(--accent-color);
    text-shadow: 0 0 20px var(--accent-glow);
    transition: color 0.3s;
}
#rocket-status {
    font-size: 16px;
    color: #aaa;
    margin-top: 5px;
}
#rocket-canvas-container {
    width: 100%;
    text-align: center;
}
#rocketCanvas {
    width: 100%;
    height: auto;
    background: #0a0a0a;
    border-radius: 12px;
}
#rocket-bet-control {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin: 10px 0;
}
#rocket-bet-control label {
    font-size: 14px;
    color: #ccc;
}
#rocket-bet-range {
    width: 80%;
    max-width: 250px;
    margin-top: 5px;
    accent-color: var(--accent-color);
}
#rocket-buttons {
    display: flex;
    justify-content: center;
    gap: 12px;
    margin: 15px 0;
}
#rocket-start-btn, #rocket-cashout-btn {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 12px 30px;
    border-radius: 30px;
    font-weight: 700;
    font-size: 18px;
    cursor: pointer;
    box-shadow: 0 0 20px var(--accent-glow);
    transition: transform 0.1s, box-shadow 0.3s, background 0.3s;
    flex: 1;
    max-width: 150px;
}
#rocket-start-btn:disabled, #rocket-cashout-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}
#rocket-start-btn:active, #rocket-cashout-btn:active {
    transform: scale(0.95);
}
#rocket-timer {
    font-size: 14px;
    color: #aaa;
    margin: 5px 0;
    text-align: center;
}
#rocket-timer span {
    color: var(--accent-color);
}
#rocket-result {
    margin-top: 10px;
    font-size: 18px;
    font-weight: 600;
    text-align: center;
    color: var(--accent-color);
    min-height: 30px;
}

#notification-feed {
    width: 100%;
    max-width: 400px;
    background: var(--card-bg);
    border-radius: 12px;
    padding: 12px;
    margin: 20px 0;
    z-index: 2;
    border: 1px solid var(--border-color);
}
#notification-feed h3 {
    color: var(--accent-color);
    margin-bottom: 8px;
    font-size: 16px;
    transition: color 0.3s;
}
#feed-list {
    list-style: none;
    max-height: 150px;
    overflow-y: auto;
}
#feed-list li {
    padding: 6px 0;
    border-bottom: 1px solid var(--border-color);
    font-size: 13px;
    color: #ddd;
}

#withdraw-btn {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 12px 30px;
    border-radius: 30px;
    font-weight: 700;
    font-size: 16px;
    margin-top: 10px;
    cursor: pointer;
    box-shadow: 0 0 15px var(--accent-glow);
    z-index: 2;
    transition: background 0.3s, box-shadow 0.3s;
}
#promo-area {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    align-items: center;
    gap: 8px;
    margin: 10px 0;
    z-index: 2;
    width: 100%;
    max-width: 400px;
}
#promo-input {
    flex: 1;
    min-width: 140px;
    padding: 8px 14px;
    border-radius: 20px;
    border: 1px solid var(--accent-color);
    background: #222;
    color: #fff;
    outline: none;
    font-size: 14px;
    transition: border-color 0.3s, box-shadow 0.3s;
    text-align: center;
}
#promo-input:focus {
    border-color: var(--accent-color);
    box-shadow: 0 0 10px var(--accent-glow);
}
#promo-btn {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 8px 20px;
    border-radius: 20px;
    font-weight: bold;
    font-size: 14px;
    cursor: pointer;
    transition: background 0.3s, box-shadow 0.3s;
    box-shadow: 0 0 10px var(--accent-glow);
}
#promo-btn:active {
    transform: scale(0.95);
}
#promo-message {
    width: 100%;
    font-size: 14px;
    text-align: center;
    min-height: 20px;
    color: var(--accent-color);
    transition: color 0.3s;
}

#bottom-nav {
    position: fixed;
    bottom: 0;
    left: 0;
    width: 100%;
    background: #111;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px;
    border-top: 1px solid var(--border-color);
    z-index: 10;
}
.nav-btn {
    background: transparent;
    color: #888;
    border: none;
    font-size: 14px;
    font-weight: 600;
    padding: 6px 12px;
    border-radius: 20px;
    cursor: pointer;
    transition: 0.2s;
}
.nav-btn.active {
    color: var(--accent-color);
    background: rgba(255,215,0,0.1);
}

#bets-modal ul li {
    padding: 8px 0;
    border-bottom: 1px solid var(--border-color);
    color: #ddd;
    font-size: 14px;
}
#bets-modal ul li span.positive {
    color: #4CAF50;
}
#bets-modal ul li span.negative {
    color: #f44336;
}

#wheel-wrapper {
    display: none;
    justify-content: center;
    margin: 10px 0 5px;
}
#wheel-container {
    position: relative;
    width: 100%;
    max-width: 400px;
    height: 120px;
    overflow: hidden;
    border: 3px solid var(--accent-color);
    border-radius: 16px;
    background: #111;
    box-shadow: 0 0 30px var(--accent-glow);
    margin: 0 auto;
}
#wheel-strip {
    display: flex;
    height: 100%;
    align-items: center;
    gap: 4px;
    padding: 0 10px;
    will-change: transform;
    transition: none;
    min-width: 100%;
    width: max-content;
}
.wheel-cell {
    flex: 0 0 60px;
    height: 80px;
    background: #222;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 36px;
    border: 2px solid #444;
    box-shadow: inset 0 0 10px rgba(0,0,0,0.5);
    transition: border-color 0.3s, box-shadow 0.3s;
    flex-shrink: 0;
}
.wheel-cell.win-cell {
    border-color: #4CAF50;
    box-shadow: 0 0 20px #4CAF5066;
}
.wheel-cell.lose-cell {
    border-color: #f44336;
    box-shadow: 0 0 20px #f4433666;
}
#wheel-arrow {
    position: absolute;
    top: -10px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 36px;
    color: var(--accent-color);
    text-shadow: 0 0 20px var(--accent-glow);
    pointer-events: none;
    z-index: 5;
    line-height: 1;
}

#logout-btn:hover {
    color: #ff1744 !important;
}
""")

# JavaScript
with open(os.path.join(STATIC_DIR, "script.js"), "w", encoding="utf-8") as f:
    f.write("""const BASE_URL = window.location.origin;
let current_user = null;
let balance = 0;
let currentMode = 'light';
let isSpinning = false;

// ========== ЭКРАН ВХОДА ==========
document.getElementById('login-btn').addEventListener('click', async () => {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value.trim();
    const errorEl = document.getElementById('login-error');
    
    if (!username || !password) {
        errorEl.textContent = 'Заполните все поля!';
        return;
    }
    
    if (username.length < 3) {
        errorEl.textContent = 'Имя должно быть минимум 3 символа!';
        return;
    }
    
    if (password.length < 3) {
        errorEl.textContent = 'Пароль должен быть минимум 3 символа!';
        return;
    }
    
    errorEl.textContent = 'Загрузка...';
    
    try {
        const resp = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await resp.json();
        
        if (resp.ok) {
            current_user = data;
            balance = data.balance;
            document.getElementById('login-screen').style.display = 'none';
            document.getElementById('app-content').style.display = 'block';
            document.getElementById('balance-amount').textContent = balance;
            document.getElementById('username-display').textContent = '@' + username;
            document.getElementById('avatar-placeholder').textContent = username.charAt(0).toUpperCase();
            initGames();
            if (data.telegram_id) {
                loadAvatar(data.telegram_id);
            }
        } else {
            errorEl.textContent = data.detail || 'Ошибка входа';
        }
    } catch (e) {
        errorEl.textContent = 'Ошибка соединения с сервером';
        console.error(e);
    }
});

// Enter key для входа
document.getElementById('login-password').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') document.getElementById('login-btn').click();
});
document.getElementById('login-username').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') document.getElementById('login-btn').click();
});

async function loadAvatar(telegramId) {
    try {
        const resp = await fetch(`/api/avatar/${telegramId}`);
        const data = await resp.json();
        if (data.url) {
            const img = document.getElementById('avatar-img');
            img.src = data.url;
            img.style.display = 'block';
            document.getElementById('avatar-placeholder').style.display = 'none';
        }
    } catch (e) {
        console.error('Avatar load error:', e);
    }
}

async function fetchUserData() {
    if (!current_user) return;
    try {
        const resp = await fetch(`/api/user/${current_user.id}`);
        const data = await resp.json();
        if (resp.ok) {
            balance = data.balance;
            document.getElementById('balance-amount').textContent = balance;
        }
    } catch (e) {
        console.error('Ошибка загрузки пользователя:', e);
    }
}

function updateBalanceUI(newBalance) {
    balance = newBalance;
    document.getElementById('balance-amount').textContent = newBalance;
}

document.getElementById('user-info').addEventListener('click', async () => {
    if (!current_user) return;
    try {
        const resp = await fetch(`/api/referral/${current_user.id}`);
        const data = await resp.json();
        document.getElementById('ref-link').textContent = data.link;
        document.getElementById('ref-count').textContent = data.count;
        document.getElementById('referral-modal').style.display = 'flex';
    } catch (e) {
        alert('Ошибка загрузки реферальной информации');
    }
});

document.getElementById('close-ref-modal').addEventListener('click', () => {
    document.getElementById('referral-modal').style.display = 'none';
});
document.getElementById('referral-modal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) document.getElementById('referral-modal').style.display = 'none';
});

document.getElementById('copy-ref-link').addEventListener('click', () => {
    const link = document.getElementById('ref-link').textContent;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(() => alert('Ссылка скопирована!'))
            .catch(() => fallbackCopy(link));
    } else fallbackCopy(link);
});

function fallbackCopy(text) {
    const input = document.createElement('input');
    input.style.position = 'fixed';
    input.style.opacity = '0';
    input.value = text;
    document.body.appendChild(input);
    input.select();
    try { document.execCommand('copy'); alert('Ссылка скопирована!'); } 
    catch (e) { alert('Не удалось скопировать, скопируйте вручную: ' + text); }
    document.body.removeChild(input);
}

document.getElementById('bets-btn').addEventListener('click', async () => {
    if (!current_user) return;
    try {
        const resp = await fetch(`/api/user_bets/${current_user.id}`);
        const bets = await resp.json();
        const list = document.getElementById('bets-list');
        list.innerHTML = '';
        if (bets.length === 0) list.innerHTML = '<li style="color:#aaa;">Ставок пока нет</li>';
        else bets.forEach(b => {
            const li = document.createElement('li');
            let sign = '', cls = '';
            if (b.amount > 0) { sign = '+'; cls = 'positive'; }
            else if (b.amount < 0) { sign = ''; cls = 'negative'; }
            else { sign = '0'; cls = ''; }
            li.innerHTML = `<span class="${cls}">${sign}${b.amount}</span> ${b.description} <span style="color:#888;font-size:12px;">${new Date(b.created_at).toLocaleString()}</span>`;
            list.appendChild(li);
        });
        document.getElementById('bets-modal').style.display = 'flex';
    } catch (e) { alert('Ошибка загрузки ставок'); console.error(e); }
});

document.getElementById('close-bets-modal').addEventListener('click', () => {
    document.getElementById('bets-modal').style.display = 'none';
});
document.getElementById('bets-modal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) document.getElementById('bets-modal').style.display = 'none';
});

document.getElementById('promo-btn').addEventListener('click', async () => {
    if (!current_user) return;
    const input = document.getElementById('promo-input');
    const code = input.value.trim();
    const msg = document.getElementById('promo-message');
    if (!code) { msg.textContent = 'Введите промокод'; return; }
    try {
        const resp = await fetch('/api/activate_promo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: current_user.id, code })
        });
        const data = await resp.json();
        if (resp.ok) {
            msg.textContent = '✅ ' + data.message;
            input.value = '';
            balance = data.new_balance;
            document.getElementById('balance-amount').textContent = balance;
        } else msg.textContent = '❌ ' + data.detail;
    } catch (e) { msg.textContent = 'Ошибка соединения'; console.error(e); }
});

function initGames() {
    applyTheme('light');
    updateKeyColor('light');
    updateSpinCost();
    const initialBet = parseInt(document.getElementById('bet-range').value);
    document.getElementById('bet-display').textContent = initialBet;
    drawRocket(0, 'idle');
    document.getElementById('rocket-countdown').textContent = '0';
    startAutoRocket();
    startFakeWins();
    buildRouletteStrip();
}

// ========== РУЛЕТКА (БЕСКОНЕЧНЫЕ СЛОТЫ) ==========
function buildRouletteStrip() {
    const strip = document.getElementById('wheel-strip');
    strip.innerHTML = '';
    const symbols = ['❌', '🎫'];
    // 2000 слотов для полной уверенности
    for (let i = 0; i < 2000; i++) {
        const cell = document.createElement('div');
        cell.className = 'wheel-cell';
        cell.dataset.index = i;
        cell.textContent = symbols[i % 2];
        strip.appendChild(cell);
    }
}

function animateRouletteWheel(win) {
    return new Promise((resolve) => {
        const container = document.getElementById('wheel-container');
        const strip = document.getElementById('wheel-strip');
        const cells = strip.children;
        const cellWidth = cells[0].offsetWidth + 4;
        const containerWidth = container.offsetWidth;

        const targetSymbol = win ? '🎫' : '❌';
        
        let targetIndex = -1;
        const startRange = 550;
        const endRange = 580;
        
        for (let i = startRange; i <= endRange && i < cells.length; i++) {
            if (cells[i].textContent === targetSymbol) {
                targetIndex = i;
                break;
            }
        }
        
        if (targetIndex === -1) {
            for (let i = 0; i < cells.length; i++) {
                if (cells[i].textContent === targetSymbol) {
                    targetIndex = i;
                    break;
                }
            }
        }
        if (targetIndex === -1) targetIndex = startRange;

        let targetOffset = targetIndex * cellWidth + cellWidth/2 - containerWidth/2;
        // Много оборотов для долгого вращения
        const extraLoops = 20 + Math.floor(Math.random() * 10);
        const totalOffset = targetOffset + extraLoops * cells.length * cellWidth;

        strip.style.transform = `translateX(0px)`;

        const duration = 15000;
        const startTime = performance.now();
        const startOffset = 0;

        function easeOutCubic(t) {
            return 1 - Math.pow(1 - t, 3);
        }

        function animate(now) {
            const elapsed = now - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const easedProgress = easeOutCubic(progress);
            const currentOffset = startOffset + (totalOffset - startOffset) * easedProgress;
            strip.style.transform = `translateX(-${currentOffset}px)`;

            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                resolve();
            }
        }
        requestAnimationFrame(animate);
    });
}

document.getElementById('spin-btn').addEventListener('click', async () => {
    if (!current_user || isSpinning) return;
    const cost = { light:25, normal:50, hard:100 }[currentMode];
    if (balance < cost) {
        document.getElementById('result-message').textContent = '❌ Недостаточно токенов!';
        return;
    }
    isSpinning = true;
    const btn = document.getElementById('spin-btn');
    btn.disabled = true;
    btn.innerHTML = 'КРУТИТЬ <span>Загрузка...</span>';
    document.getElementById('result-message').textContent = '';

    document.getElementById('key-container').style.display = 'none';
    const wheelWrapper = document.getElementById('wheel-wrapper');
    wheelWrapper.style.display = 'flex';
    buildRouletteStrip();

    try {
        const resp = await fetch('/api/spin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: current_user.id, mode: currentMode })
        });
        const data = await resp.json();
        if (resp.ok) {
            await animateRouletteWheel(data.win);
            updateBalanceUI(data.new_balance);
            document.getElementById('result-message').textContent = data.message;
            document.getElementById('result-message').style.color = data.win ? '#4CAF50' : '#f44336';
            if (data.win) {
                addFakeWinToFeed(current_user.username, data.prize_name, data.prize_value);
            }
            setTimeout(() => {
                document.getElementById('key-container').style.display = 'flex';
                document.getElementById('wheel-wrapper').style.display = 'none';
            }, 3000);
        } else {
            document.getElementById('result-message').textContent = '❌ ' + data.detail;
        }
    } catch (e) {
        document.getElementById('result-message').textContent = 'Ошибка соединения';
        console.error(e);
    }
    isSpinning = false;
    btn.disabled = false;
    const cost2 = { light:25, normal:50, hard:100 }[currentMode];
    btn.innerHTML = 'КРУТИТЬ <span>' + cost2 + ' Токенов</span>';
});

// ========== СЛОТ-МАШИНА ==========
let slotSpinning = false;
const slotSymbols = ['🍒','🍋','🍊','🍇','🍉','🍓','🍑','🎰'];
const reels = [
    document.getElementById('reel1'),
    document.getElementById('reel2'),
    document.getElementById('reel3')
];
document.getElementById('bet-range').addEventListener('input', function() {
    document.getElementById('bet-display').textContent = this.value;
});
document.getElementById('spin-slot-btn').addEventListener('click', async () => {
    if (!current_user || slotSpinning) return;
    const bet = parseInt(document.getElementById('bet-range').value);
    if (isNaN(bet) || bet<20 || bet>100) { alert('Ставка от 20 до 100'); return; }
    if (balance < bet) { alert('Недостаточно токенов!'); return; }
    slotSpinning = true;
    const btn = document.getElementById('spin-slot-btn');
    btn.disabled = true;
    btn.textContent = '🎰 Крутим...';
    let interval = setInterval(() => {
        reels.forEach(reel => {
            reel.textContent = slotSymbols[Math.floor(Math.random()*slotSymbols.length)];
        });
    }, 100);
    try {
        const resp = await fetch('/api/slot_spin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: current_user.id, bet })
        });
        const data = await resp.json();
        clearInterval(interval);
        if (resp.ok) {
            reels[0].textContent = data.symbols[0];
            reels[1].textContent = data.symbols[1];
            reels[2].textContent = data.symbols[2];
            updateBalanceUI(data.new_balance);
            const resultDiv = document.getElementById('slot-result');
            if (data.win) {
                resultDiv.textContent = '🎉 ВЫИГРЫШ! +' + data.win_amount + ' токенов!';
                resultDiv.style.color = '#4CAF50';
                addFakeWinToFeed(current_user.username, '🎰 Слот', data.win_amount);
            } else {
                resultDiv.textContent = '😞 Проигрыш. -' + bet + ' токенов';
                resultDiv.style.color = '#f44336';
            }
        } else {
            document.getElementById('slot-result').textContent = '❌ ' + data.detail;
        }
    } catch (e) {
        clearInterval(interval);
        document.getElementById('slot-result').textContent = 'Ошибка соединения';
        console.error(e);
    }
    slotSpinning = false;
    btn.disabled = false;
    btn.textContent = 'Дёрнуть рычаг 🎰';
});

// ========== РАКЕТКА ==========
let rocketInterval = null, rocketRoundId = null, rocketActive = false;
let rocketCountdown = 5, countdownInterval = null, rocketAnimationFrame = null;
const rocketCanvas = document.getElementById('rocketCanvas');
const rctx = rocketCanvas.getContext('2d');
let rocketX = 30, rocketY = 170;
let rocketTrail = [];
let isCrashed = false;
let falling = false;
let fallY = 0;
let explosionX = 0, explosionY = 0;
let startTime = 0;
let isRocketRoundFinished = true;

function drawRocket(multiplier, status) {
    const ctx = rctx;
    const width = rocketCanvas.width;
    const height = rocketCanvas.height;
    
    ctx.clearRect(0, 0, width, height);
    
    if (rocketTrail.length > 1 && status !== 'crashed' && status !== 'idle') {
        ctx.beginPath();
        ctx.moveTo(rocketTrail[0].x, rocketTrail[0].y);
        for (let i = 1; i < rocketTrail.length; i++) {
            ctx.lineTo(rocketTrail[i].x, rocketTrail[i].y);
        }
        ctx.strokeStyle = 'rgba(255,215,0,0.3)';
        ctx.lineWidth = 2;
        ctx.stroke();
    }
    
    if (status === 'crashed') {
        ctx.font = '40px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('💥', explosionX, explosionY);
        if (falling) {
            ctx.font = '20px sans-serif';
            ctx.fillText('🚀', rocketX, fallY);
        }
        return;
    }
    
    if (status === 'idle') {
        ctx.font = '24px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('🚀', 30, 170);
        return;
    }
    
    ctx.font = '24px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('🚀', rocketX, rocketY);
    
    ctx.fillStyle = '#ffd700';
    ctx.font = '12px sans-serif';
    ctx.fillText(multiplier.toFixed(2) + 'x', rocketX, rocketY - 25);
}

document.getElementById('rocket-bet-range').addEventListener('input', function() {
    document.getElementById('rocket-bet-display').textContent = this.value;
});

document.getElementById('rocket-start-btn').addEventListener('click', async () => {
    if (!current_user || rocketActive || !isRocketRoundFinished) return;
    
    const bet = parseInt(document.getElementById('rocket-bet-range').value);
    if (isNaN(bet) || bet<100 || bet>1000) { alert('Ставка от 100 до 1000'); return; }
    if (balance < bet) { alert('Недостаточно токенов!'); return; }
    
    isRocketRoundFinished = false;
    if (rocketInterval) clearInterval(rocketInterval);
    if (rocketAnimationFrame) cancelAnimationFrame(rocketAnimationFrame);
    rocketTrail = [];
    isCrashed = false;
    falling = false;
    
    try {
        const resp = await fetch('/api/rocket/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: current_user.id, bet })
        });
        const data = await resp.json();
        if (resp.ok) {
            rocketRoundId = data.round_id;
            rocketActive = true;
            document.getElementById('rocket-start-btn').disabled = true;
            document.getElementById('rocket-cashout-btn').disabled = false;
            document.getElementById('rocket-result').textContent = '';
            document.getElementById('rocket-status').textContent = '🚀 Взлёт!';
            document.getElementById('rocket-multiplier').textContent = '0.00';
            rocketX = 30;
            rocketY = 170;
            rocketTrail = [{x:rocketX, y:rocketY}];
            startTime = Date.now();
            if (rocketInterval) clearInterval(rocketInterval);
            rocketInterval = setInterval(updateRocketStatus, 150);
            if (rocketAnimationFrame) cancelAnimationFrame(rocketAnimationFrame);
            animateRocket();
        } else alert('❌ ' + data.detail);
    } catch (e) { alert('Ошибка соединения'); console.error(e); }
});

function animateRocket() {
    if (!rocketActive && !falling) {
        if (!isRocketRoundFinished) {
            rocketAnimationFrame = requestAnimationFrame(animateRocket);
        }
        return;
    }
    if (isCrashed && !falling) {
        falling = true;
        fallY = rocketY;
        explosionX = rocketX;
        explosionY = rocketY - 15;
    }
    if (falling) {
        fallY += 3;
        if (fallY > rocketCanvas.height + 50) {
            falling = false;
            isCrashed = false;
            isRocketRoundFinished = true;
            drawRocket(0, 'idle');
            return;
        }
        drawRocket(0, 'crashed');
        rocketAnimationFrame = requestAnimationFrame(animateRocket);
        return;
    }
    if (!rocketActive) return;
    
    const elapsed = (Date.now() - startTime) / 1000;
    const speedFactor = 1 + elapsed * 0.06;
    const dx = 1.0 * speedFactor;
    const dy = 0.7 * speedFactor;
    rocketX += dx;
    rocketY -= dy;
    
    if (rocketX > 280) rocketX = 280;
    if (rocketY < 10) rocketY = 10;
    
    const sinOffset = 6 * Math.sin(elapsed * 1.0 + 0.5);
    let targetY = 170 - (rocketX - 30) * (160 / 250);
    rocketY = targetY + sinOffset;
    if (rocketY < 8) rocketY = 8;
    if (rocketY > 192) rocketY = 192;
    
    rocketTrail.push({x: rocketX, y: rocketY});
    if (rocketTrail.length > 80) rocketTrail.shift();
    
    const mult = parseFloat(document.getElementById('rocket-multiplier').textContent) || 0;
    drawRocket(mult, 'active');
    rocketAnimationFrame = requestAnimationFrame(animateRocket);
}

async function updateRocketStatus() {
    if (!rocketRoundId || isRocketRoundFinished) return;
    try {
        const resp = await fetch(`/api/rocket/status/${rocketRoundId}`);
        const data = await resp.json();
        if (resp.ok) {
            const display = data.display_multiplier;
            document.getElementById('rocket-multiplier').textContent = display.toFixed(2);
            if (data.crashed) {
                document.getElementById('rocket-status').textContent = '💥 Упала!';
                document.getElementById('rocket-cashout-btn').disabled = true;
                document.getElementById('rocket-start-btn').disabled = false;
                rocketActive = false;
                isCrashed = true;
                isRocketRoundFinished = true;
                if (rocketInterval) clearInterval(rocketInterval);
                animateRocket();
                document.getElementById('rocket-result').textContent = '😞 Ракета упала. Ставка проиграна.';
                document.getElementById('rocket-result').style.color = '#f44336';
                fetchUserData();
                startCountdown();
            } else if (data.cashed_out) {
                document.getElementById('rocket-status').textContent = '💰 Выведено!';
                document.getElementById('rocket-cashout-btn').disabled = true;
                document.getElementById('rocket-start-btn').disabled = false;
                rocketActive = false;
                isRocketRoundFinished = true;
                if (rocketInterval) clearInterval(rocketInterval);
                if (rocketAnimationFrame) cancelAnimationFrame(rocketAnimationFrame);
                fetchUserData();
                startCountdown();
            }
        } else console.error('Status error:', data);
    } catch (e) { console.error(e); }
}

document.getElementById('rocket-cashout-btn').addEventListener('click', async () => {
    if (!current_user || !rocketRoundId || !rocketActive || isRocketRoundFinished) return;
    try {
        const resp = await fetch('/api/rocket/cashout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ round_id: rocketRoundId, user_id: current_user.id })
        });
        const data = await resp.json();
        if (resp.ok) {
            document.getElementById('rocket-result').textContent = '🎉 Вы выиграли ' + data.win_amount + ' токенов!';
            document.getElementById('rocket-result').style.color = '#4CAF50';
            document.getElementById('rocket-status').textContent = '💰 Выведено!';
            document.getElementById('rocket-cashout-btn').disabled = true;
            document.getElementById('rocket-start-btn').disabled = false;
            rocketActive = false;
            isRocketRoundFinished = true;
            if (rocketInterval) clearInterval(rocketInterval);
            if (rocketAnimationFrame) cancelAnimationFrame(rocketAnimationFrame);
            updateBalanceUI(data.new_balance);
            addFakeWinToFeed(current_user.username, '🚀 Ракетка', data.win_amount);
            startCountdown();
        } else alert('❌ ' + data.detail);
    } catch (e) { alert('Ошибка соединения'); console.error(e); }
});

function startCountdown() {
    rocketCountdown = 5;
    document.getElementById('rocket-countdown').textContent = rocketCountdown;
    if (countdownInterval) clearInterval(countdownInterval);
    countdownInterval = setInterval(() => {
        rocketCountdown--;
        document.getElementById('rocket-countdown').textContent = rocketCountdown;
        if (rocketCountdown <= 0) {
            clearInterval(countdownInterval);
            countdownInterval = null;
            document.getElementById('rocket-countdown').textContent = '0';
            document.getElementById('rocket-start-btn').disabled = false;
        }
    }, 1000);
}

let autoRocketTimer = null;
function startAutoRocket() {
    if (autoRocketTimer) clearInterval(autoRocketTimer);
    autoRocketTimer = setInterval(() => {
        if (!rocketActive && isRocketRoundFinished) {
            const fakeBet = 100 + Math.floor(Math.random() * 900) * 10;
            simulateRocketRound(fakeBet);
        }
    }, 12000 + Math.random() * 18000);
}

function simulateRocketRound(bet) {
    const win = Math.random() < 0.35;
    const crashMultiplier = win ? 1.1 + Math.random() * 2.0 : 0.01 + Math.random() * 0.5;
    let progress = 0;
    const interval = setInterval(() => {
        progress += 0.02;
        if (progress >= 1) {
            clearInterval(interval);
            if (win) {
                const winAmount = Math.floor(bet * crashMultiplier);
                const fakeUsers = ['user_' + (100000 + Math.floor(Math.random()*900000)), 'player_' + (200000 + Math.floor(Math.random()*800000)), 'gamer_' + (300000 + Math.floor(Math.random()*700000))];
                const username = fakeUsers[Math.floor(Math.random()*fakeUsers.length)];
                addFakeWinToFeed(username, '🚀 Ракетка', winAmount);
            }
            document.getElementById('rocket-multiplier').textContent = '0.00';
            document.getElementById('rocket-status').textContent = 'Ожидание';
            drawRocket(0, 'idle');
            isRocketRoundFinished = true;
            return;
        }
        const currentMultiplier = win ? 1 + progress * crashMultiplier : progress * 0.3;
        document.getElementById('rocket-multiplier').textContent = currentMultiplier.toFixed(2);
        if (win) {
            document.getElementById('rocket-status').textContent = '🚀 Взлёт!';
            drawRocket(currentMultiplier, 'active');
        } else {
            if (progress > 0.3) {
                document.getElementById('rocket-status').textContent = '💥 Упала!';
                drawRocket(currentMultiplier, 'crashed');
                isRocketRoundFinished = true;
                clearInterval(interval);
            } else {
                document.getElementById('rocket-status').textContent = '🚀 Взлёт!';
                drawRocket(currentMultiplier, 'active');
            }
        }
    }, 150);
}

// ========== ДОПОЛНИТЕЛЬНЫЕ ФУНКЦИИ ==========
function startFakeWins() {
    setInterval(() => {
        const isWin = Math.random() < 0.75;
        const fakeUsers = ['user_' + (100000 + Math.floor(Math.random()*900000)), 
                           'player_' + (200000 + Math.floor(Math.random()*800000)), 
                           'gamer_' + (300000 + Math.floor(Math.random()*700000)), 
                           'winner_' + (400000 + Math.floor(Math.random()*600000))];
        const username = fakeUsers[Math.floor(Math.random()*fakeUsers.length)];
        const prizes = ['🎰 Слот', '🎡 Рулетка', '🚀 Ракетка', '🎁 Подарок'];
        const prize = prizes[Math.floor(Math.random()*prizes.length)];
        const amount = Math.floor(Math.random() * 150) + 10;
        if (isWin) {
            addFakeWinToFeed(username, prize, amount);
        } else {
            const loseMessages = ['проиграл', 'не повезло', 'удача отвернулась', 'мимо', 'сгорел'];
            const msg = loseMessages[Math.floor(Math.random() * loseMessages.length)];
            addFakeLoseToFeed(username, prize, msg);
        }
    }, 2000);
}
function addFakeWinToFeed(username, prize, amount) {
    const list = document.getElementById('feed-list');
    const li = document.createElement('li');
    li.textContent = '@' + username + ' выиграл ' + prize + ' (+' + amount + ' токенов) 🎉';
    list.insertBefore(li, list.firstChild);
    if (list.children.length > 10) list.removeChild(list.lastChild);
}
function addFakeLoseToFeed(username, prize, msg) {
    const list = document.getElementById('feed-list');
    const li = document.createElement('li');
    li.textContent = '@' + username + ' ' + msg + ' в ' + prize + ' 😞';
    list.insertBefore(li, list.firstChild);
    if (list.children.length > 10) list.removeChild(list.lastChild);
}

function applyTheme(mode) {
    document.body.classList.remove('theme-light', 'theme-normal', 'theme-hard');
    if (mode === 'light') document.body.classList.add('theme-light');
    else if (mode === 'normal') document.body.classList.add('theme-normal');
    else if (mode === 'hard') document.body.classList.add('theme-hard');
    updateKeyColor(mode);
}

function updateKeyColor(mode) {
    const keyDisplay = document.getElementById('key-display');
    if (mode === 'light') keyDisplay.textContent = '🔑';
    else if (mode === 'normal') keyDisplay.textContent = '🎟';
    else if (mode === 'hard') keyDisplay.textContent = '🎫';
}

document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (isSpinning) return;
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentMode = btn.dataset.mode;
        updateSpinCost();
        applyTheme(currentMode);
    });
});

function updateSpinCost() {
    const costs = { light: 25, normal: 50, hard: 100 };
    const cost = costs[currentMode];
    document.getElementById('spin-cost').textContent = cost;
    document.getElementById('spin-cost-label').textContent = cost + ' Токенов';
}

document.getElementById('deposit-btn').addEventListener('click', () => {
    const menu = document.getElementById('deposit-menu');
    menu.style.display = menu.style.display === 'none' ? 'flex' : 'none';
});

document.querySelectorAll('.deposit-option').forEach(btn => {
    btn.addEventListener('click', async () => {
        const amount = parseInt(btn.dataset.amount);
        if (!current_user) {
            alert('Ошибка авторизации.');
            return;
        }
        try {
            const resp = await fetch('/api/create_payment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: current_user.id, amount })
            });
            const data = await resp.json();
            if (resp.ok) {
                window.open(data.payment_url, '_blank');
                localStorage.setItem('current_order', data.order_id);
                alert('Ссылка на оплату открыта. После оплаты баланс обновится автоматически.');
            } else {
                alert('Ошибка: ' + data.detail);
            }
        } catch (e) {
            alert('Ошибка соединения');
            console.error(e);
        }
    });
});

document.getElementById('close-deposit').addEventListener('click', () => {
    document.getElementById('deposit-menu').style.display = 'none';
});

document.getElementById('withdraw-btn').addEventListener('click', async () => {
    if (!current_user) return;
    const amount = prompt('Введите сумму вывода (минимум 500 токенов):');
    if (!amount || isNaN(amount) || amount < 500) {
        alert('Введите корректное число не менее 500');
        return;
    }
    try {
        const resp = await fetch('/api/withdraw', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: current_user.id, amount: parseInt(amount) })
        });
        const data = await resp.json();
        if (resp.ok) {
            alert('✅ Заявка на вывод отправлена!');
            fetchUserData();
        } else alert('❌ ' + data.detail);
    } catch (e) { alert('Ошибка соединения'); console.error(e); }
});

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.dataset.tab;
        document.getElementById('roulette-page').style.display = tab==='roulette' ? 'block' : 'none';
        document.getElementById('slot-page').style.display = tab==='slot' ? 'block' : 'none';
        document.getElementById('rocket-page').style.display = tab==='rocket' ? 'block' : 'none';
        if (tab==='roulette') {
            document.getElementById('key-container').style.display = 'flex';
            document.getElementById('wheel-wrapper').style.display = 'none';
        }
        if (tab==='rocket') {
            fetchUserData();
            if (!rocketActive) {
                isRocketRoundFinished = true;
                document.getElementById('rocket-start-btn').disabled = false;
                document.getElementById('rocket-cashout-btn').disabled = true;
            }
        }
    });
});

document.getElementById('logout-btn').addEventListener('click', () => {
    if (confirm('Вы уверены, что хотите выйти?')) {
        current_user = null;
        document.getElementById('app-content').style.display = 'none';
        document.getElementById('login-screen').style.display = 'flex';
        document.getElementById('login-username').value = '';
        document.getElementById('login-password').value = '';
        document.getElementById('login-error').textContent = '';
        if (rocketInterval) clearInterval(rocketInterval);
        if (countdownInterval) clearInterval(countdownInterval);
        if (rocketAnimationFrame) cancelAnimationFrame(rocketAnimationFrame);
        rocketActive = false;
        isRocketRoundFinished = true;
    }
});
""")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")

@app.head("/")
async def root_head():
    return RedirectResponse(url="/static/index.html")

@app.post("/webhook")
async def webhook(request: Request):
    update = types.Update(**(await request.json()))
    await dp.feed_update(bot, update)
    return {"status": "ok"}

# ==================== API МОДЕЛИ ====================
class LoginRequest(BaseModel):
    username: str
    password: str

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

class PaymentRequest(BaseModel):
    user_id: int
    amount: int

class RegisterRequest(BaseModel):
    username: str
    password: str
    telegram_id: int = None

class YookassaNotification(BaseModel):
    event: str
    object: dict

# ==================== API ЭНДПОИНТЫ ====================
@app.post("/api/login")
async def api_login(data: LoginRequest):
    user = login_user(data.username, data.password)
    if not user:
        new_user = create_user(data.username, data.password)
        if new_user:
            return {"id": new_user["id"], "username": new_user["username"], "balance": new_user["balance"], "telegram_id": new_user["telegram_id"]}
        else:
            raise HTTPException(status_code=400, detail="Имя пользователя уже занято!")
    return {"id": user["id"], "username": user["username"], "balance": user["balance"], "telegram_id": user["telegram_id"]}

@app.post("/api/register_telegram")
async def register_telegram(data: RegisterRequest):
    user = get_user_by_username(data.username)
    if user:
        raise HTTPException(status_code=400, detail="Имя пользователя уже занято!")
    new_user = create_user(data.username, data.password, data.telegram_id)
    if not new_user:
        raise HTTPException(status_code=400, detail="Ошибка создания пользователя")
    return {"id": new_user["id"], "username": new_user["username"], "balance": new_user["balance"]}

@app.post("/api/create_payment")
async def create_payment(data: PaymentRequest):
    user = get_user_by_id(data.user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if data.amount not in PAYMENT_LINKS:
        raise HTTPException(400, "Invalid amount")
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT INTO orders (user_id, username, amount, status) VALUES (?, ?, ?, 'pending')", 
                (data.user_id, user["username"], data.amount))
    order_id = cur.lastrowid
    conn.commit()
    conn.close()
    payment_url = PAYMENT_LINKS[data.amount]
    return {"payment_url": payment_url, "order_id": order_id}

@app.post("/api/payment_callback")
async def payment_callback(notification: YookassaNotification):
    if notification.event == "payment.succeeded":
        payment_id = notification.object.get("id")
        amount = notification.object.get("amount", {}).get("value")
        if amount is None:
            return {"error": "No amount"}
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("SELECT id, user_id FROM orders WHERE amount = ? AND status = 'pending' ORDER BY id DESC LIMIT 1", 
                    (int(float(amount)),))
        order = cur.fetchone()
        if not order:
            conn.close()
            return {"error": "Order not found"}
        order_id, user_id = order
        tokens = int(float(amount))
        update_balance(user_id, tokens, f"Пополнение через ЮKassa (заказ {order_id})")
        cur.execute("UPDATE orders SET status = 'paid', payment_id = ? WHERE id = ?", 
                    (payment_id, order_id))
        conn.commit()
        conn.close()
        return {"status": "ok"}
    return {"status": "ignored"}

@app.get("/api/user/{user_id}")
async def api_get_user(user_id: int):
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] == 0:
        conn = sqlite3.connect(DB_NAME)
        cur = conn.cursor()
        cur.execute("UPDATE users SET balance = ? WHERE id = ?", (START_BALANCE, user_id))
        cur.execute(
            "INSERT INTO transactions (user_id, username, type, amount, description) VALUES (?, ?, ?, ?, ?)",
            (user_id, user["username"], "deposit", START_BALANCE, "Стартовый бонус 50 токенов (восстановлен через API)")
        )
        conn.commit()
        conn.close()
        user["balance"] = START_BALANCE
    return {"balance": user["balance"], "username": user["username"]}

@app.get("/api/user_bets/{user_id}")
async def api_user_bets(user_id: int):
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    bets = get_user_bets(user_id, 50)
    return bets

@app.post("/api/spin")
async def api_spin(data: SpinRequest):
    user_id = data.user_id
    mode = data.mode
    cost = SPIN_COSTS.get(mode, 25)
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] < cost:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    update_balance(user_id, -cost, f"Спин в режиме {mode}")
    win, prize_name, prize_value = get_next_spin_result(user_id, mode)
    if win:
        update_balance(user_id, prize_value, f"Выигрыш: {prize_name}")
        add_win(user_id, prize_name, prize_value, mode)
        message = f"🎉 Вы выиграли {prize_name} (+{prize_value} токенов)!"
    else:
        message = "😞 К сожалению, вы проиграли. Попробуйте ещё раз!"
    new_balance = get_user_by_id(user_id)["balance"]
    await asyncio.sleep(1)
    return {
        "win": win,
        "prize_name": prize_name if win else None,
        "prize_value": prize_value if win else 0,
        "new_balance": new_balance,
        "message": message
    }

@app.post("/api/slot_spin")
async def api_slot_spin(data: SlotSpinRequest):
    user_id = data.user_id
    bet = data.bet
    if bet < 20 or bet > 100:
        raise HTTPException(status_code=400, detail="Ставка должна быть от 20 до 100 токенов")
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] < bet:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    update_balance(user_id, -bet, f"Ставка в игровом автомате {bet} токенов")
    win, symbols, win_amount = get_slot_result(bet)
    if win:
        update_balance(user_id, win_amount, f"Выигрыш в игровом автомате {win_amount} токенов")
        add_win(user_id, f"🎰 {symbols[0]}{symbols[1]}{symbols[2]}", win_amount, "slot")
    new_balance = get_user_by_id(user_id)["balance"]
    await asyncio.sleep(1)
    return {
        "win": win,
        "symbols": symbols,
        "win_amount": win_amount if win else 0,
        "new_balance": new_balance
    }

@app.post("/api/rocket/start")
async def rocket_start(data: RocketStartRequest):
    user_id = data.user_id
    bet = data.bet
    if bet < 100 or bet > 1000:
        raise HTTPException(status_code=400, detail="Ставка должна быть от 100 до 1000 токенов")
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] < bet:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    update_balance(user_id, -bet, f"Ставка в ракетке {bet} токенов")
    
    # НОВАЯ ЛОГИКА ВЗРЫВА РАКЕТКИ
    # От 0.00 до 1.00: 70% шанс взрыва (проигрыш)
    # От 1.00 до 2.50: 90% шанс взрыва (редкий выигрыш)
    crash_display = random.uniform(0.01, 2.50)
    
    # Если краш меньше 1.00, то 70% шанс что взорвётся именно там
    if crash_display < 1.00:
        if random.random() < 0.70:  # 70% шанс взрыва до 1.00
            # Оставляем как есть
            pass
        else:
            # 30% шанс что долетит дальше
            crash_display = random.uniform(1.00, 2.50)
    else:
        # Если краш больше 1.00, то 90% шанс взрыва в этом диапазоне
        if random.random() < 0.90:
            # Оставляем как есть
            pass
        else:
            # 10% шанс что долетит до максимума
            crash_display = 2.50
    
    global round_counter
    round_counter += 1
    round_id = round_counter
    rocket_rounds[round_id] = {
        "user_id": user_id,
        "bet": bet,
        "crash_display": crash_display,
        "start_time": time.time(),
        "status": "active",
        "current_display": 0.0
    }
    return {"round_id": round_id}

@app.get("/api/rocket/status/{round_id}")
async def rocket_status(round_id: int):
    if round_id not in rocket_rounds:
        raise HTTPException(status_code=404, detail="Round not found")
    round_data = rocket_rounds[round_id]
    if round_data["status"] == "crashed":
        return {
            "display_multiplier": round_data["crash_display"],
            "crashed": True,
            "cashed_out": False
        }
    if round_data["status"] == "cashed_out":
        return {
            "display_multiplier": round_data["current_display"],
            "crashed": False,
            "cashed_out": True
        }
    elapsed = time.time() - round_data["start_time"]
    display_multiplier = elapsed * 0.06
    if display_multiplier >= round_data["crash_display"]:
        round_data["status"] = "crashed"
        return {
            "display_multiplier": round_data["crash_display"],
            "crashed": True,
            "cashed_out": False
        }
    else:
        round_data["current_display"] = display_multiplier
        return {
            "display_multiplier": display_multiplier,
            "crashed": False,
            "cashed_out": False
        }

@app.post("/api/rocket/cashout")
async def rocket_cashout(data: RocketCashoutRequest):
    round_id = data.round_id
    user_id = data.user_id
    if round_id not in rocket_rounds:
        raise HTTPException(status_code=404, detail="Round not found")
    round_data = rocket_rounds[round_id]
    if round_data["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not your round")
    if round_data["status"] != "active":
        raise HTTPException(status_code=400, detail="Round already finished")
    elapsed = time.time() - round_data["start_time"]
    display_multiplier = elapsed * 0.06
    if display_multiplier >= round_data["crash_display"]:
        round_data["status"] = "crashed"
        raise HTTPException(status_code=400, detail="Ракета уже упала")
    real_multiplier = 1.0 + display_multiplier
    win_amount = int(round_data["bet"] * real_multiplier)
    update_balance(user_id, win_amount, f"Выигрыш в ракетке {win_amount} токенов")
    add_win(user_id, f"🚀 x{real_multiplier:.2f}", win_amount, "rocket")
    round_data["status"] = "cashed_out"
    round_data["current_display"] = display_multiplier
    new_balance = get_user_by_id(user_id)["balance"]
    return {
        "win_amount": win_amount,
        "new_balance": new_balance,
        "multiplier": real_multiplier
    }

@app.post("/api/withdraw")
async def api_withdraw(data: WithdrawRequest):
    user_id = data.user_id
    amount = data.amount
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] < amount:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    if amount < 500:
        raise HTTPException(status_code=400, detail="Минимальная сумма вывода – 500 токенов")
    create_withdraw_request(user_id, amount)
    return {"status": "success", "message": "Заявка на вывод отправлена администратору"}

@app.get("/api/recent_wins")
async def api_recent_wins():
    return get_recent_wins(limit=10)

@app.get("/api/referral/{user_id}")
async def api_get_referral(user_id: int):
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    info = get_referral_info(user_id)
    link = get_referral_link(user_id)
    return {"code": info["code"], "count": info["count"], "link": link}

@app.post("/api/activate_promo")
async def activate_promo(data: PromoRequest):
    user_id = data.user_id
    code = data.code.lower().strip()
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if code not in PROMOCODES:
        raise HTTPException(status_code=400, detail="Неверный промокод")
    
    if is_promo_used(user_id, code):
        raise HTTPException(status_code=400, detail="Вы уже использовали этот промокод")
    
    reward = PROMOCODES[code]
    update_balance(user_id, reward, f"Промокод {code}")
    use_promo(user_id, code)
    
    new_balance = get_user_by_id(user_id)["balance"]
    return {
        "status": "success",
        "message": f"Промокод активирован! Вы получили +{reward} токенов",
        "new_balance": new_balance
    }

# ==================== ЗАПУСК ====================
async def set_webhook():
    webhook_url = f"https://star-drop.onrender.com/webhook"
    await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    logging.info(f"Webhook установлен на {webhook_url}")

async def run_uvicorn():
    port = int(os.environ.get("PORT", 10000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    server_task = asyncio.create_task(run_uvicorn())
    await set_webhook()
    await server_task

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Остановка сервисов...")
        sys.exit(0)
