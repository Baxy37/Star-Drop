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
            referral_code TEXT UNIQUE,
            clicker_balance INTEGER DEFAULT 0,
            click_power INTEGER DEFAULT 1,
            auto_click_level INTEGER DEFAULT 0,
            multiplier_level INTEGER DEFAULT 0,
            crystal_boost_level INTEGER DEFAULT 0,
            energy INTEGER DEFAULT 15,
            max_energy INTEGER DEFAULT 15
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
        "INSERT INTO users (username, password, telegram_id, referral_code, balance, clicker_balance, energy, max_energy) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (username, password, telegram_id, code, START_BALANCE, 0, 15, 15)
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

def update_clicker_data(user_id: int, clicks: int = 0, click_power: int = None, auto_level: int = None, mult_level: int = None, crystal_level: int = None):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    updates = []
    if clicks != 0:
        updates.append(f"clicker_balance = clicker_balance + {clicks}")
    if click_power is not None:
        updates.append(f"click_power = {click_power}")
    if auto_level is not None:
        updates.append(f"auto_click_level = {auto_level}")
    if mult_level is not None:
        updates.append(f"multiplier_level = {mult_level}")
    if crystal_level is not None:
        updates.append(f"crystal_boost_level = {crystal_level}")
    
    if updates:
        cur.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", (user_id,))
        conn.commit()
    conn.close()

def get_clicker_data(user_id: int) -> Dict:
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT clicker_balance, click_power, auto_click_level, multiplier_level, crystal_boost_level, energy, max_energy FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

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
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, ReplyKeyboardRemove, InputFile, BufferedInputFile

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
    
    try:
        image_path = os.path.join(os.path.dirname(__file__), "Start_img.JPG")
        
        if os.path.exists(image_path):
            with open(image_path, 'rb') as img_file:
                photo = BufferedInputFile(img_file.read(), filename="start_img.jpg")
                await message.answer_photo(
                    photo=photo,
                    caption=(
                        "👋 Добро пожаловать в **Star Drop**!\n\n"
                        "Для входа в игру используйте наше мини-приложение.\n"
                        "Нажмите кнопку ниже, чтобы открыть приложение и войти в свой аккаунт."
                    ),
                    reply_markup=get_start_keyboard()
                )
        else:
            logging.warning(f"Изображение не найдено по пути: {image_path}")
            await message.answer(
                "👋 Добро пожаловать в **Star Drop**!\n\n"
                "Для входа в игру используйте наше мини-приложение.\n"
                "Нажмите кнопку ниже, чтобы открыть приложение и войти в свой аккаунт.",
                reply_markup=get_start_keyboard()
            )
    except Exception as e:
        logging.error(f"Ошибка при отправке изображения: {e}")
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
from fastapi.responses import RedirectResponse, FileResponse
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

# ==================== МАРШРУТ ДЛЯ РАЗДАЧИ ФАЙЛОВ ИЗ КОРНЯ ====================
@app.get("/{filename}")
async def serve_root_files(filename: str):
    """Раздача файлов из корневой папки"""
    allowed_files = [
        'IMGlow.png', 'IMGnorm.jpg', 'IMGhard.jpg',
        'Start_img.JPG', 'win_symbol.png', 'lose_symbol.png',
        'case.jpg', 'raketa.jpg', 'slot.jpg', 'cloker.jpg'
    ]
    
    if filename in allowed_files:
        file_path = os.path.join(os.path.dirname(__file__), filename)
        if os.path.exists(file_path):
            return FileResponse(file_path)
    
    raise HTTPException(status_code=404, detail="File not found")

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
    <title>StarDrop</title>
    <link rel="stylesheet" href="/static/style.css?v=16">
</head>
<body>

    <!-- ЭКРАН ВХОДА -->
    <div id="login-screen" class="login-screen">
        <div class="login-container">
            <div class="login-logo">
                <span class="logo-icon">⭐</span>
                <span class="logo-text">Star<span class="highlight">Drop</span></span>
            </div>
            <p class="login-subtitle">Войдите в свой аккаунт</p>
            <div class="input-group">
                <input id="login-username" type="text" placeholder="Имя пользователя" class="login-input">
                <input id="login-password" type="password" placeholder="Пароль" class="login-input">
            </div>
            <button id="login-btn" class="btn-primary btn-large">Войти</button>
            <div id="login-error" class="login-error"></div>
        </div>
    </div>

    <!-- ОСНОВНОЙ ИНТЕРФЕЙС -->
    <div id="app-content" class="app-content" style="display:none;">
        
        <!-- Фоновые частицы -->
        <div class="particles">
            <div class="particle"></div><div class="particle"></div><div class="particle"></div>
            <div class="particle"></div><div class="particle"></div><div class="particle"></div>
            <div class="particle"></div><div class="particle"></div><div class="particle"></div>
            <div class="particle"></div><div class="particle"></div><div class="particle"></div>
            <div class="particle"></div><div class="particle"></div><div class="particle"></div>
            <div class="particle"></div><div class="particle"></div><div class="particle"></div>
            <div class="particle"></div><div class="particle"></div><div class="particle"></div>
            <div class="particle"></div><div class="particle"></div><div class="particle"></div>
        </div>

        <!-- ВЕРХНЯЯ ПАНЕЛЬ -->
        <div class="top-bar glass-panel">
            <div id="user-info" class="user-info">
                <div id="avatar-container" class="avatar-container">
                    <img id="avatar-img" src="" alt="avatar" class="avatar-img">
                    <span id="avatar-placeholder" class="avatar-placeholder">U</span>
                </div>
                <span id="username-display" class="username-display">@username</span>
            </div>
            <div class="balance-section">
                <span class="balance-amount"><span id="balance-amount">0</span> 🎫</span>
                <button id="deposit-btn" class="btn-icon">+</button>
                <button id="bets-btn" class="btn-text">Ставки</button>
            </div>
        </div>

        <!-- МЕНЮ ПОПОЛНЕНИЯ -->
        <div id="deposit-menu" class="deposit-menu glass-panel" style="display: none;">
            <div class="deposit-title">Пополнить баланс</div>
            <div class="deposit-options">
                <button class="deposit-option" data-amount="100">100₽</button>
                <button class="deposit-option" data-amount="200">200₽</button>
                <button class="deposit-option" data-amount="500">500₽</button>
                <button class="deposit-option" data-amount="1000">1000₽</button>
            </div>
            <button id="close-deposit" class="btn-close">✖</button>
        </div>

        <!-- МОДАЛЬНЫЕ ОКНА -->
        <div id="referral-modal" class="modal-overlay" style="display: none;">
            <div class="modal-content glass-panel">
                <h3 class="modal-title">Реферальная система</h3>
                <p class="modal-text">Приведи друга и получи <b>+50 токенов</b> на баланс!</p>
                <p id="ref-link" class="ref-link">Загрузка...</p>
                <button id="copy-ref-link" class="btn-primary">Копировать ссылку</button>
                <div class="ref-count">Приглашено друзей: <b id="ref-count">0</b></div>
                <button id="close-ref-modal" class="btn-secondary">Закрыть</button>
            </div>
        </div>

        <div id="bets-modal" class="modal-overlay" style="display: none;">
            <div class="modal-content glass-panel">
                <h3 class="modal-title">Мои ставки</h3>
                <ul id="bets-list" class="bets-list"></ul>
                <button id="close-bets-modal" class="btn-secondary">Закрыть</button>
            </div>
        </div>

        <!-- ГЛАВНАЯ СТРАНИЦА -->
        <div id="home-page" class="page active">
            <div class="home-header">
                <h1 class="main-title">⭐ Star<span class="highlight">Drop</span></h1>
                <p class="main-subtitle">Испытай удачу</p>
            </div>

            <div class="games-grid">
                <div class="game-card" data-tab="roulette">
                    <div class="game-card-content">
                        <img src="/case.jpg" alt="Кейсы" class="game-image">
                        <span class="game-name">Кейсы</span>
                    </div>
                </div>
                <div class="game-card" data-tab="slot">
                    <div class="game-card-content">
                        <img src="/slot.jpg" alt="Слоты" class="game-image">
                        <span class="game-name">Слоты</span>
                    </div>
                </div>
                <div class="game-card" data-tab="rocket">
                    <div class="game-card-content">
                        <img src="/raketa.jpg" alt="Ракетка" class="game-image">
                        <span class="game-name">Ракетка</span>
                    </div>
                </div>
                <div class="game-card" data-tab="clicker">
                    <div class="game-card-content">
                        <img src="/cloker.jpg" alt="Кликер" class="game-image">
                        <span class="game-name">Кликер</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- СТРАНИЦА КЕЙСОВ -->
        <div id="roulette-page" class="page">
            <div class="game-header">
                <button class="btn-back" data-back="home">←</button>
                <span class="game-title">Кейсы</span>
            </div>
            <div id="mode-selector" class="mode-selector">
                <button class="mode-btn active" data-mode="light">Low</button>
                <button class="mode-btn" data-mode="normal">Normal</button>
                <button class="mode-btn" data-mode="hard">Hard</button>
            </div>
            <div id="key-container" class="key-container">
                <div id="key-display" class="key-display">
                    <img id="key-image" src="/IMGlow.png" alt="Key" class="key-icon">
                </div>
            </div>
            <div id="wheel-wrapper" style="display:none;">
                <div id="wheel-container" class="wheel-container">
                    <div id="wheel-strip" class="wheel-strip"></div>
                    <div id="wheel-arrow" class="wheel-arrow">▼</div>
                </div>
            </div>
            <div id="spin-area" class="spin-area">
                <div id="spin-info" class="spin-info">1 кейс = <span id="spin-cost">25</span> монет</div>
                <button id="spin-btn" class="btn-primary btn-large btn-glow btn-shimmer">
                    ОТКРЫТЬ
                    <span id="spin-cost-label">25 Токенов</span>
                </button>
            </div>
            <div id="result-message" class="result-message"></div>
        </div>

        <!-- СТРАНИЦА СЛОТОВ -->
        <div id="slot-page" class="page">
            <div class="game-header">
                <button class="btn-back" data-back="home">←</button>
                <span class="game-title">Слоты</span>
            </div>
            <div id="slot-machine" class="slot-machine glass-panel">
                <div id="reels" class="reels">
                    <div class="reel" id="reel1">🍒</div>
                    <div class="reel" id="reel2">🍋</div>
                    <div class="reel" id="reel3">🍊</div>
                </div>
                <div class="slot-controls">
                    <div class="bet-control">
                        <label>Ставка: <span id="bet-display">20</span> токенов</label>
                        <input type="range" id="bet-range" min="20" max="100" step="10" value="20">
                        <div id="slot-multiplier">При выигрыше: <b>x2</b></div>
                    </div>
                    <button id="spin-slot-btn" class="btn-primary btn-large btn-shimmer">Дёрнуть рычаг 🎰</button>
                </div>
                <div id="slot-result" class="slot-result"></div>
            </div>
        </div>

        <!-- СТРАНИЦА РАКЕТКИ -->
        <div id="rocket-page" class="page">
            <div class="game-header">
                <button class="btn-back" data-back="home">←</button>
                <span class="game-title">Ракетка</span>
            </div>
            <div id="rocket-game" class="rocket-game glass-panel">
                <div id="rocket-display" class="rocket-display">
                    <div id="rocket-multiplier" class="rocket-multiplier">0.00</div>
                    <div id="rocket-status" class="rocket-status">Ожидание</div>
                </div>
                <div id="rocket-canvas-container" class="rocket-canvas-container">
                    <canvas id="rocketCanvas" width="300" height="200"></canvas>
                </div>
                <div class="rocket-bet-control">
                    <label>Ставка: <span id="rocket-bet-display">500</span> токенов</label>
                    <input type="range" id="rocket-bet-range" min="100" max="1000" step="10" value="500">
                </div>
                <div class="rocket-buttons">
                    <button id="rocket-start-btn" class="btn-primary btn-large btn-shimmer">🚀 Старт</button>
                    <button id="rocket-cashout-btn" class="btn-secondary btn-large" disabled>💸 Забрать</button>
                </div>
                <div id="rocket-timer" class="rocket-timer">Следующий взлёт через: <span id="rocket-countdown">5</span>с</div>
                <div id="rocket-result" class="rocket-result"></div>
            </div>
        </div>

        <!-- СТРАНИЦА КЛИКЕРА -->
        <div id="clicker-page" class="page">
            <div class="game-header">
                <button class="btn-back" data-back="home">←</button>
                <span class="game-title">Кликер</span>
            </div>
            
            <div class="clicker-container glass-panel">
                <!-- Верхняя панель ресурсов -->
                <div class="clicker-resources">
                    <div class="resource-item">
                        <span class="resource-icon">⭐</span>
                        <div class="resource-info">
                            <span class="resource-value" id="clicker-stars">0</span>
                            <span class="resource-label">КЛИКИ</span>
                        </div>
                    </div>
                    <div class="resource-item">
                        <span class="resource-icon">💎</span>
                        <div class="resource-info">
                            <span class="resource-value" id="clicker-crystals">0</span>
                            <span class="resource-label">CRYSTAL</span>
                        </div>
                    </div>
                    <div class="resource-item">
                        <span class="resource-icon">⚡</span>
                        <div class="resource-info">
                            <span class="resource-value" id="clicker-energy">15/15</span>
                            <span class="resource-label">ENERGY</span>
                        </div>
                    </div>
                </div>

                <!-- Центральный кликер -->
                <div class="clicker-area" id="clicker-area">
                    <div class="clicker-circle" id="clicker-circle">
                        <span class="clicker-icon">✈️</span>
                        <span class="clicker-plus" id="clicker-plus">+1</span>
                    </div>
                </div>

                <!-- Нижняя панель улучшений -->
                <div class="clicker-boosts">
                    <div class="boost-card" id="boost-auto">
                        <div class="boost-icon">🖱️</div>
                        <div class="boost-info">
                            <span class="boost-name">Auto Click</span>
                            <span class="boost-level">Level <span id="auto-level">0</span></span>
                        </div>
                        <div class="boost-price">
                            <span class="price-icon">⭐</span>
                            <span class="price-value" id="auto-price">500</span>
                        </div>
                        <button class="boost-btn btn-shimmer" data-boost="auto">Buy</button>
                    </div>

                    <div class="boost-card" id="boost-multiplier">
                        <div class="boost-icon">🚀</div>
                        <div class="boost-info">
                            <span class="boost-name">Star Multiplier</span>
                            <span class="boost-level">Level <span id="multiplier-level">0</span></span>
                        </div>
                        <div class="boost-price">
                            <span class="price-icon">⭐</span>
                            <span class="price-value" id="multiplier-price">1000</span>
                        </div>
                        <button class="boost-btn btn-shimmer" data-boost="multiplier">Buy</button>
                    </div>

                    <div class="boost-card" id="boost-crystal">
                        <div class="boost-icon">💎</div>
                        <div class="boost-info">
                            <span class="boost-name">Crystal Boost</span>
                            <span class="boost-level">Level <span id="crystal-level">0</span></span>
                        </div>
                        <div class="boost-price">
                            <span class="price-icon">⭐</span>
                            <span class="price-value" id="crystal-price">2000</span>
                        </div>
                        <button class="boost-btn btn-shimmer" data-boost="crystal">Buy</button>
                    </div>
                </div>

                <!-- Кнопка продажи кликов -->
                <button id="sell-clicks-btn" class="btn-primary btn-large sell-btn btn-shimmer">
                    💰 Продать клики (1000 = 1 токен)
                </button>
                <div id="sell-message" class="sell-message"></div>
            </div>
        </div>

        <!-- НИЖНЯЯ НАВИГАЦИЯ -->
        <nav class="bottom-nav">
            <button class="nav-btn active" data-tab="home">🏠</button>
            <button class="nav-btn" data-tab="roulette">🎡</button>
            <button class="nav-btn" data-tab="slot">🎰</button>
            <button class="nav-btn" data-tab="rocket">🚀</button>
            <button class="nav-btn" data-tab="clicker">👆</button>
            <button id="logout-btn" class="nav-btn logout-btn">🚪</button>
        </nav>

        <!-- ФИД ПОСЛЕДНИХ ВЫИГРЫШЕЙ -->
        <div id="notification-feed" class="notification-feed glass-panel">
            <h3>Последние выигрыши</h3>
            <ul id="feed-list" class="feed-list"></ul>
        </div>

        <!-- ПРОМОКОД -->
        <div id="promo-area" class="promo-area">
            <input type="text" id="promo-input" placeholder="Введите промокод" class="promo-input">
            <button id="promo-btn" class="btn-primary btn-shimmer">Активировать</button>
            <div id="promo-message" class="promo-message"></div>
        </div>

        <button id="withdraw-btn" class="btn-primary btn-large btn-shimmer">Вывести токены</button>

    </div>

    <script src="/static/script.js?v=16"></script>
</body>
</html>""")

# CSS
with open(os.path.join(STATIC_DIR, "style.css"), "w", encoding="utf-8") as f:
    f.write("""/* ===== RESET & BASE ===== */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
}

:root {
    --bg-primary: #090B0F;
    --bg-secondary: #141414;
    --bg-card: rgba(255, 255, 255, 0.05);
    --border-glass: rgba(255, 255, 255, 0.1);
    --text-primary: #ffffff;
    --text-secondary: #aaaaaa;
    --accent-gold: #FFD54A;
    --accent-gold-gradient: linear-gradient(135deg, #FFD54A, #F9B800);
    --accent-blue: #4FC3F7;
    --accent-purple: #B39DDB;
    --accent-pink: #F06292;
    --shadow-glow: 0 0 30px rgba(255, 213, 74, 0.15);
    --radius-large: 28px;
    --radius-medium: 16px;
    --radius-small: 12px;
}

body {
    background: var(--bg-primary);
    color: var(--text-primary);
    min-height: 100vh;
    display: flex;
    justify-content: center;
    padding: 16px 12px 90px 12px;
    overflow-x: hidden;
    -webkit-font-smoothing: antialiased;
}

/* ===== GLASSMORPHISM ===== */
.glass-panel {
    background: var(--bg-card);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid var(--border-glass);
    border-radius: var(--radius-large);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

/* ===== SCROLLBAR ===== */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--accent-gold); border-radius: 10px; }

/* ===== PARTICLES BACKGROUND ===== */
.particles {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: 0;
    overflow: hidden;
    opacity: 1;
}
.particle {
    position: absolute;
    border-radius: 50%;
    opacity: 0.6;
    animation: floatParticle linear infinite;
    box-shadow: 0 0 10px rgba(255, 213, 74, 0.2);
}
.particle:nth-child(1) { left: 5%; animation-duration: 14s; animation-delay: 0s; width: 8px; height: 8px; background: #FFD54A; }
.particle:nth-child(2) { left: 12%; animation-duration: 18s; animation-delay: 2s; width: 5px; height: 5px; background: #FF6B6B; }
.particle:nth-child(3) { left: 20%; animation-duration: 12s; animation-delay: 1s; width: 10px; height: 10px; background: #4FC3F7; }
.particle:nth-child(4) { left: 28%; animation-duration: 20s; animation-delay: 3s; width: 6px; height: 6px; background: #FFD54A; }
.particle:nth-child(5) { left: 35%; animation-duration: 15s; animation-delay: 0.5s; width: 7px; height: 7px; background: #CE93D8; }
.particle:nth-child(6) { left: 42%; animation-duration: 13s; animation-delay: 4s; width: 9px; height: 9px; background: #FFD54A; }
.particle:nth-child(7) { left: 50%; animation-duration: 17s; animation-delay: 1.5s; width: 5px; height: 5px; background: #81C784; }
.particle:nth-child(8) { left: 58%; animation-duration: 16s; animation-delay: 2.5s; width: 11px; height: 11px; background: #FFD54A; }
.particle:nth-child(9) { left: 65%; animation-duration: 11s; animation-delay: 0.8s; width: 6px; height: 6px; background: #FF8A65; }
.particle:nth-child(10) { left: 72%; animation-duration: 19s; animation-delay: 3.5s; width: 8px; height: 8px; background: #FFD54A; }
.particle:nth-child(11) { left: 80%; animation-duration: 14s; animation-delay: 5s; width: 7px; height: 7px; background: #4FC3F7; }
.particle:nth-child(12) { left: 88%; animation-duration: 16s; animation-delay: 2.8s; width: 10px; height: 10px; background: #FFD54A; }
.particle:nth-child(13) { left: 15%; animation-duration: 22s; animation-delay: 1.2s; width: 4px; height: 4px; background: #FFD54A; }
.particle:nth-child(14) { left: 45%; animation-duration: 18s; animation-delay: 4.2s; width: 12px; height: 12px; background: #CE93D8; }
.particle:nth-child(15) { left: 70%; animation-duration: 15s; animation-delay: 3.8s; width: 6px; height: 6px; background: #FFD54A; }
.particle:nth-child(16) { left: 92%; animation-duration: 13s; animation-delay: 0.3s; width: 8px; height: 8px; background: #81C784; }
.particle:nth-child(17) { left: 8%; animation-duration: 17s; animation-delay: 2.2s; width: 5px; height: 5px; background: #FFD54A; }
.particle:nth-child(18) { left: 55%; animation-duration: 14s; animation-delay: 1.8s; width: 9px; height: 9px; background: #FF6B6B; }
.particle:nth-child(19) { left: 25%; animation-duration: 19s; animation-delay: 4.8s; width: 7px; height: 7px; background: #FFD54A; }
.particle:nth-child(20) { left: 78%; animation-duration: 16s; animation-delay: 0.7s; width: 11px; height: 11px; background: #4FC3F7; }
.particle:nth-child(21) { left: 48%; animation-duration: 21s; animation-delay: 3.2s; width: 4px; height: 4px; background: #FFD54A; }
.particle:nth-child(22) { left: 62%; animation-duration: 14s; animation-delay: 5.5s; width: 8px; height: 8px; background: #CE93D8; }
.particle:nth-child(23) { left: 18%; animation-duration: 18s; animation-delay: 0.9s; width: 6px; height: 6px; background: #FFD54A; }
.particle:nth-child(24) { left: 85%; animation-duration: 15s; animation-delay: 2.1s; width: 10px; height: 10px; background: #81C784; }

@keyframes floatParticle {
    0% { transform: translate(0, 0) scale(1); opacity: 0.6; }
    25% { transform: translate(20px, -30px) scale(1.2); opacity: 0.9; }
    50% { transform: translate(-10px, -60px) scale(0.8); opacity: 0.5; }
    75% { transform: translate(30px, -90px) scale(1.1); opacity: 0.8; }
    100% { transform: translate(0, -120px) scale(1); opacity: 0.4; }
}

/* ===== LOGIN SCREEN ===== */
.login-screen {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    width: 100%;
    max-width: 400px;
    position: relative;
    z-index: 2;
}
.login-container {
    width: 100%;
    padding: 40px 24px;
    text-align: center;
}
.login-logo {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    margin-bottom: 8px;
}
.logo-icon {
    font-size: 36px;
}
.logo-text {
    font-size: 32px;
    font-weight: 700;
    letter-spacing: -0.5px;
}
.logo-text .highlight {
    color: var(--accent-gold);
}
.login-subtitle {
    color: var(--text-secondary);
    font-size: 16px;
    margin-bottom: 32px;
}
.input-group {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-bottom: 24px;
}
.login-input {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border-glass);
    border-radius: var(--radius-medium);
    padding: 16px 18px;
    color: var(--text-primary);
    font-size: 16px;
    outline: none;
    transition: border-color 0.3s;
}
.login-input:focus {
    border-color: var(--accent-gold);
}
.login-input::placeholder {
    color: var(--text-secondary);
}
.login-error {
    color: #ff6b6b;
    font-size: 14px;
    margin-top: 12px;
    min-height: 20px;
}

/* ===== BUTTONS ===== */
.btn-primary {
    background: var(--accent-gold-gradient);
    color: #0a0a0a;
    border: none;
    border-radius: var(--radius-medium);
    padding: 14px 24px;
    font-weight: 700;
    font-size: 16px;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(255, 213, 74, 0.2);
    position: relative;
    overflow: hidden;
}
.btn-primary:hover {
    transform: scale(1.02);
    box-shadow: 0 6px 25px rgba(255, 213, 74, 0.4);
}
.btn-primary:active {
    transform: scale(0.97);
}
.btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
}
.btn-large {
    padding: 18px 32px;
    font-size: 18px;
    border-radius: var(--radius-medium);
}
.btn-glow {
    box-shadow: 0 0 30px rgba(255, 213, 74, 0.15);
}

/* ===== SHIMMER EFFECT ===== */
.btn-shimmer {
    position: relative;
    overflow: hidden;
    z-index: 1;
}

.btn-shimmer::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: linear-gradient(
        45deg,
        transparent 30%,
        rgba(255, 255, 255, 0.15) 40%,
        rgba(255, 215, 0, 0.3) 50%,
        rgba(255, 255, 255, 0.15) 60%,
        transparent 70%
    );
    background-size: 200% 200%;
    animation: shimmer 3s ease-in-out infinite;
    z-index: -1;
}

@keyframes shimmer {
    0% { transform: translateX(-100%) rotate(25deg); }
    100% { transform: translateX(100%) rotate(25deg); }
}

.btn-shimmer:nth-child(1)::before { animation-duration: 3s; }
.btn-shimmer:nth-child(2)::before { animation-duration: 4s; }
.btn-shimmer:nth-child(3)::before { animation-duration: 3.5s; }
.btn-shimmer:hover::before { animation-duration: 1.5s; }

#spin-btn.btn-shimmer::before {
    background: linear-gradient(
        45deg,
        transparent 25%,
        rgba(255, 215, 0, 0.2) 35%,
        rgba(255, 215, 0, 0.5) 45%,
        rgba(255, 255, 255, 0.3) 55%,
        rgba(255, 215, 0, 0.2) 65%,
        transparent 75%
    );
    animation-duration: 2.5s;
}

.btn-secondary {
    background: rgba(255, 255, 255, 0.08);
    color: var(--text-primary);
    border: 1px solid var(--border-glass);
    border-radius: var(--radius-medium);
    padding: 12px 20px;
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.2s ease;
}
.btn-secondary:hover {
    background: rgba(255, 255, 255, 0.15);
}

.btn-icon {
    background: var(--accent-gold-gradient);
    border: none;
    border-radius: 50%;
    width: 36px;
    height: 36px;
    font-size: 22px;
    font-weight: 700;
    color: #0a0a0a;
    cursor: pointer;
    transition: transform 0.2s;
    display: flex;
    align-items: center;
    justify-content: center;
}
.btn-icon:hover {
    transform: scale(1.05);
}

.btn-text {
    background: transparent;
    border: none;
    color: var(--accent-gold);
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    padding: 4px 8px;
    transition: opacity 0.2s;
}
.btn-text:hover {
    opacity: 0.7;
}

.btn-close {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-size: 20px;
    cursor: pointer;
    position: absolute;
    top: 12px;
    right: 16px;
}
.btn-back {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-size: 20px;
    cursor: pointer;
    padding: 4px 8px;
}

/* ===== TOP BAR ===== */
.top-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    margin-bottom: 20px;
    width: 100%;
    max-width: 400px;
    position: sticky;
    top: 0;
    z-index: 20;
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
}
.user-info {
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
}
.avatar-container {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    overflow: hidden;
    background: var(--accent-gold-gradient);
    flex-shrink: 0;
}
.avatar-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: none;
}
.avatar-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    font-weight: 700;
    font-size: 16px;
    color: #0a0a0a;
}
.username-display {
    font-weight: 600;
    font-size: 14px;
    color: var(--text-primary);
}
.balance-section {
    display: flex;
    align-items: center;
    gap: 6px;
}
.balance-amount {
    font-weight: 700;
    font-size: 16px;
    color: var(--accent-gold);
}

/* ===== DEPOSIT MENU ===== */
.deposit-menu {
    position: relative;
    padding: 20px;
    margin-bottom: 12px;
    width: 100%;
    max-width: 400px;
}
.deposit-title {
    text-align: center;
    font-weight: 700;
    font-size: 16px;
    color: var(--accent-gold);
    margin-bottom: 16px;
}
.deposit-options {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    justify-content: center;
}
.deposit-option {
    background: var(--accent-gold-gradient);
    border: none;
    border-radius: var(--radius-small);
    padding: 12px 20px;
    font-weight: 700;
    font-size: 15px;
    color: #0a0a0a;
    cursor: pointer;
    transition: transform 0.2s;
}
.deposit-option:hover {
    transform: scale(1.05);
}

/* ===== MODALS ===== */
.modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(8px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
}
.modal-content {
    max-width: 340px;
    width: 90%;
    padding: 28px 24px;
    text-align: center;
    position: relative;
}
.modal-title {
    font-size: 20px;
    color: var(--accent-gold);
    margin-bottom: 8px;
}
.modal-text {
    color: var(--text-secondary);
    font-size: 14px;
    margin-bottom: 16px;
}
.ref-link {
    background: rgba(255, 255, 255, 0.05);
    border-radius: var(--radius-small);
    padding: 12px;
    word-break: break-all;
    font-size: 13px;
    margin-bottom: 16px;
    color: var(--text-primary);
}
.ref-count {
    color: var(--text-secondary);
    font-size: 14px;
    margin: 12px 0 16px;
}
.bets-list {
    list-style: none;
    max-height: 300px;
    overflow-y: auto;
    text-align: left;
    margin: 12px 0;
}
.bets-list li {
    padding: 8px 0;
    border-bottom: 1px solid var(--border-glass);
    font-size: 14px;
    color: var(--text-secondary);
}
.bets-list li .positive { color: #4CAF50; }
.bets-list li .negative { color: #ff6b6b; }

/* ===== PAGES ===== */
.page {
    display: none;
    width: 100%;
    max-width: 400px;
    flex-direction: column;
    align-items: center;
    position: relative;
    z-index: 1;
}
.page.active {
    display: flex;
}

/* ===== HOME PAGE ===== */
.home-header {
    text-align: center;
    margin: 12px 0 24px;
}
.main-title {
    font-size: 28px;
    font-weight: 800;
    letter-spacing: -0.5px;
}
.main-title .highlight {
    color: var(--accent-gold);
}
.main-subtitle {
    color: var(--text-secondary);
    font-size: 14px;
    margin-top: 4px;
}
.games-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
    width: 100%;
    margin-bottom: 24px;
}
.game-card {
    background: transparent;
    border: none;
    border-radius: var(--radius-medium);
    padding: 0;
    text-align: center;
    cursor: pointer;
    transition: all 0.3s ease;
}
.game-card-content {
    background: transparent !important;
    border: 1.5px solid rgba(255, 255, 255, 0.2);
    border-radius: var(--radius-medium);
    padding: 12px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 200px;
    transition: all 0.3s ease;
    position: relative;
}
.game-card:hover .game-card-content {
    border-color: rgba(255, 255, 255, 0.4);
    transform: translateY(-4px);
}
.game-card:hover .game-image {
    transform: scale(1.05);
}
.game-card .game-image {
    width: 100%;
    height: 160px;
    object-fit: contain;
    margin-bottom: 6px;
    border-radius: var(--radius-small);
    transition: all 0.3s ease;
}
.game-card .game-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-top: 2px;
    text-shadow: 0 0 10px rgba(0, 0, 0, 0.8);
}

/* ===== GAME HEADERS ===== */
.game-header {
    display: flex;
    align-items: center;
    gap: 12px;
    width: 100%;
    padding: 8px 0 16px;
}
.game-title {
    font-size: 18px;
    font-weight: 700;
}

/* ===== ROULETTE / CASES ===== */
.mode-selector {
    display: flex;
    gap: 12px;
    margin-bottom: 20px;
    justify-content: center;
}
.mode-btn {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border-glass);
    border-radius: 20px;
    padding: 8px 24px;
    color: var(--text-secondary);
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
    transition: all 0.3s ease;
}
.mode-btn.active {
    background: var(--accent-gold-gradient);
    color: #0a0a0a;
    border-color: transparent;
    box-shadow: 0 0 20px rgba(255, 213, 74, 0.2);
}
.key-container {
    display: flex;
    justify-content: center;
    margin: 8px 0 16px;
}
.key-display {
    display: flex;
    justify-content: center;
    align-items: center;
}
.key-icon {
    width: 300px;
    height: 300px;
    object-fit: contain;
}
.key-icon:hover {
    transform: scale(1.02);
}
.wheel-container {
    width: 100%;
    height: 120px;
    overflow: hidden;
    border-radius: var(--radius-medium);
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-glass);
    position: relative;
    margin-bottom: 12px;
}
.wheel-strip {
    display: flex;
    height: 100%;
    align-items: center;
    gap: 4px;
    padding: 0 10px;
    will-change: transform;
    width: max-content;
}
.wheel-cell {
    flex: 0 0 60px;
    height: 80px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: var(--radius-small);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 32px;
    border: 1px solid var(--border-glass);
}
.wheel-arrow {
    position: absolute;
    top: -8px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 28px;
    color: var(--accent-gold);
    text-shadow: 0 0 20px rgba(255, 213, 74, 0.3);
    pointer-events: none;
}
.spin-area {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 100%;
    margin-top: 20px;
}
.spin-info {
    color: var(--text-secondary);
    font-size: 14px;
    margin-bottom: 8px;
}
.spin-info span {
    color: var(--accent-gold);
    font-weight: 700;
}
.result-message {
    min-height: 40px;
    font-size: 18px;
    font-weight: 700;
    text-align: center;
    margin: 8px 0;
}

/* ===== SLOT ===== */
.slot-machine {
    padding: 20px;
    width: 100%;
}
.reels {
    display: flex;
    justify-content: center;
    gap: 16px;
    padding: 16px 0;
}
.reel {
    width: 80px;
    height: 96px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: var(--radius-medium);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 48px;
    border: 1px solid var(--border-glass);
}
.slot-controls {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
}
.bet-control {
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
}
.bet-control label {
    color: var(--text-secondary);
    font-size: 14px;
}
.bet-control input[type="range"] {
    width: 80%;
    max-width: 250px;
    accent-color: var(--accent-gold);
    margin-top: 4px;
}
#slot-multiplier {
    font-size: 14px;
    color: var(--text-secondary);
}
#slot-multiplier b {
    color: var(--accent-gold);
}
.slot-result {
    font-size: 18px;
    font-weight: 700;
    text-align: center;
    min-height: 30px;
    margin-top: 12px;
}

/* ===== ROCKET ===== */
.rocket-game {
    padding: 20px;
    width: 100%;
}
.rocket-display {
    text-align: center;
    padding: 8px 0;
}
.rocket-multiplier {
    font-size: 44px;
    font-weight: 900;
    color: var(--accent-gold);
    text-shadow: 0 0 30px rgba(255, 213, 74, 0.15);
}
.rocket-status {
    font-size: 14px;
    color: var(--text-secondary);
}
.rocket-canvas-container {
    width: 100%;
    margin: 8px 0;
}
.rocket-canvas-container canvas {
    width: 100%;
    height: auto;
    border-radius: var(--radius-medium);
    background: rgba(255, 255, 255, 0.02);
}
.rocket-bet-control {
    display: flex;
    flex-direction: column;
    align-items: center;
    margin: 8px 0;
}
.rocket-bet-control label {
    color: var(--text-secondary);
    font-size: 14px;
}
.rocket-bet-control input[type="range"] {
    width: 80%;
    max-width: 250px;
    accent-color: var(--accent-gold);
    margin-top: 4px;
}
.rocket-buttons {
    display: flex;
    gap: 12px;
    justify-content: center;
    margin: 12px 0;
}
.rocket-buttons .btn-primary, .rocket-buttons .btn-secondary {
    flex: 1;
    max-width: 150px;
    text-align: center;
}
.rocket-timer {
    font-size: 14px;
    color: var(--text-secondary);
    text-align: center;
    margin: 4px 0;
}
.rocket-timer span {
    color: var(--accent-gold);
}
.rocket-result {
    font-size: 18px;
    font-weight: 700;
    text-align: center;
    min-height: 30px;
    margin-top: 8px;
}

/* ===== CLICKER ===== */
.clicker-container {
    padding: 20px;
    width: 100%;
}

.clicker-resources {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-bottom: 20px;
}

.resource-item {
    background: rgba(255, 255, 255, 0.05);
    border-radius: var(--radius-small);
    padding: 10px 8px;
    display: flex;
    align-items: center;
    gap: 8px;
    border: 1px solid var(--border-glass);
}

.resource-icon {
    font-size: 20px;
}

.resource-info {
    display: flex;
    flex-direction: column;
}

.resource-value {
    font-size: 14px;
    font-weight: 700;
    color: var(--text-primary);
}

.resource-label {
    font-size: 9px;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.clicker-area {
    display: flex;
    justify-content: center;
    align-items: center;
    padding: 20px 0;
    cursor: pointer;
}

.clicker-circle {
    width: 160px;
    height: 160px;
    border-radius: 50%;
    background: radial-gradient(circle at 30% 30%, rgba(79, 195, 247, 0.2), rgba(79, 195, 247, 0.05));
    border: 2px solid var(--accent-blue);
    box-shadow: 0 0 40px rgba(79, 195, 247, 0.2), inset 0 0 40px rgba(79, 195, 247, 0.05);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    transition: all 0.1s ease;
    position: relative;
    cursor: pointer;
    user-select: none;
}

.clicker-circle:active {
    transform: scale(0.95);
    box-shadow: 0 0 60px rgba(79, 195, 247, 0.4);
}

.clicker-icon {
    font-size: 48px;
    margin-bottom: 4px;
}

.clicker-plus {
    font-size: 18px;
    font-weight: 700;
    color: var(--accent-blue);
}

.clicker-boosts {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin: 16px 0;
}

.boost-card {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-glass);
    border-radius: var(--radius-medium);
    padding: 12px 16px;
    display: grid;
    grid-template-columns: 40px 1fr auto auto;
    align-items: center;
    gap: 10px;
    transition: all 0.3s ease;
}

.boost-card.disabled {
    opacity: 0.4;
    pointer-events: none;
}

.boost-card:hover:not(.disabled) {
    border-color: var(--accent-gold);
    box-shadow: var(--shadow-glow);
}

.boost-icon {
    font-size: 24px;
}

.boost-info {
    display: flex;
    flex-direction: column;
}

.boost-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
}

.boost-level {
    font-size: 11px;
    color: var(--text-secondary);
}

.boost-price {
    display: flex;
    align-items: center;
    gap: 4px;
}

.price-icon {
    font-size: 12px;
}

.price-value {
    font-size: 13px;
    font-weight: 600;
    color: var(--accent-gold);
}

.boost-btn {
    background: var(--accent-gold-gradient);
    border: none;
    border-radius: var(--radius-small);
    padding: 6px 14px;
    font-weight: 700;
    font-size: 12px;
    color: #0a0a0a;
    cursor: pointer;
    transition: all 0.2s ease;
    position: relative;
    overflow: hidden;
}

.boost-btn:hover:not(:disabled) {
    transform: scale(1.05);
}

.boost-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
}

.sell-btn {
    width: 100%;
    margin-top: 8px;
    background: linear-gradient(135deg, #4CAF50, #2E7D32);
    box-shadow: 0 4px 15px rgba(76, 175, 80, 0.3);
}

.sell-btn:hover {
    box-shadow: 0 6px 25px rgba(76, 175, 80, 0.5);
}

.sell-message {
    text-align: center;
    font-size: 14px;
    min-height: 24px;
    margin-top: 8px;
    color: var(--accent-gold);
}

/* ===== BOTTOM NAV ===== */
.bottom-nav {
    position: fixed;
    bottom: 0;
    left: 0;
    width: 100%;
    background: rgba(9, 11, 15, 0.95);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border-top: 1px solid var(--border-glass);
    display: flex;
    justify-content: space-around;
    padding: 10px 4px 14px;
    z-index: 50;
    max-width: 100%;
}
.nav-btn {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-size: 20px;
    padding: 4px 8px;
    border-radius: var(--radius-small);
    cursor: pointer;
    transition: all 0.2s ease;
}
.nav-btn.active {
    color: var(--accent-gold);
    text-shadow: 0 0 20px rgba(255, 213, 74, 0.2);
}
.nav-btn:hover {
    color: var(--text-primary);
}
.nav-btn.logout-btn {
    font-size: 16px;
}
.nav-btn.logout-btn:hover {
    color: #ff6b6b;
}

/* ===== NOTIFICATION FEED ===== */
.notification-feed {
    padding: 16px 18px;
    width: 100%;
    max-width: 400px;
    margin: 16px 0;
}
.notification-feed h3 {
    font-size: 14px;
    color: var(--text-secondary);
    font-weight: 600;
    margin-bottom: 8px;
    letter-spacing: 0.5px;
}
.feed-list {
    list-style: none;
    max-height: 160px;
    overflow-y: auto;
}
.feed-list li {
    padding: 6px 0;
    border-bottom: 1px solid var(--border-glass);
    font-size: 13px;
    color: var(--text-secondary);
}
.feed-list li:last-child {
    border-bottom: none;
}

/* ===== PROMO ===== */
.promo-area {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    justify-content: center;
    width: 100%;
    max-width: 400px;
    margin: 8px 0;
}
.promo-input {
    flex: 1;
    min-width: 140px;
    padding: 12px 16px;
    border-radius: var(--radius-medium);
    border: 1px solid var(--border-glass);
    background: rgba(255, 255, 255, 0.05);
    color: var(--text-primary);
    font-size: 14px;
    outline: none;
    text-align: center;
}
.promo-input:focus {
    border-color: var(--accent-gold);
}
.promo-message {
    width: 100%;
    text-align: center;
    font-size: 14px;
    min-height: 20px;
    color: var(--accent-gold);
}

/* ===== WITHDRAW ===== */
#withdraw-btn {
    margin: 12px 0 20px;
    width: 100%;
    max-width: 400px;
}

/* ===== RESPONSIVE ===== */
@media (max-width: 420px) {
    .games-grid {
        gap: 8px;
    }
    .game-card-content {
        padding: 8px;
        min-height: 140px;
    }
    .game-card .game-image {
        height: 120px;
    }
    .game-card .game-name {
        font-size: 11px;
    }
    .reel {
        width: 64px;
        height: 80px;
        font-size: 36px;
    }
    .rocket-multiplier {
        font-size: 36px;
    }
    .clicker-circle {
        width: 130px;
        height: 130px;
    }
    .clicker-icon {
        font-size: 38px;
    }
    .resource-value {
        font-size: 12px;
    }
    .boost-card {
        grid-template-columns: 32px 1fr auto auto;
        padding: 10px 12px;
    }
    .key-icon {
        width: 220px;
        height: 220px;
    }
    .mode-btn {
        padding: 6px 16px;
        font-size: 12px;
    }
}
""")

# JavaScript (исправленная анимация)
with open(os.path.join(STATIC_DIR, "script.js"), "w", encoding="utf-8") as f:
    f.write("""const BASE_URL = window.location.origin;
let current_user = null;
let balance = 0;
let currentMode = 'light';
let isSpinning = false;

// ========== КЛИКЕР ПЕРЕМЕННЫЕ ==========
let clickerStars = 0;
let clickerCrystals = 0;
let clickerEnergy = 15;
let maxEnergy = 15;
let clickPower = 1;
let autoClickLevel = 0;
let multiplierLevel = 0;
let crystalBoostLevel = 0;
let autoClickInterval = null;
let energyRegenInterval = null;
let isClicking = false;

// ========== ЭКРАН ВХОДА ==========
document.getElementById('login-btn').addEventListener('click', async () => {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value.trim();
    const errorEl = document.getElementById('login-error');
    
    if (!username || !password) {
        errorEl.textContent = 'Заполните все поля!';
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
            await initGames();
            await loadClickerData();
            if (data.telegram_id) loadAvatar(data.telegram_id);
        } else {
            errorEl.textContent = data.detail || 'Ошибка входа';
        }
    } catch (e) {
        errorEl.textContent = 'Ошибка соединения с сервером';
        console.error(e);
    }
});

document.getElementById('login-password').addEventListener('keypress', (e) => {
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
    } catch (e) { console.error(e); }
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
    } catch (e) { console.error(e); }
}

function updateBalanceUI(newBalance) {
    balance = newBalance;
    document.getElementById('balance-amount').textContent = newBalance;
}

// ========== НАВИГАЦИЯ ==========
function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const page = document.getElementById(pageId + '-page');
    if (page) page.classList.add('active');
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    const navBtn = document.querySelector(`.nav-btn[data-tab="${pageId}"]`);
    if (navBtn) navBtn.classList.add('active');
    
    if (pageId === 'home') {
        document.getElementById('key-container').style.display = 'flex';
        document.getElementById('wheel-wrapper').style.display = 'none';
    }
    if (pageId === 'rocket') {
        fetchUserData();
        if (!rocketActive) {
            isRocketRoundFinished = true;
            document.getElementById('rocket-start-btn').disabled = false;
            document.getElementById('rocket-cashout-btn').disabled = true;
        }
    }
    if (pageId === 'clicker') {
        loadClickerData();
    }
}

document.querySelectorAll('.nav-btn[data-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
        showPage(btn.dataset.tab);
    });
});

document.querySelectorAll('.btn-back').forEach(btn => {
    btn.addEventListener('click', () => {
        showPage(btn.dataset.back);
    });
});

document.querySelectorAll('.game-card').forEach(card => {
    card.addEventListener('click', () => {
        showPage(card.dataset.tab);
    });
});

// ========== РЕФЕРАЛКА ==========
document.getElementById('user-info').addEventListener('click', async () => {
    if (!current_user) return;
    try {
        const resp = await fetch(`/api/referral/${current_user.id}`);
        const data = await resp.json();
        document.getElementById('ref-link').textContent = data.link;
        document.getElementById('ref-count').textContent = data.count;
        document.getElementById('referral-modal').style.display = 'flex';
    } catch (e) { alert('Ошибка загрузки реферальной информации'); }
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
        navigator.clipboard.writeText(link).then(() => alert('Ссылка скопирована!')).catch(() => fallbackCopy(link));
    } else fallbackCopy(link);
});

function fallbackCopy(text) {
    const input = document.createElement('input');
    input.style.position = 'fixed';
    input.style.opacity = '0';
    input.value = text;
    document.body.appendChild(input);
    input.select();
    try { document.execCommand('copy'); alert('Ссылка скопирована!'); } catch (e) { alert('Не удалось скопировать: ' + text); }
    document.body.removeChild(input);
}

// ========== СТАВКИ ==========
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
    } catch (e) { alert('Ошибка загрузки ставок'); }
});

document.getElementById('close-bets-modal').addEventListener('click', () => {
    document.getElementById('bets-modal').style.display = 'none';
});
document.getElementById('bets-modal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) document.getElementById('bets-modal').style.display = 'none';
});

// ========== ПРОМОКОД ==========
document.getElementById('promo-btn').addEventListener('click', async () => {
    if (!current_user) return;
    const code = document.getElementById('promo-input').value.trim();
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
            document.getElementById('promo-input').value = '';
            balance = data.new_balance;
            document.getElementById('balance-amount').textContent = balance;
        } else msg.textContent = '❌ ' + data.detail;
    } catch (e) { msg.textContent = 'Ошибка соединения'; }
});

// ========== ПОПОЛНЕНИЕ ==========
document.getElementById('deposit-btn').addEventListener('click', () => {
    const menu = document.getElementById('deposit-menu');
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
});
document.getElementById('close-deposit').addEventListener('click', () => {
    document.getElementById('deposit-menu').style.display = 'none';
});

document.querySelectorAll('.deposit-option').forEach(btn => {
    btn.addEventListener('click', async () => {
        const amount = parseInt(btn.dataset.amount);
        if (!current_user) { alert('Ошибка авторизации.'); return; }
        try {
            const resp = await fetch('/api/create_payment', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: current_user.id, amount })
            });
            const data = await resp.json();
            if (resp.ok) {
                window.open(data.payment_url, '_blank');
                alert('Ссылка на оплату открыта. После оплаты баланс обновится автоматически.');
            } else alert('Ошибка: ' + data.detail);
        } catch (e) { alert('Ошибка соединения'); }
    });
});

// ========== ВЫВОД ==========
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
    } catch (e) { alert('Ошибка соединения'); }
});

// ========== ВЫХОД ==========
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
        if (autoClickInterval) clearInterval(autoClickInterval);
        if (energyRegenInterval) clearInterval(energyRegenInterval);
        rocketActive = false;
        isRocketRoundFinished = true;
    }
});

// ========== ИНИЦИАЛИЗАЦИЯ ИГР ==========
async function initGames() {
    updateSpinCost();
    const initialBet = parseInt(document.getElementById('bet-range').value);
    document.getElementById('bet-display').textContent = initialBet;
    drawRocket(0, 'idle');
    document.getElementById('rocket-countdown').textContent = '0';
    startAutoRocket();
    startFakeWins();
    buildRouletteStrip();
    showPage('home');
    
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentMode = this.dataset.mode;
            updateSpinCost();
            updateKeyImage(currentMode);
        });
    });
    
    initClicker();
}

// ========== РУЛЕТКА / КЕЙСЫ - БЕСКОНЕЧНАЯ ЛЕНТА ==========
function updateKeyImage(mode) {
    const keyImage = document.getElementById('key-image');
    const images = {
        light: '/IMGlow.png',
        normal: '/IMGnorm.jpg',
        hard: '/IMGhard.jpg'
    };
    keyImage.src = images[mode] || images.light;
}

function buildRouletteStrip() {
    const strip = document.getElementById('wheel-strip');
    strip.innerHTML = '';
    const symbols = ['❌', '🎫'];
    
    const totalCells = 3000;
    for (let i = 0; i < totalCells; i++) {
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
        const cellWidth = cells[0]?.offsetWidth + 4 || 64;
        const containerWidth = container.offsetWidth || 300;
        const targetSymbol = win ? '🎫' : '❌';
        
        // Ищем целевую ячейку
        let targetIndex = -1;
        const midPoint = Math.floor(cells.length / 2);
        const searchRange = 300;
        
        for (let i = midPoint - searchRange; i <= midPoint + searchRange && i < cells.length; i++) {
            if (i >= 0 && cells[i].textContent === targetSymbol) {
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
        if (targetIndex === -1) targetIndex = midPoint;
        
        // ОГРАНИЧИВАЕМ СМЕЩЕНИЕ
        let targetOffset = targetIndex * cellWidth + cellWidth/2 - containerWidth/2;
        const maxOffset = (cells.length - 10) * cellWidth - containerWidth;
        targetOffset = Math.min(targetOffset, maxOffset);
        targetOffset = Math.max(targetOffset, 0);
        
        // МИНИМАЛЬНЫЕ ОБОРОТЫ (1-2)
        const loops = 1 + Math.floor(Math.random() * 2);
        const usableLength = cells.length * 0.2;
        const totalOffset = targetOffset + loops * usableLength * cellWidth;
        
        // НАЧАЛО С СЕРЕДИНЫ
        const startOffset = midPoint * cellWidth - containerWidth / 2;
        strip.style.transform = `translateX(-${startOffset}px)`;
        
        const duration = 8000 + Math.random() * 4000;
        const startTime = performance.now();
        const startPos = startOffset;
        const endPos = totalOffset;
        
        function easeInOutCubic(t) {
            return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        }
        
        function animate(now) {
            const elapsed = now - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const easedProgress = easeInOutCubic(progress);
            
            const currentOffset = startPos + (endPos - startPos) * easedProgress;
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

function updateSpinCost() {
    const costs = { light: 25, normal: 50, hard: 100 };
    const cost = costs[currentMode];
    document.getElementById('spin-cost').textContent = cost;
    document.getElementById('spin-cost-label').textContent = cost + ' Токенов';
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
    btn.innerHTML = 'ОТКРЫТЬ <span>Загрузка...</span>';
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
            document.getElementById('result-message').style.color = data.win ? '#4CAF50' : '#ff6b6b';
            if (data.win) addFakeWinToFeed(current_user.username, data.prize_name, data.prize_value);
            setTimeout(() => {
                document.getElementById('key-container').style.display = 'flex';
                document.getElementById('wheel-wrapper').style.display = 'none';
            }, 3000);
        } else {
            document.getElementById('result-message').textContent = '❌ ' + data.detail;
        }
    } catch (e) {
        document.getElementById('result-message').textContent = 'Ошибка соединения';
    }
    isSpinning = false;
    btn.disabled = false;
    const cost2 = { light:25, normal:50, hard:100 }[currentMode];
    btn.innerHTML = 'ОТКРЫТЬ <span>' + cost2 + ' Токенов</span>';
});

// ========== СЛОТ ==========
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
        reels.forEach(reel => { reel.textContent = slotSymbols[Math.floor(Math.random()*slotSymbols.length)]; });
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
                resultDiv.style.color = '#ff6b6b';
            }
        } else { document.getElementById('slot-result').textContent = '❌ ' + data.detail; }
    } catch (e) {
        clearInterval(interval);
        document.getElementById('slot-result').textContent = 'Ошибка соединения';
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
        for (let i = 1; i < rocketTrail.length; i++) ctx.lineTo(rocketTrail[i].x, rocketTrail[i].y);
        ctx.strokeStyle = 'rgba(255,213,74,0.2)';
        ctx.lineWidth = 2;
        ctx.stroke();
    }
    if (status === 'crashed') {
        ctx.font = '40px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('💥', explosionX, explosionY);
        if (falling) { ctx.font = '20px sans-serif'; ctx.fillText('🚀', rocketX, fallY); }
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
    ctx.fillStyle = '#FFD54A';
    ctx.font = '12px sans-serif';
    ctx.fillText((multiplier || 0).toFixed(2) + 'x', rocketX, rocketY - 25);
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
            rocketX = 30; rocketY = 170;
            rocketTrail = [{x:rocketX, y:rocketY}];
            startTime = Date.now();
            if (rocketInterval) clearInterval(rocketInterval);
            rocketInterval = setInterval(updateRocketStatus, 150);
            if (rocketAnimationFrame) cancelAnimationFrame(rocketAnimationFrame);
            animateRocket();
        } else alert('❌ ' + data.detail);
    } catch (e) { alert('Ошибка соединения'); }
});

function animateRocket() {
    if (!rocketActive && !falling) {
        if (!isRocketRoundFinished) { rocketAnimationFrame = requestAnimationFrame(animateRocket); }
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
            falling = false; isCrashed = false; isRocketRoundFinished = true;
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
                document.getElementById('rocket-result').style.color = '#ff6b6b';
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
        }
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
    } catch (e) { alert('Ошибка соединения'); }
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

// ========== КЛИКЕР ==========
async function loadClickerData() {
    if (!current_user) return;
    try {
        const resp = await fetch(`/api/clicker_data/${current_user.id}`);
        const data = await resp.json();
        if (resp.ok) {
            clickerStars = data.clicker_balance || 0;
            clickerCrystals = data.crystal_boost_level * 10 || 0;
            clickerEnergy = data.energy || 15;
            maxEnergy = data.max_energy || 15;
            clickPower = data.click_power || 1;
            autoClickLevel = data.auto_click_level || 0;
            multiplierLevel = data.multiplier_level || 0;
            crystalBoostLevel = data.crystal_boost_level || 0;
            
            updateClickerUI();
            updateBoostButtons();
        }
    } catch (e) { console.error('Ошибка загрузки данных кликера:', e); }
}

function updateClickerUI() {
    document.getElementById('clicker-stars').textContent = formatNumber(clickerStars);
    document.getElementById('clicker-crystals').textContent = formatNumber(clickerCrystals);
    document.getElementById('clicker-energy').textContent = `${clickerEnergy}/${maxEnergy}`;
    document.getElementById('clicker-plus').textContent = `+${clickPower}`;
    document.getElementById('auto-level').textContent = autoClickLevel;
    document.getElementById('multiplier-level').textContent = multiplierLevel;
    document.getElementById('crystal-level').textContent = crystalBoostLevel;
    
    const autoPrice = 500 * Math.pow(1.5, autoClickLevel);
    const multiplierPrice = 1000 * Math.pow(2, multiplierLevel);
    const crystalPrice = 2000 * Math.pow(1.8, crystalBoostLevel);
    
    document.getElementById('auto-price').textContent = formatNumber(Math.floor(autoPrice));
    document.getElementById('multiplier-price').textContent = formatNumber(Math.floor(multiplierPrice));
    document.getElementById('crystal-price').textContent = formatNumber(Math.floor(crystalPrice));
}

function updateBoostButtons() {
    const autoPrice = 500 * Math.pow(1.5, autoClickLevel);
    const multiplierPrice = 1000 * Math.pow(2, multiplierLevel);
    const crystalPrice = 2000 * Math.pow(1.8, crystalBoostLevel);
    
    document.querySelectorAll('.boost-btn').forEach(btn => {
        const boost = btn.dataset.boost;
        let price = 0;
        if (boost === 'auto') price = Math.floor(autoPrice);
        else if (boost === 'multiplier') price = Math.floor(multiplierPrice);
        else if (boost === 'crystal') price = Math.floor(crystalPrice);
        
        btn.disabled = clickerStars < price;
        btn.parentElement.classList.toggle('disabled', clickerStars < price);
    });
}

function initClicker() {
    const circle = document.getElementById('clicker-circle');
    const area = document.getElementById('clicker-area');
    
    circle.addEventListener('click', handleClick);
    area.addEventListener('touchstart', (e) => {
        e.preventDefault();
        handleClick(e);
    });
    
    document.querySelectorAll('.boost-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const boost = btn.dataset.boost;
            await buyBoost(boost);
        });
    });
    
    document.getElementById('sell-clicks-btn').addEventListener('click', sellClicks);
    
    startAutoClicker();
    startEnergyRegeneration();
}

function handleClick(e) {
    if (!current_user || clickerEnergy <= 0) {
        if (clickerEnergy <= 0) {
            const msg = document.getElementById('sell-message');
            msg.textContent = '❌ Нет энергии! Подождите восстановления.';
            msg.style.color = '#ff6b6b';
            setTimeout(() => { msg.textContent = ''; }, 2000);
        }
        return;
    }
    
    clickerEnergy--;
    const starsEarned = clickPower * (1 + multiplierLevel * 0.1);
    clickerStars += starsEarned;
    clickerCrystals += 0.1 * (1 + crystalBoostLevel * 0.05);
    
    animateClick(e);
    
    updateClickerUI();
    updateBoostButtons();
    
    saveClickerData(starsEarned);
}

function animateClick(e) {
    const circle = document.getElementById('clicker-circle');
    const plus = document.getElementById('clicker-plus');
    
    circle.style.transform = 'scale(0.92)';
    setTimeout(() => {
        circle.style.transform = 'scale(1)';
    }, 100);
    
    const clone = plus.cloneNode(true);
    clone.style.position = 'absolute';
    clone.style.left = '50%';
    clone.style.top = '50%';
    clone.style.transform = 'translate(-50%, -50%)';
    clone.style.fontSize = '28px';
    clone.style.color = '#4FC3F7';
    clone.style.pointerEvents = 'none';
    clone.style.opacity = '1';
    circle.appendChild(clone);
    
    let y = -30;
    const anim = setInterval(() => {
        y -= 2;
        clone.style.transform = `translate(-50%, ${y}px)`;
        clone.style.opacity -= 0.02;
        if (y < -100) {
            clearInterval(anim);
            clone.remove();
        }
    }, 16);
}

async function saveClickerData(starsEarned) {
    if (!current_user) return;
    try {
        await fetch('/api/clicker_update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: current_user.id,
                stars: Math.floor(starsEarned),
                energy: -1
            })
        });
    } catch (e) { console.error('Ошибка сохранения кликера:', e); }
}

async function buyBoost(boost) {
    if (!current_user) return;
    
    let price = 0;
    let level = 0;
    let type = boost;
    
    if (boost === 'auto') {
        price = Math.floor(500 * Math.pow(1.5, autoClickLevel));
        level = autoClickLevel;
    } else if (boost === 'multiplier') {
        price = Math.floor(1000 * Math.pow(2, multiplierLevel));
        level = multiplierLevel;
    } else if (boost === 'crystal') {
        price = Math.floor(2000 * Math.pow(1.8, crystalBoostLevel));
        level = crystalBoostLevel;
    }
    
    if (clickerStars < price) {
        const msg = document.getElementById('sell-message');
        msg.textContent = '❌ Недостаточно звезд!';
        msg.style.color = '#ff6b6b';
        setTimeout(() => { msg.textContent = ''; }, 2000);
        return;
    }
    
    clickerStars -= price;
    
    if (boost === 'auto') autoClickLevel++;
    else if (boost === 'multiplier') multiplierLevel++;
    else if (boost === 'crystal') crystalBoostLevel++;
    
    updateClickerUI();
    updateBoostButtons();
    
    try {
        await fetch('/api/clicker_update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: current_user.id,
                stars: -price,
                auto_level: autoClickLevel,
                multiplier_level: multiplierLevel,
                crystal_level: crystalBoostLevel
            })
        });
        
        const msg = document.getElementById('sell-message');
        msg.textContent = '✅ Улучшение куплено!';
        msg.style.color = '#4CAF50';
        setTimeout(() => { msg.textContent = ''; }, 2000);
        
        startAutoClicker();
    } catch (e) {
        console.error('Ошибка покупки буста:', e);
    }
}

function startAutoClicker() {
    if (autoClickInterval) clearInterval(autoClickInterval);
    
    if (autoClickLevel > 0) {
        const interval = Math.max(1000, 3000 - autoClickLevel * 150);
        autoClickInterval = setInterval(() => {
            if (current_user && clickerEnergy > 0 && autoClickLevel > 0) {
                const starsEarned = clickPower * (1 + multiplierLevel * 0.1) * 0.3 * (1 + autoClickLevel * 0.1);
                clickerStars += Math.floor(starsEarned);
                clickerEnergy = Math.max(0, clickerEnergy - 0.5);
                
                updateClickerUI();
                updateBoostButtons();
                
                saveClickerData(Math.floor(starsEarned));
            }
        }, interval);
    }
}

function startEnergyRegeneration() {
    if (energyRegenInterval) clearInterval(energyRegenInterval);
    
    energyRegenInterval = setInterval(() => {
        if (clickerEnergy < maxEnergy) {
            clickerEnergy = Math.min(maxEnergy, clickerEnergy + 1);
            updateClickerUI();
        }
    }, 3000);
}

async function sellClicks() {
    if (!current_user) return;
    
    const clicksToSell = Math.floor(clickerStars);
    if (clicksToSell < 1000) {
        const msg = document.getElementById('sell-message');
        msg.textContent = '❌ Нужно минимум 1000 кликов для продажи!';
        msg.style.color = '#ff6b6b';
        setTimeout(() => { msg.textContent = ''; }, 3000);
        return;
    }
    
    const tokensEarned = Math.floor(clicksToSell / 1000);
    
    try {
        const resp = await fetch('/api/sell_clicks', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: current_user.id,
                clicks: clicksToSell
            })
        });
        const data = await resp.json();
        
        if (resp.ok) {
            clickerStars = data.remaining_clicks;
            balance = data.new_balance;
            document.getElementById('balance-amount').textContent = balance;
            updateClickerUI();
            updateBoostButtons();
            
            const msg = document.getElementById('sell-message');
            msg.textContent = `✅ Продано ${clicksToSell} кликов! Получено ${tokensEarned} токенов!`;
            msg.style.color = '#4CAF50';
            setTimeout(() => { msg.textContent = ''; }, 4000);
        } else {
            const msg = document.getElementById('sell-message');
            msg.textContent = '❌ ' + data.detail;
            msg.style.color = '#ff6b6b';
            setTimeout(() => { msg.textContent = ''; }, 3000);
        }
    } catch (e) {
        console.error('Ошибка продажи кликов:', e);
    }
}

function formatNumber(num) {
    if (num >= 1e6) return (num / 1e6).toFixed(1) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(1) + 'K';
    return Math.floor(num).toString();
}

// ========== ФИД ПОБЕД ==========
function startFakeWins() {
    setInterval(() => {
        const isWin = Math.random() < 0.75;
        const fakeUsers = ['user_' + (100000 + Math.floor(Math.random()*900000)), 
                           'player_' + (200000 + Math.floor(Math.random()*800000)), 
                           'gamer_' + (300000 + Math.floor(Math.random()*700000)), 
                           'winner_' + (400000 + Math.floor(Math.random()*600000))];
        const username = fakeUsers[Math.floor(Math.random()*fakeUsers.length)];
        const prizes = ['🎰 Слот', '🎡 Кейсы', '🚀 Ракетка', '🎁 Подарок'];
        const prize = prizes[Math.floor(Math.random()*prizes.length)];
        const amount = Math.floor(Math.random() * 150) + 10;
        if (isWin) addFakeWinToFeed(username, prize, amount);
        else addFakeLoseToFeed(username, prize, 'проиграл');
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

class ClickerUpdateRequest(BaseModel):
    user_id: int
    stars: int = 0
    energy: int = 0
    auto_level: int = None
    multiplier_level: int = None
    crystal_level: int = None

class SellClicksRequest(BaseModel):
    user_id: int
    clicks: int

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

@app.get("/api/clicker_data/{user_id}")
async def api_get_clicker_data(user_id: int):
    data = get_clicker_data(user_id)
    if not data:
        raise HTTPException(status_code=404, detail="User not found")
    return data

@app.post("/api/clicker_update")
async def api_update_clicker(data: ClickerUpdateRequest):
    user = get_user_by_id(data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    if data.stars != 0:
        cur.execute("UPDATE users SET clicker_balance = clicker_balance + ? WHERE id = ?", (data.stars, data.user_id))
    
    if data.energy != 0:
        cur.execute("UPDATE users SET energy = energy + ? WHERE id = ?", (data.energy, data.user_id))
    
    if data.auto_level is not None:
        cur.execute("UPDATE users SET auto_click_level = ? WHERE id = ?", (data.auto_level, data.user_id))
    
    if data.multiplier_level is not None:
        cur.execute("UPDATE users SET multiplier_level = ? WHERE id = ?", (data.multiplier_level, data.user_id))
    
    if data.crystal_level is not None:
        cur.execute("UPDATE users SET crystal_boost_level = ? WHERE id = ?", (data.crystal_level, data.user_id))
    
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/sell_clicks")
async def api_sell_clicks(data: SellClicksRequest):
    user = get_user_by_id(data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if data.clicks < 1000:
        raise HTTPException(status_code=400, detail="Нужно минимум 1000 кликов для продажи")
    
    tokens = data.clicks // 1000
    remaining = data.clicks % 1000
    
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    
    cur.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (tokens, data.user_id))
    cur.execute("UPDATE users SET clicker_balance = clicker_balance - ? WHERE id = ?", (data.clicks, data.user_id))
    
    cur.execute("SELECT username FROM users WHERE id = ?", (data.user_id,))
    username_row = cur.fetchone()
    username = username_row[0] if username_row else None
    
    cur.execute(
        "INSERT INTO transactions (user_id, username, type, amount, description) VALUES (?, ?, ?, ?, ?)",
        (data.user_id, username, "deposit", tokens, f"Продажа кликов: {data.clicks} кликов = {tokens} токенов")
    )
    
    conn.commit()
    conn.close()
    
    new_balance = get_user_by_id(data.user_id)["balance"]
    return {
        "remaining_clicks": remaining,
        "new_balance": new_balance,
        "tokens_earned": tokens
    }

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
    
    crash_display = random.uniform(0.01, 2.50)
    
    if crash_display < 1.00:
        if random.random() < 0.70:
            pass
        else:
            crash_display = random.uniform(1.00, 2.50)
    else:
        if random.random() < 0.90:
            pass
        else:
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
