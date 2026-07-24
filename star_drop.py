import os
import sys
import asyncio
import logging
import sqlite3
import random
import signal
import time
import string
from datetime import datetime
from typing import Optional, List, Dict
import json
import hashlib

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8988678866:AAHIWxUB8zKBCoF21g7OVYEEWnwEF_MpLmI"

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

PRIZES = {
    "light": [
        {"name": "🧸 Мишка", "value": 15},
        {"name": "🍬 Конфета", "value": 20},
        {"name": "⭐ Звезда", "value": 25},
        {"name": "🌹 Роза", "value": 40},
        {"name": "💨 Пусто", "value": 0},
        {"name": "🧸 Мишка", "value": 10},
        {"name": "💨 Пусто", "value": 0},
        {"name": "⭐ Звезда", "value": 20},
    ],
    "normal": [
        {"name": "💍 Кольцо", "value": 120},
        {"name": "💎 Бриллиант", "value": 200},
        {"name": "🧁 Торт", "value": 150},
        {"name": "🏆 Кубок", "value": 250},
        {"name": "💨 Пусто", "value": 0},
        {"name": "💍 Кольцо", "value": 100},
        {"name": "💨 Пусто", "value": 0},
        {"name": "💎 Бриллиант", "value": 180},
    ],
    "hard": [
        {"name": "👑 Корона", "value": 600},
        {"name": "🧢 Кепка Дурова", "value": 800},
        {"name": "🚀 Ракета", "value": 700},
        {"name": "🛸 НЛО", "value": 1000},
        {"name": "💨 Пусто", "value": 0},
        {"name": "👑 Корона", "value": 500},
        {"name": "💨 Пусто", "value": 0},
        {"name": "🚀 Ракета", "value": 650},
    ]
}

DB_NAME = "star_drop.db"
WEBAPP_URL = "https://star-drop.onrender.com"
REFERRAL_BONUS = 50

SLOT_SYMBOLS = ['🍒', '🍋', '🍊', '🍇', '🍉', '🍓', '🍑', '🎰']
SLOT_WIN_MULTIPLIER = 2

PROMOCODES = {
    "rifleman": 50,
}

rocket_rounds = {}
round_counter = 0

# Хранилище кодов верификации
verification_codes = {}  # user_id -> {code, expires_at}

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
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

def create_user(user_id: int, username: str = None, referrer_code: str = None):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    code = hashlib.md5(str(user_id).encode()).hexdigest()[:8]
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, username, referral_code) VALUES (?, ?, ?)",
        (user_id, username, code)
    )
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
def generate_verification_code():
    """Генерирует 4-символьный код из букв (кроме похожих) и цифр."""
    chars = string.ascii_lowercase + string.digits
    # исключаем похожие: 0, o, 1, l
    chars = [c for c in chars if c not in '01ol']
    return ''.join(random.choice(chars) for _ in range(4))

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
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

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
    create_user(user_id, username, referrer_code)
    await message.answer(
        f"🎉 Приветствую тебя, {username}!\n"
        "Добро пожаловать в **Star Drop** – розыгрыш подарков Telegram!\n\n"
        "Нажми кнопку ниже, чтобы открыть наше мини-приложение и испытать удачу! 🍀",
        reply_markup=get_start_keyboard()
    )

# ==================== ВЕБ-СЕРВЕР (FASTAPI) ====================
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = "static"
os.makedirs(STATIC_DIR, exist_ok=True)

# ==================== СТАТИЧЕСКИЕ ФАЙЛЫ ====================
STATIC_FILES = {
    "index.html": """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Star Drop</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body class="theme-light">
    <div class="stars-background">
        <span>⭐</span><span>✨</span><span>🌟</span><span>💫</span>
        <span>🎁</span><span>🧸</span><span>💎</span><span>🧢</span>
        <span>🚀</span><span>💍</span><span>🧁</span><span>🎈</span>
        <span>👑</span><span>🛸</span><span>💎</span><span>🎁</span>
    </div>

    <!-- Экран входа -->
    <div id="login-screen">
        <div id="login-card">
            <h1>🚀 Star Drop</h1>
            <p>Войдите, чтобы продолжить</p>
            <button id="login-btn">Войти через Telegram</button>
            <div id="code-section" style="display:none; margin-top:15px;">
                <p>Введите код из Telegram</p>
                <input type="text" id="code-input" placeholder="Код" maxlength="4" style="padding:10px; border-radius:8px; border:1px solid var(--accent-color); background:#222; color:#fff; text-align:center; font-size:20px; width:120px; text-transform:lowercase;">
                <br>
                <button id="verify-btn" style="margin-top:10px;">Подтвердить</button>
                <p id="login-message" style="color:var(--accent-color); margin-top:8px;"></p>
            </div>
        </div>
    </div>

    <!-- Основное приложение (скрыто до входа) -->
    <div id="app-content" style="display:none; width:100%; max-width:400px;">

        <div id="top-bar">
            <div id="user-info" style="display:flex; align-items:center; gap:10px; cursor:pointer;">
                <div id="avatar" style="width:32px; height:32px; border-radius:50%; background:var(--accent-color); display:flex; align-items:center; justify-content:center; font-weight:bold; font-size:16px; color:#0a0a0a;">U</div>
                <span id="username">@user</span>
            </div>
            <div id="balance">
                <span id="balance-amount">0</span> 🌟
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

        <!-- РУЛЕТКА -->
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
                <canvas id="wheelCanvas" width="300" height="300"></canvas>
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

        <!-- РАКЕТКА -->
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

    <script src="/static/script.js"></script>
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
}
body.theme-normal {
    --accent-color: #2196F3;
    --accent-glow: #2196F366;
}
body.theme-hard {
    --accent-color: #f44336;
    --accent-glow: #f4433666;
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
    animation: fall linear infinite;
    opacity: 0.4;
    color: var(--accent-color);
    text-shadow: 0 0 8px var(--accent-glow);
    font-size: 18px;
}

.stars-background span:nth-child(1) { left: 5%; animation-duration: 8s; font-size: 16px; }
.stars-background span:nth-child(2) { left: 15%; animation-duration: 12s; font-size: 22px; animation-delay: 1s; }
.stars-background span:nth-child(3) { left: 25%; animation-duration: 7s; font-size: 14px; animation-delay: 2s; }
.stars-background span:nth-child(4) { left: 35%; animation-duration: 10s; font-size: 20px; animation-delay: 0.5s; }
.stars-background span:nth-child(5) { left: 45%; animation-duration: 9s; font-size: 24px; animation-delay: 3s; }
.stars-background span:nth-child(6) { left: 55%; animation-duration: 6s; font-size: 18px; animation-delay: 1.5s; }
.stars-background span:nth-child(7) { left: 65%; animation-duration: 11s; font-size: 28px; animation-delay: 2.5s; }
.stars-background span:nth-child(8) { left: 75%; animation-duration: 8s; font-size: 16px; animation-delay: 4s; }
.stars-background span:nth-child(9) { left: 85%; animation-duration: 10s; font-size: 20px; animation-delay: 0.8s; }
.stars-background span:nth-child(10) { left: 92%; animation-duration: 7s; font-size: 14px; animation-delay: 3.5s; }
.stars-background span:nth-child(11) { left: 10%; animation-duration: 13s; font-size: 26px; animation-delay: 5s; }
.stars-background span:nth-child(12) { left: 40%; animation-duration: 9s; font-size: 30px; animation-delay: 1.2s; }
.stars-background span:nth-child(13) { left: 70%; animation-duration: 11s; font-size: 22px; animation-delay: 2.8s; }
.stars-background span:nth-child(14) { left: 20%; animation-duration: 8s; font-size: 18px; animation-delay: 4.5s; }
.stars-background span:nth-child(15) { left: 60%; animation-duration: 12s; font-size: 28px; animation-delay: 0.2s; }
.stars-background span:nth-child(16) { left: 80%; animation-duration: 7s; font-size: 20px; animation-delay: 3.8s; }

@keyframes fall {
    0% { transform: translateY(-30px) rotate(0deg); opacity: 0; }
    20% { opacity: 0.7; }
    80% { opacity: 0.7; }
    100% { transform: translateY(105vh) rotate(720deg); opacity: 0; }
}

#login-screen {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 80vh;
    width: 100%;
}

#login-card {
    background: var(--card-bg);
    border: 1px solid var(--accent-color);
    border-radius: 20px;
    padding: 30px 20px;
    text-align: center;
    max-width: 320px;
    width: 100%;
    box-shadow: 0 0 40px var(--accent-glow);
}

#login-card h1 {
    color: var(--accent-color);
    font-size: 28px;
    margin-bottom: 10px;
}

#login-card p {
    color: #aaa;
    margin-bottom: 20px;
}

#login-btn, #verify-btn {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 12px 30px;
    border-radius: 30px;
    font-weight: 700;
    font-size: 16px;
    cursor: pointer;
    transition: transform 0.1s, box-shadow 0.3s;
    box-shadow: 0 0 20px var(--accent-glow);
    width: 100%;
    max-width: 250px;
}

#login-btn:active, #verify-btn:active {
    transform: scale(0.95);
}

#code-input {
    padding: 10px;
    border-radius: 8px;
    border: 1px solid var(--accent-color);
    background: #222;
    color: #fff;
    text-align: center;
    font-size: 20px;
    width: 120px;
    text-transform: lowercase;
}

#app-content {
    width: 100%;
    max-width: 400px;
    display: none;
}

/* Остальные стили (как ранее) */
#top-bar {
    display: flex;
    justify-content: space-between;
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

#avatar {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: var(--accent-color);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
    font-size: 16px;
    color: #0a0a0a;
    transition: background 0.3s;
}

#username {
    font-size: 18px;
    font-weight: 600;
    color: var(--accent-color);
    transition: color 0.3s;
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

#prizes-list {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
    margin: 15px 0;
    width: 100%;
    max-width: 400px;
    z-index: 2;
}

.prize-item {
    background: #1a1a1a;
    border: 1px solid var(--border-color);
    border-radius: 20px;
    padding: 6px 14px;
    font-size: 13px;
    color: #ccc;
}

#mode-selector {
    display: flex;
    gap: 12px;
    margin: 10px 0;
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

#wheel-container {
    position: relative;
    width: 280px;
    height: 280px;
    margin: 15px auto;
    z-index: 2;
}

#wheel-pointer {
    position: absolute;
    top: -12px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 24px;
    color: var(--accent-color);
    z-index: 5;
    text-shadow: 0 0 8px var(--accent-glow);
    transition: color 0.3s, text-shadow 0.3s;
}

#wheelCanvas {
    width: 100%;
    height: 100%;
    border-radius: 50%;
    box-shadow: 0 0 30px var(--accent-glow);
    border: 4px solid var(--accent-color);
    transition: transform 3s cubic-bezier(0.15, 0.7, 0.1, 1),
                box-shadow 0.3s,
                border-color 0.3s;
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

/* Слот */
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
    gap: 15px;
    padding: 15px 0;
}

.reel {
    width: 70px;
    height: 80px;
    background: #222;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 48px;
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

/* Ракетка */
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

/* Общие элементы */
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
    justify-content: space-around;
    padding: 10px 0;
    border-top: 1px solid var(--border-color);
    z-index: 10;
}

.nav-btn {
    background: transparent;
    color: #888;
    border: none;
    font-size: 14px;
    font-weight: 600;
    padding: 6px 20px;
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
""",
    "script.js": """const BASE_URL = window.location.origin;
let user_id = null;
let balance = 0;
let currentMode = 'light';
let isSpinning = false;
let currentRotation = 0;

// Получаем Telegram user_id для входа
let tgUserId = null;
if (window.Telegram && window.Telegram.WebApp) {
    window.Telegram.WebApp.ready();
    const tgUser = window.Telegram.WebApp.initDataUnsafe?.user;
    if (tgUser && tgUser.id) {
        tgUserId = tgUser.id;
        console.log('Telegram user ID:', tgUserId);
    }
}

// Проверяем, есть ли сохранённый user_id в localStorage
const savedUserId = localStorage.getItem('starDrop_userId');
if (savedUserId) {
    user_id = parseInt(savedUserId);
    // Загружаем данные пользователя
    fetchUserData().then(() => {
        showApp();
    });
}

// === Экран входа ===
const loginScreen = document.getElementById('login-screen');
const appContent = document.getElementById('app-content');
const loginBtn = document.getElementById('login-btn');
const codeSection = document.getElementById('code-section');
const codeInput = document.getElementById('code-input');
const verifyBtn = document.getElementById('verify-btn');
const loginMsg = document.getElementById('login-message');

loginBtn.addEventListener('click', async () => {
    if (!tgUserId) {
        loginMsg.textContent = 'Не удалось определить аккаунт Telegram';
        return;
    }
    // Отправляем запрос на получение кода
    try {
        const resp = await fetch('/api/send_code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: tgUserId })
        });
        const data = await resp.json();
        if (resp.ok) {
            loginMsg.textContent = 'Код отправлен в Telegram!';
            codeSection.style.display = 'block';
            codeInput.focus();
        } else {
            loginMsg.textContent = 'Ошибка: ' + data.detail;
        }
    } catch (e) {
        loginMsg.textContent = 'Ошибка соединения';
        console.error(e);
    }
});

verifyBtn.addEventListener('click', async () => {
    const code = codeInput.value.trim().toLowerCase();
    if (!code || code.length < 4) {
        loginMsg.textContent = 'Введите 4-символьный код';
        return;
    }
    try {
        const resp = await fetch('/api/verify_code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const data = await resp.json();
        if (resp.ok) {
            user_id = data.user_id;
            localStorage.setItem('starDrop_userId', user_id);
            // Обновляем интерфейс
            document.getElementById('username').textContent = '@' + data.username;
            const avatar = document.getElementById('avatar');
            const name = data.username || 'U';
            avatar.textContent = name.charAt(0).toUpperCase();
            avatar.style.background = '#' + (user_id % 0xFFFFFF).toString(16).padStart(6, '0');
            balance = data.balance;
            document.getElementById('balance-amount').textContent = balance;
            showApp();
        } else {
            loginMsg.textContent = 'Ошибка: ' + data.detail;
        }
    } catch (e) {
        loginMsg.textContent = 'Ошибка соединения';
        console.error(e);
    }
});

function showApp() {
    loginScreen.style.display = 'none';
    appContent.style.display = 'block';
    // Загружаем данные
    fetchUserData();
    // Инициализируем остальные компоненты
    initGames();
}

async function fetchUserData() {
    if (!user_id) return;
    try {
        const resp = await fetch(`/api/user/${user_id}`);
        if (!resp.ok) throw new Error('User not found');
        const data = await resp.json();
        balance = data.balance;
        document.getElementById('balance-amount').textContent = balance;
        if (data.username) {
            document.getElementById('username').textContent = '@' + data.username;
            const avatar = document.getElementById('avatar');
            avatar.textContent = (data.username || 'U').charAt(0).toUpperCase();
        }
    } catch (e) {
        console.error(e);
    }
}

function updateBalanceUI(newBalance) {
    balance = newBalance;
    document.getElementById('balance-amount').textContent = newBalance;
}

// === Клик по юзеру — рефералка ===
document.getElementById('user-info').addEventListener('click', async () => {
    if (!user_id) return;
    try {
        const resp = await fetch(`/api/referral/${user_id}`);
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

document.getElementById('copy-ref-link').addEventListener('click', () => {
    const link = document.getElementById('ref-link').textContent;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(() => {
            alert('Ссылка скопирована!');
        }).catch(() => {
            fallbackCopy(link);
        });
    } else {
        fallbackCopy(link);
    }
});

function fallbackCopy(text) {
    const input = document.createElement('input');
    input.style.position = 'fixed';
    input.style.opacity = '0';
    input.value = text;
    document.body.appendChild(input);
    input.select();
    try {
        document.execCommand('copy');
        alert('Ссылка скопирована!');
    } catch (e) {
        alert('Не удалось скопировать, скопируйте вручную: ' + text);
    }
    document.body.removeChild(input);
}

// === Мои ставки ===
document.getElementById('bets-btn').addEventListener('click', async () => {
    if (!user_id) return;
    try {
        const resp = await fetch(`/api/user_bets/${user_id}`);
        const bets = await resp.json();
        const list = document.getElementById('bets-list');
        list.innerHTML = '';
        if (bets.length === 0) {
            list.innerHTML = '<li style="color:#aaa;">Ставок пока нет</li>';
        } else {
            bets.forEach(b => {
                const li = document.createElement('li');
                let sign = '';
                let cls = '';
                if (b.amount > 0) { sign = '+'; cls = 'positive'; }
                else if (b.amount < 0) { sign = ''; cls = 'negative'; }
                else { sign = '0'; cls = ''; }
                li.innerHTML = `<span class="${cls}">${sign}${b.amount}</span> ${b.description} <span style="color:#888;font-size:12px;">${new Date(b.created_at).toLocaleString()}</span>`;
                list.appendChild(li);
            });
        }
        document.getElementById('bets-modal').style.display = 'flex';
    } catch (e) {
        alert('Ошибка загрузки ставок');
        console.error(e);
    }
});

document.getElementById('close-bets-modal').addEventListener('click', () => {
    document.getElementById('bets-modal').style.display = 'none';
});

document.getElementById('bets-modal').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) {
        document.getElementById('bets-modal').style.display = 'none';
    }
});

// === Промокоды ===
document.getElementById('promo-btn').addEventListener('click', async () => {
    if (!user_id) return;
    const input = document.getElementById('promo-input');
    const code = input.value.trim();
    const msg = document.getElementById('promo-message');
    if (!code) {
        msg.textContent = 'Введите промокод';
        return;
    }
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
            balance = data.new_balance;
            document.getElementById('balance-amount').textContent = balance;
        } else {
            msg.textContent = '❌ ' + data.detail;
        }
    } catch (e) {
        msg.textContent = 'Ошибка соединения';
        console.error(e);
    }
});

// === Инициализация игр ===
function initGames() {
    // РУЛЕТКА
    applyTheme('light');
    drawWheel();
    updateSpinCost();

    // СЛОТ
    const initialBet = parseInt(document.getElementById('bet-range').value);
    document.getElementById('bet-display').textContent = initialBet;

    // РАКЕТКА
    drawRocket(0, 'idle');
    document.getElementById('rocket-countdown').textContent = '0';
}

// === РУЛЕТКА ===
function applyTheme(mode) {
    document.body.classList.remove('theme-light', 'theme-normal', 'theme-hard');
    if (mode === 'light') document.body.classList.add('theme-light');
    else if (mode === 'normal') document.body.classList.add('theme-normal');
    else if (mode === 'hard') document.body.classList.add('theme-hard');
}

document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        if (isSpinning) return;
        document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentMode = btn.dataset.mode;
        updateSpinCost();
        applyTheme(currentMode);
        drawWheel();
    });
});

function updateSpinCost() {
    const costs = { light: 25, normal: 50, hard: 100 };
    const cost = costs[currentMode];
    document.getElementById('spin-cost').textContent = cost;
    document.getElementById('spin-cost-label').textContent = cost + ' Токенов';
}

const canvas = document.getElementById('wheelCanvas');
const ctx = canvas.getContext('2d');

function getPrizesForMode(mode) {
    const allPrizes = {
        light: [
            { name: '🧸', value: 15 },
            { name: '🍬', value: 20 },
            { name: '⭐', value: 25 },
            { name: '🌹', value: 40 },
            { name: '💨', value: 0 },
            { name: '🧸', value: 10 },
            { name: '💨', value: 0 },
            { name: '⭐', value: 20 }
        ],
        normal: [
            { name: '💍', value: 120 },
            { name: '💎', value: 200 },
            { name: '🧁', value: 150 },
            { name: '🏆', value: 250 },
            { name: '💨', value: 0 },
            { name: '💍', value: 100 },
            { name: '💨', value: 0 },
            { name: '💎', value: 180 }
        ],
        hard: [
            { name: '👑', value: 600 },
            { name: '🧢', value: 800 },
            { name: '🚀', value: 700 },
            { name: '🛸', value: 1000 },
            { name: '💨', value: 0 },
            { name: '👑', value: 500 },
            { name: '💨', value: 0 },
            { name: '🚀', value: 650 }
        ]
    };
    return allPrizes[mode] || allPrizes.light;
}

function drawWheel() {
    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) / 2 - 4;
    
    ctx.clearRect(0, 0, width, height);
    const modePrizes = getPrizesForMode(currentMode);
    const count = modePrizes.length;
    const angleStep = (2 * Math.PI) / count;

    for (let i = 0; i < count; i++) {
        const startAngle = i * angleStep;
        const endAngle = startAngle + angleStep;
        
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, startAngle, endAngle);
        ctx.closePath();
        
        if (modePrizes[i].value > 0) {
            ctx.fillStyle = '#2e7d32';
        } else {
            ctx.fillStyle = '#c62828';
        }
        ctx.fill();
        ctx.strokeStyle = '#0a0a0a';
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.save();
        ctx.translate(centerX, centerY);
        ctx.rotate(startAngle + angleStep / 2);
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.font = 'bold 20px sans-serif';
        ctx.fillStyle = '#fff';
        const label = modePrizes[i].name;
        ctx.fillText(label, radius * 0.65, 0);
        ctx.restore();
    }

    ctx.beginPath();
    ctx.arc(centerX, centerY, 22, 0, 2 * Math.PI);
    ctx.fillStyle = '#111';
    ctx.fill();
    ctx.strokeStyle = currentMode === 'light' ? '#ffd700' : (currentMode === 'normal' ? '#2196F3' : '#f44336');
    ctx.lineWidth = 3;
    ctx.stroke();
}

document.getElementById('spin-btn').addEventListener('click', async () => {
    if (!user_id) return;
    if (isSpinning) return;
    isSpinning = true;
    document.getElementById('spin-btn').disabled = true;
    document.getElementById('spin-btn').innerHTML = 'КРУТИТЬ <span>Загрузка...</span>';
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
            const extraSpins = 5 + Math.floor(Math.random() * 3);
            const randomAngle = Math.random() * 360;
            currentRotation += (extraSpins * 360) + randomAngle;
            canvas.style.transform = `rotate(${currentRotation}deg)`;

            setTimeout(() => {
                document.getElementById('result-message').textContent = data.message;
                if (data.win) {
                    document.getElementById('result-message').style.color = '#4CAF50';
                } else {
                    document.getElementById('result-message').style.color = '#f44336';
                }
                if (data.win) fetchFeed();
            }, 3000);
        } else {
            document.getElementById('result-message').textContent = '❌ ' + data.detail;
        }
    } catch (e) {
        document.getElementById('result-message').textContent = 'Ошибка соединения';
        console.error(e);
    }

    setTimeout(() => {
        isSpinning = false;
        document.getElementById('spin-btn').disabled = false;
        const cost = { light: 25, normal: 50, hard: 100 }[currentMode];
        document.getElementById('spin-btn').innerHTML = 'КРУТИТЬ <span>' + cost + ' Токенов</span>';
    }, 3200);
});

// === СЛОТ ===
let slotSpinning = false;
const slotSymbols = ['🍒', '🍋', '🍊', '🍇', '🍉', '🍓', '🍑', '🎰'];
const reels = [
    document.getElementById('reel1'),
    document.getElementById('reel2'),
    document.getElementById('reel3')
];

document.getElementById('bet-range').addEventListener('input', function() {
    document.getElementById('bet-display').textContent = this.value;
});

document.getElementById('spin-slot-btn').addEventListener('click', async () => {
    if (!user_id) return;
    if (slotSpinning) return;
    const bet = parseInt(document.getElementById('bet-range').value);
    if (isNaN(bet) || bet < 20 || bet > 100) {
        alert('Ставка должна быть от 20 до 100 токенов');
        return;
    }
    if (balance < bet) {
        alert('Недостаточно токенов!');
        return;
    }

    slotSpinning = true;
    const btn = document.getElementById('spin-slot-btn');
    btn.disabled = true;
    btn.textContent = '🎰 Крутим...';

    let interval = setInterval(() => {
        reels.forEach(reel => {
            reel.textContent = slotSymbols[Math.floor(Math.random() * slotSymbols.length)];
        });
    }, 100);

    try {
        const resp = await fetch('/api/slot_spin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id, bet })
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
            } else {
                resultDiv.textContent = '😞 Проигрыш. -' + bet + ' токенов';
                resultDiv.style.color = '#f44336';
            }
            if (data.win) fetchFeed();
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

// === РАКЕТКА ===
let rocketInterval = null;
let rocketRoundId = null;
let rocketActive = false;
let rocketCountdown = 5;
let countdownInterval = null;
let rocketAnimationFrame = null;
let rocketCanvas = document.getElementById('rocketCanvas');
let rctx = rocketCanvas.getContext('2d');
let rocketX = 0;
let rocketY = 150;
let rocketSpeed = 1.5;
let rocketTrail = [];

function drawRocket(multiplier, status, crash) {
    rctx.clearRect(0, 0, rocketCanvas.width, rocketCanvas.height);
    
    // Рисуем полосу (траекторию)
    if (rocketTrail.length > 1) {
        rctx.beginPath();
        rctx.moveTo(rocketTrail[0].x, rocketTrail[0].y);
        for (let i = 1; i < rocketTrail.length; i++) {
            rctx.lineTo(rocketTrail[i].x, rocketTrail[i].y);
        }
        rctx.strokeStyle = 'rgba(255,215,0,0.3)';
        rctx.lineWidth = 2;
        rctx.stroke();
    }

    if (status === 'crashed') {
        // Взрыв 💥
        rctx.font = '40px sans-serif';
        rctx.textAlign = 'center';
        rctx.fillText('💥', rocketX, rocketY);
        return;
    }

    // Рисуем ракету 🚀
    rctx.font = '30px sans-serif';
    rctx.textAlign = 'center';
    rctx.fillText('🚀', rocketX, rocketY);

    // Отображаем коэффициент
    rctx.fillStyle = '#ffd700';
    rctx.font = '14px sans-serif';
    rctx.fillText(multiplier.toFixed(2) + 'x', rocketX, rocketY - 20);
}

document.getElementById('rocket-bet-range').addEventListener('input', function() {
    document.getElementById('rocket-bet-display').textContent = this.value;
});

document.getElementById('rocket-start-btn').addEventListener('click', async () => {
    if (!user_id) return;
    if (rocketActive) return;
    const bet = parseInt(document.getElementById('rocket-bet-range').value);
    if (isNaN(bet) || bet < 500 || bet > 5000) {
        alert('Ставка должна быть от 500 до 5000 токенов');
        return;
    }
    if (balance < bet) {
        alert('Недостаточно токенов!');
        return;
    }

    try {
        const resp = await fetch('/api/rocket/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id, bet })
        });
        const data = await resp.json();
        if (resp.ok) {
            rocketRoundId = data.round_id;
            rocketActive = true;
            document.getElementById('rocket-start-btn').disabled = true;
            document.getElementById('rocket-cashout-btn').disabled = false;
            document.getElementById('rocket-result').textContent = '';
            document.getElementById('rocket-status').textContent = '🚀 Взлёт!';
            rocketX = 10;
            rocketY = 150 + (Math.random() - 0.5) * 20;
            rocketTrail = [{x: rocketX, y: rocketY}];
            if (rocketInterval) clearInterval(rocketInterval);
            rocketInterval = setInterval(updateRocketStatus, 150);
            if (rocketAnimationFrame) cancelAnimationFrame(rocketAnimationFrame);
            animateRocket();
        } else {
            alert('❌ ' + data.detail);
        }
    } catch (e) {
        alert('Ошибка соединения');
        console.error(e);
    }
});

function animateRocket() {
    if (!rocketActive) return;
    rocketX += rocketSpeed;
    rocketY += Math.sin(rocketX * 0.1) * 0.5 + (Math.random() - 0.5) * 1.0;
    if (rocketY < 20) rocketY = 20;
    if (rocketY > 180) rocketY = 180;
    rocketTrail.push({x: rocketX, y: rocketY});
    if (rocketTrail.length > 100) rocketTrail.shift();
    rocketAnimationFrame = requestAnimationFrame(animateRocket);
}

async function updateRocketStatus() {
    if (!rocketRoundId) return;
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
                if (rocketInterval) {
                    clearInterval(rocketInterval);
                    rocketInterval = null;
                }
                if (rocketAnimationFrame) {
                    cancelAnimationFrame(rocketAnimationFrame);
                    rocketAnimationFrame = null;
                }
                drawRocket(display, 'crashed', true);
                document.getElementById('rocket-result').textContent = '😞 Ракета упала. Ставка проиграна.';
                document.getElementById('rocket-result').style.color = '#f44336';
                fetchUserData();
                startCountdown();
            } else if (data.cashed_out) {
                document.getElementById('rocket-status').textContent = '💰 Выведено!';
                document.getElementById('rocket-cashout-btn').disabled = true;
                document.getElementById('rocket-start-btn').disabled = false;
                rocketActive = false;
                if (rocketInterval) {
                    clearInterval(rocketInterval);
                    rocketInterval = null;
                }
                if (rocketAnimationFrame) {
                    cancelAnimationFrame(rocketAnimationFrame);
                    rocketAnimationFrame = null;
                }
                fetchUserData();
                startCountdown();
            } else {
                drawRocket(display, 'active', false);
            }
        } else {
            console.error('Status error:', data);
        }
    } catch (e) {
        console.error(e);
    }
}

document.getElementById('rocket-cashout-btn').addEventListener('click', async () => {
    if (!user_id || !rocketRoundId || !rocketActive) return;
    try {
        const resp = await fetch('/api/rocket/cashout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ round_id: rocketRoundId, user_id })
        });
        const data = await resp.json();
        if (resp.ok) {
            document.getElementById('rocket-result').textContent = '🎉 Вы выиграли ' + data.win_amount + ' токенов!';
            document.getElementById('rocket-result').style.color = '#4CAF50';
            document.getElementById('rocket-status').textContent = '💰 Выведено!';
            document.getElementById('rocket-cashout-btn').disabled = true;
            document.getElementById('rocket-start-btn').disabled = false;
            rocketActive = false;
            if (rocketInterval) {
                clearInterval(rocketInterval);
                rocketInterval = null;
            }
            if (rocketAnimationFrame) {
                cancelAnimationFrame(rocketAnimationFrame);
                rocketAnimationFrame = null;
            }
            updateBalanceUI(data.new_balance);
            fetchFeed();
            startCountdown();
        } else {
            alert('❌ ' + data.detail);
        }
    } catch (e) {
        alert('Ошибка соединения');
        console.error(e);
    }
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
            document.getElementById('rocket-start-btn').click();
        }
    }, 1000);
}

// === ОБЩИЕ ФУНКЦИИ ===
document.getElementById('deposit-btn').addEventListener('click', () => {
    const menu = document.getElementById('deposit-menu');
    menu.style.display = menu.style.display === 'none' ? 'flex' : 'none';
});

document.querySelectorAll('.deposit-option').forEach(btn => {
    btn.addEventListener('click', () => {
        const amount = btn.dataset.amount;
        const links = {
            100: 'https://yookassa.ru/my/i/amMy2QzHTXRI/l',
            200: 'https://yookassa.ru/my/i/amMzHkXK55Uk/l',
            500: 'https://yookassa.ru/my/i/amMzSdZUSmIm/l',
            1000: 'https://yookassa.ru/my/i/amMzbZDBr9y2/l'
        };
        if (links[amount]) {
            window.open(links[amount], '_blank');
        }
    });
});

document.getElementById('close-deposit').addEventListener('click', () => {
    document.getElementById('deposit-menu').style.display = 'none';
});

async function fetchFeed() {
    try {
        const resp = await fetch('/api/recent_wins');
        const wins = await resp.json();
        const list = document.getElementById('feed-list');
        list.innerHTML = '';
        wins.forEach(w => {
            const li = document.createElement('li');
            li.textContent = '@' + w.username + ' выиграл ' + w.prize_name + ' (+' + w.prize_value + ' токенов)';
            list.appendChild(li);
        });
    } catch (e) {
        console.error(e);
    }
}
fetchFeed();
setInterval(fetchFeed, 5000);

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
        if (resp.ok) {
            alert('✅ Заявка на вывод отправлена!');
        } else {
            alert('❌ ' + data.detail);
        }
    } catch (e) {
        alert('Ошибка соединения');
        console.error(e);
    }
});

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.dataset.tab;
        if (tab === 'roulette') {
            document.getElementById('roulette-page').style.display = 'block';
            document.getElementById('slot-page').style.display = 'none';
            document.getElementById('rocket-page').style.display = 'none';
        } else if (tab === 'slot') {
            document.getElementById('roulette-page').style.display = 'none';
            document.getElementById('slot-page').style.display = 'block';
            document.getElementById('rocket-page').style.display = 'none';
        } else if (tab === 'rocket') {
            document.getElementById('roulette-page').style.display = 'none';
            document.getElementById('slot-page').style.display = 'none';
            document.getElementById('rocket-page').style.display = 'block';
            fetchUserData();
        }
    });
});
"""
}

for filename, content in STATIC_FILES.items():
    filepath = os.path.join(STATIC_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Обновлён {filepath}")

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

# API модели
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

class SendCodeRequest(BaseModel):
    user_id: int

class VerifyCodeRequest(BaseModel):
    code: str

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
    bets = get_user_bets(user_id, 50)
    return bets

@app.post("/api/send_code")
async def send_code(data: SendCodeRequest):
    user_id = data.user_id
    # Проверяем, существует ли пользователь
    user = get_user(user_id)
    if not user:
        # Создаём пользователя с временным именем
        create_user(user_id, f"user_{user_id}")
    # Генерируем 4-символьный код
    code = generate_verification_code()
    # Сохраняем с временем жизни 5 минут
    verification_codes[user_id] = {
        "code": code,
        "expires_at": time.time() + 300
    }
    # Отправляем код в Telegram
    try:
        await bot.send_message(chat_id=user_id, text=f"Ваш код подтверждения: {code}")
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Не удалось отправить код в Telegram")

@app.post("/api/verify_code")
async def verify_code(data: VerifyCodeRequest):
    code = data.code.strip().lower()
    # Ищем код в хранилище
    for uid, info in verification_codes.items():
        if info["code"] == code and time.time() < info["expires_at"]:
            user = get_user(uid)
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            # Удаляем использованный код
            del verification_codes[uid]
            return {
                "user_id": uid,
                "username": user["username"],
                "balance": user["balance"]
            }
    raise HTTPException(status_code=400, detail="Неверный или просроченный код")

# Остальные эндпоинты без изменений
@app.post("/api/spin")
async def api_spin(data: SpinRequest):
    user_id = data.user_id
    mode = data.mode
    cost = SPIN_COSTS.get(mode, 25)
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] < cost:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    update_balance(user_id, -cost, f"Спин в режиме {mode}")
    win, prize_name, prize_value = get_spin_result(mode)
    if win:
        update_balance(user_id, prize_value, f"Выигрыш: {prize_name}")
        add_win(user_id, prize_name, prize_value, mode)
        message = f"🎉 Вы выиграли {prize_name} (+{prize_value} токенов)!"
    else:
        message = "😞 К сожалению, вы проиграли. Попробуйте ещё раз!"
    new_balance = get_user(user_id)["balance"]
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
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] < bet:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    
    update_balance(user_id, -bet, f"Ставка в игровом автомате {bet} токенов")
    win, symbols, win_amount = get_slot_result(bet)
    if win:
        update_balance(user_id, win_amount, f"Выигрыш в игровом автомате {win_amount} токенов")
        add_win(user_id, f"🎰 {symbols[0]}{symbols[1]}{symbols[2]}", win_amount, "slot")
    new_balance = get_user(user_id)["balance"]
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
    if bet < 500 or bet > 5000:
        raise HTTPException(status_code=400, detail="Ставка должна быть от 500 до 5000 токенов")
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] < bet:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    
    update_balance(user_id, -bet, f"Ставка в ракетке {bet} токенов")
    
    if random.random() < 0.05:
        crash_display = 0.7 + random.random() * 98.3
    else:
        crash_display = random.random() * 0.7
    
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
    display_multiplier = elapsed * 0.3
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
    display_multiplier = elapsed * 0.3
    if display_multiplier >= round_data["crash_display"]:
        round_data["status"] = "crashed"
        raise HTTPException(status_code=400, detail="Ракета уже упала")
    
    real_multiplier = 1.0 + display_multiplier
    win_amount = int(round_data["bet"] * real_multiplier)
    update_balance(user_id, win_amount, f"Выигрыш в ракетке {win_amount} токенов")
    add_win(user_id, f"🚀 x{real_multiplier:.2f}", win_amount, "rocket")
    round_data["status"] = "cashed_out"
    round_data["current_display"] = display_multiplier
    new_balance = get_user(user_id)["balance"]
    return {
        "win_amount": win_amount,
        "new_balance": new_balance,
        "multiplier": real_multiplier
    }

@app.post("/api/withdraw")
async def api_withdraw(data: WithdrawRequest):
    user_id = data.user_id
    amount = data.amount
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] < amount:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    if amount < 500:
        raise HTTPException(status_code=400, detail="Минимальная сумма вывода – 500 токенов")
    create_withdraw_request(user_id, amount)
    return {"status": "success", "message": "Заявка на вывод отправлена администратору"}

@app.get("/api/leaderboard")
async def api_leaderboard():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT 10")
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/api/recent_wins")
async def api_recent_wins():
    return get_recent_wins(limit=10)

@app.get("/api/prizes/{mode}")
async def api_get_prizes(mode: str):
    if mode not in SPIN_COSTS:
        raise HTTPException(status_code=400, detail="Invalid mode")
    return get_prizes_for_mode(mode)

@app.get("/api/referral/{user_id}")
async def api_get_referral(user_id: int):
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    info = get_referral_info(user_id)
    link = get_referral_link(user_id)
    return {"code": info["code"], "count": info["count"], "link": link}

@app.post("/api/activate_promo")
async def activate_promo(data: PromoRequest):
    user_id = data.user_id
    code = data.code.lower().strip()
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if code not in PROMOCODES:
        raise HTTPException(status_code=400, detail="Неверный промокод")
    
    if is_promo_used(user_id, code):
        raise HTTPException(status_code=400, detail="Вы уже использовали этот промокод")
    
    reward = PROMOCODES[code]
    update_balance(user_id, reward, f"Промокод {code}")
    use_promo(user_id, code)
    
    new_balance = get_user(user_id)["balance"]
    return {
        "status": "success",
        "message": f"Промокод активирован! Вы получили +{reward} токенов",
        "new_balance": new_balance
    }

# ==================== ЗАПУСК ====================
async def set_webhook():
    port = int(os.environ.get("PORT", 10000))
    webhook_url = f"https://star-drop.onrender.com/webhook"
    await bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    logging.info(f"Webhook установлен на {webhook_url}")

async def run_uvicorn():
    port = int(os.environ.get("PORT", 10000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def shutdown(sig, loop):
    logging.info(f"Received signal {sig}, shutting down...")
    await bot.delete_webhook()
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

async def main():
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(sig, loop)))
    await set_webhook()
    await run_uvicorn()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Остановка сервисов...")
        sys.exit(0)
