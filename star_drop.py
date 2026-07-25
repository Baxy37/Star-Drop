import os
import sys
import asyncio
import logging
import sqlite3
import random
import signal
import time
import hashlib
from datetime import datetime
from typing import Optional, List, Dict

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8988678866:AAHIWxUB8zKBCoF21g7OVYEEWnwEF_MpLmI"
ADMIN_ID = 8551946505
WEBAPP_URL = "https://star-drop.onrender.com"
RUB_TO_TOKEN = 1
SPIN_COSTS = {"light": 25, "normal": 50, "hard": 100}
REFERRAL_BONUS = 50
DB_NAME = "star_drop.db"
START_BALANCE = 50  # 👈 стартовый баланс

PAYMENT_LINKS = {
    100: "https://yookassa.ru/my/i/amMy2QzHTXRI/l",
    200: "https://yookassa.ru/my/i/amMzHkXK55Uk/l",
    500: "https://yookassa.ru/my/i/amMzSdZUSmIm/l",
    1000: "https://yookassa.ru/my/i/amMzbZDBr9y2/l"
}

# ==================== СПИСОК ПОДАРКОВ ДЛЯ БИТВЫ ====================
GIFTS = [
    {"id": 1, "name": "Роза", "emoji": "🌹", "cost": 10},
    {"id": 2, "name": "Торт", "emoji": "🎂", "cost": 20},
    {"id": 3, "name": "Сердце", "emoji": "❤️", "cost": 15},
    {"id": 4, "name": "Звезда", "emoji": "⭐", "cost": 25},
    {"id": 5, "name": "Алмаз", "emoji": "💎", "cost": 50},
    {"id": 6, "name": "Бомба", "emoji": "💣", "cost": 30},
]

# ==================== ИМПОРТЫ ====================
import uvicorn
import aiofiles
import aiohttp
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

# ==================== ИНИЦИАЛИЗАЦИЯ БАЗЫ ====================
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS wins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            prize_name TEXT,
            prize_value INTEGER,
            mode TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS used_promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            code TEXT,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, code)
        )
    ''')
    try:
        cur.execute("ALTER TABLE users ADD COLUMN phone TEXT UNIQUE")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

init_db()

# ==================== ФУНКЦИИ БАЗЫ ====================
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
    cur.execute("UPDATE users SET balance = ? WHERE user_id = ? AND balance = 0", (START_BALANCE, user_id))
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

# ==================== ИГРОВЫЕ УТИЛИТЫ ====================
PRIZES_LIGHT = [
    {"name": "❌", "value": 0},
    {"name": "🎁 10", "value": 10},
    {"name": "❌", "value": 0},
    {"name": "🎁 15", "value": 15},
    {"name": "❌", "value": 0},
    {"name": "🎁 20", "value": 20},
    {"name": "❌", "value": 0},
    {"name": "🎁 25", "value": 25},
    {"name": "❌", "value": 0},
    {"name": "🎁 30", "value": 30},
    {"name": "❌", "value": 0},
    {"name": "🎁 40", "value": 40},
]

SLOT_SYMBOLS = ['🍒', '🍋', '🍊', '🍇', '🍉', '🍓', '🍑', '🎰']
SLOT_WIN_MULTIPLIER = 2
PROMOCODES = {"rifleman": 50, "blant": 50}
rocket_rounds = {}
round_counter = 0

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
        if mode == "light":
            available_prizes = [p for p in PRIZES_LIGHT if p["value"] > 0]
            if available_prizes:
                prize = random.choice(available_prizes)
                return True, prize["name"], prize["value"]
        elif mode == "normal":
            value = random.randint(1, 100)
            return True, f"🎁 {value}", value
        elif mode == "hard":
            value = random.randint(1, 500)
            return True, f"🎁 {value}", value
    return False, "❌ Проигрыш", 0

def get_prizes_for_mode(mode: str):
    if mode == "light":
        return PRIZES_LIGHT
    elif mode == "normal":
        nums = random.sample(range(1, 101), 6)
        nums.sort()
        prizes = []
        for i in range(6):
            prizes.append({"name": "❌", "value": 0})
            prizes.append({"name": f"🎁 {nums[i]}", "value": nums[i]})
        return prizes
    elif mode == "hard":
        nums = random.sample(range(1, 501), 6)
        nums.sort()
        prizes = []
        for i in range(6):
            prizes.append({"name": "❌", "value": 0})
            prizes.append({"name": f"🎁 {nums[i]}", "value": nums[i]})
        return prizes
    else:
        return PRIZES_LIGHT

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
    create_user(user_id, username, referrer_code=referrer_code)
    await message.answer(
        f"🎉 Привет, {username}!\n"
        "Добро пожаловать в **Star Drop** – розыгрыш подарков Telegram!\n\n"
        f"Вам начислено {START_BALANCE} токенов в подарок! 🎁\n"
        "Нажми кнопку ниже, чтобы открыть приложение и начать игру.",
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

# ==================== FASTAPI ====================
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

# ==================== МОДЕЛИ ====================
class RegisterRequest(BaseModel):
    telegram_id: int
    phone: str

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

class GiftBattleRequest(BaseModel):
    user_id: int
    gift_id: int

# ==================== НОВЫЙ ЭНДПОИНТ ДЛЯ БИТВЫ ====================
@app.get("/api/gifts")
async def api_get_gifts():
    return GIFTS

@app.post("/api/gift_battle")
async def api_gift_battle(data: GiftBattleRequest):
    user_id = data.user_id
    gift_id = data.gift_id
    gift = next((g for g in GIFTS if g["id"] == gift_id), None)
    if not gift:
        raise HTTPException(status_code=404, detail="Подарок не найден")
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["balance"] < gift["cost"]:
        raise HTTPException(status_code=400, detail="Недостаточно токенов")
    update_balance(user_id, -gift["cost"], f"Отправка подарка {gift['name']}")
    add_win(user_id, f"{gift['emoji']} {gift['name']}", gift["cost"], "gift_battle")
    new_balance = get_user(user_id)["balance"]
    return {
        "success": True,
        "message": f"Вы отправили {gift['emoji']} {gift['name']}!",
        "new_balance": new_balance,
        "gift": gift
    }

# ==================== ОСТАЛЬНЫЕ ЭНДПОИНТЫ (без изменений) ====================
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

@app.post("/api/register")
async def register_user(data: RegisterRequest):
    user = get_user(data.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("phone"):
        raise HTTPException(status_code=400, detail="Phone already registered")
    create_user(data.telegram_id, phone=data.phone)
    return {"status": "success", "message": "Phone registered"}

@app.get("/api/user/{user_id}")
async def api_get_user(user_id: int):
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"balance": user["balance"], "username": user["username"], "phone": user.get("phone")}

@app.get("/api/user_bets/{user_id}")
async def api_user_bets(user_id: int):
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    bets = get_user_bets(user_id, 50)
    return bets

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
    if bet < 1:
        raise HTTPException(status_code=400, detail="Ставка должна быть больше 0")
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

# ==================== СТАТИЧЕСКИЕ ФАЙЛЫ (обновлённые) ====================
static_files = {
    "index.html": """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Star Drop</title>
    <link rel="stylesheet" href="/static/style.css?v=8">
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
                <div class="wheel-wrapper">
                    <div id="wheel-pointer">▼</div>
                    <div class="wheel" id="wheel">
                        <!-- 12 секторов -->
                        <div class="sector s1" data-win-index="-1">
                            <div class="sector-content">
                                <span class="icon icon-cross">✕</span>
                            </div>
                        </div>
                        <div class="sector s2" data-win-index="0">
                            <div class="sector-content">
                                <span class="icon icon-gift">🎁</span>
                                <span class="number">10</span>
                            </div>
                        </div>
                        <div class="sector s3" data-win-index="-1">
                            <div class="sector-content">
                                <span class="icon icon-cross">✕</span>
                            </div>
                        </div>
                        <div class="sector s4" data-win-index="1">
                            <div class="sector-content">
                                <span class="icon icon-gift">🎁</span>
                                <span class="number">15</span>
                            </div>
                        </div>
                        <div class="sector s5" data-win-index="-1">
                            <div class="sector-content">
                                <span class="icon icon-cross">✕</span>
                            </div>
                        </div>
                        <div class="sector s6" data-win-index="2">
                            <div class="sector-content">
                                <span class="icon icon-gift">🎁</span>
                                <span class="number">20</span>
                            </div>
                        </div>
                        <div class="sector s7" data-win-index="-1">
                            <div class="sector-content">
                                <span class="icon icon-cross">✕</span>
                            </div>
                        </div>
                        <div class="sector s8" data-win-index="3">
                            <div class="sector-content">
                                <span class="icon icon-gift">🎁</span>
                                <span class="number">25</span>
                            </div>
                        </div>
                        <div class="sector s9" data-win-index="-1">
                            <div class="sector-content">
                                <span class="icon icon-cross">✕</span>
                            </div>
                        </div>
                        <div class="sector s10" data-win-index="4">
                            <div class="sector-content">
                                <span class="icon icon-gift">🎁</span>
                                <span class="number">30</span>
                            </div>
                        </div>
                        <div class="sector s11" data-win-index="-1">
                            <div class="sector-content">
                                <span class="icon icon-cross">✕</span>
                            </div>
                        </div>
                        <div class="sector s12" data-win-index="5">
                            <div class="sector-content">
                                <span class="icon icon-gift">🎁</span>
                                <span class="number">40</span>
                            </div>
                        </div>
                        <div class="wheel-center"></div>
                    </div>
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
                    <label for="rocket-bet-input">Ваша ставка (токены):</label>
                    <input type="number" id="rocket-bet-input" min="1" step="1" value="50" style="width:100%; padding:8px; border-radius:8px; border:1px solid var(--accent-color); background:#222; color:#fff; font-size:16px; text-align:center; max-width:200px; margin:5px auto;">
                    <div style="font-size:12px; color:#888; margin-top:4px;">Минимальная ставка – 1 токен</div>
                </div>
                <div id="rocket-buttons">
                    <button id="rocket-start-btn">🚀 Старт</button>
                    <button id="rocket-cashout-btn" disabled>💰 Стоп</button>
                </div>
                <div id="rocket-timer">Следующий взлёт через: <span id="rocket-countdown">5</span>с</div>
                <div id="rocket-result"></div>
            </div>
        </div>

        <!-- НОВАЯ ВКЛАДКА: БИТВА ПОДАРКОВ -->
        <div id="battle-page" style="display:none;">
            <div id="main-title">
                <h1>⚔️ БИТВА ПОДАРКОВ</h1>
                <p>Выбери подарок и отправь в бой!</p>
            </div>
            <div id="battle-gifts" style="display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:15px 0;">
                <!-- Заполняется JS -->
            </div>
            <div id="battle-status" style="text-align:center; font-size:18px; min-height:40px; color:var(--accent-color);"></div>
            <div id="battle-animation" style="display:none; text-align:center; margin:10px 0;">
                <canvas id="battleCanvas" width="300" height="200" style="border-radius:12px; background:#0a0a0a;"></canvas>
            </div>
            <button id="battle-send-btn" style="display:none; background:var(--accent-color); color:#0a0a0a; border:none; padding:12px 30px; border-radius:30px; font-weight:700; font-size:18px; cursor:pointer; width:100%; max-width:280px; margin:10px auto; box-shadow:0 0 20px var(--accent-glow);">Отправить в битву</button>
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
            <button class="nav-btn" data-tab="battle">⚔️ Битва</button>
        </div>
    </div>

    <script src="/static/script.js?v=8"></script>
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
#username {
    font-size: 18px;
    font-weight: 600;
    color: var(--accent-color);
}
#balance {
    font-size: 18px;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--accent-color);
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
}
.deposit-option {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 10px 20px;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
}
.deposit-option:hover { filter: brightness(1.1); }
#close-deposit {
    background: transparent;
    color: var(--accent-color);
    border: none;
    font-size: 20px;
    cursor: pointer;
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
    font-size: 13px;
}
.mode-btn.active {
    background: var(--accent-color);
    color: #0a0a0a;
    box-shadow: 0 0 15px var(--accent-glow);
}

/* ===== КОЛЕСО (обновлённое) ===== */
#wheel-container {
    position: relative;
    width: var(--wheel-size);
    height: var(--wheel-size);
    margin: 20px auto;
    z-index: 2;
}

.wheel-wrapper {
    position: relative;
    width: 100%;
    height: 100%;
    border-radius: 50%;
    padding: 14px;
    background: radial-gradient(circle at 30% 30%, #f0e68c, #b8860b);
    box-shadow: 
        0 0 40px rgba(255, 215, 0, 0.6),
        inset 0 0 30px rgba(0, 0, 0, 0.5);
    box-sizing: border-box;
}

.wheel-wrapper::before {
    content: '';
    position: absolute;
    top: -8px;
    left: -8px;
    right: -8px;
    bottom: -8px;
    border-radius: 50%;
    background: linear-gradient(145deg, #ffd700, #b8860b);
    z-index: -1;
    filter: blur(12px);
    opacity: 0.5;
}

.wheel {
    width: 100%;
    height: 100%;
    border-radius: 50%;
    position: relative;
    overflow: hidden;
    background: #1a1a1a;
    transition: transform 4s cubic-bezier(0.25, 0.1, 0.25, 1);
    will-change: transform;
    box-shadow: 
        inset 0 0 60px rgba(0, 0, 0, 0.8),
        0 0 50px rgba(255, 215, 0, 0.3);
}

/* Сектора */
.sector {
    position: absolute;
    width: 50%;
    height: 50%;
    transform-origin: 100% 100%;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    align-items: center;
    box-sizing: border-box;
    padding-top: 8%;
    backface-visibility: hidden;
    border: 1px solid rgba(255, 255, 255, 0.12);
    box-shadow: inset 0 -6px 12px rgba(0, 0, 0, 0.4);
}

.sector:nth-child(odd) {
    background: linear-gradient(145deg, #ab2b44, #8b1a2b);
}
.sector:nth-child(even) {
    background: linear-gradient(145deg, #2b805e, #1a5a3e);
}

.sector-content {
    transform: skewY(60deg);
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 100%;
    position: absolute;
    top: 12%;
    pointer-events: none;
}

.icon {
    font-size: 34px;
    margin-bottom: 2px;
    filter: drop-shadow(0 2px 6px rgba(0, 0, 0, 0.6));
    line-height: 1;
}

.icon-cross {
    color: #ff4d4d;
    font-size: 38px;
    font-weight: 900;
    text-shadow: 0 0 12px #ff4d4d88;
}
.icon-gift {
    color: #fff;
    font-size: 32px;
}

.number {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-weight: 900;
    font-size: 22px;
    color: #fff;
    text-shadow: 0 2px 10px rgba(0, 0, 0, 0.9);
    background: rgba(0, 0, 0, 0.55);
    padding: 2px 14px;
    border-radius: 30px;
    backdrop-filter: blur(4px);
    border: 1px solid rgba(255, 255, 255, 0.2);
}

/* Проигрышные сектора – скрываем цифры */
.sector .icon-cross ~ .number {
    display: none;
}

/* Указатель */
#wheel-pointer {
    position: absolute;
    top: -26px;
    left: 50%;
    transform: translateX(-50%);
    width: 0;
    height: 0;
    border-left: 20px solid transparent;
    border-right: 20px solid transparent;
    border-top: 48px solid #ffd700;
    z-index: 20;
    filter: drop-shadow(0 8px 16px rgba(255, 215, 0, 0.8));
    transition: filter 0.3s;
}

#wheel-pointer::after {
    content: '';
    position: absolute;
    top: -50px;
    left: -12px;
    width: 24px;
    height: 14px;
    background: linear-gradient(180deg, #ffd700, #b8860b);
    border-radius: 50% 50% 0 0;
    clip-path: polygon(0 0, 100% 0, 50% 100%);
}

/* Центральная кнопка */
.wheel-center {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 24%;
    height: 24%;
    background: radial-gradient(circle at 30% 30%, #f0e68c, #b8860b 80%, #8b6508);
    border-radius: 50%;
    border: 5px solid #ffd700;
    box-shadow: 
        inset 0 -8px 16px rgba(0, 0, 0, 0.6),
        inset 0 8px 16px rgba(255, 215, 0, 0.4),
        0 0 40px rgba(255, 215, 0, 0.5);
    z-index: 10;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 900;
    font-size: 20px;
    color: #1a1a1a;
    text-shadow: 0 1px 2px rgba(255, 255, 255, 0.3);
    cursor: default;
    transition: transform 0.2s, box-shadow 0.2s;
}

.wheel-center:active {
    transform: translate(-50%, -50%) scale(0.95);
    box-shadow: inset 0 -4px 8px rgba(0, 0, 0, 0.8);
}

/* Декоративные огоньки */
.wheel-wrapper::after {
    content: '';
    position: absolute;
    top: -10px;
    left: -10px;
    right: -10px;
    bottom: -10px;
    border-radius: 50%;
    background: repeating-conic-gradient(
        from 0deg,
        #ffd700 0deg 4deg,
        transparent 4deg 10deg
    );
    opacity: 0.15;
    z-index: -1;
    animation: glowPulse 2.5s ease-in-out infinite alternate;
}

@keyframes glowPulse {
    0% { opacity: 0.1; }
    100% { opacity: 0.35; }
}

/* Мобильная адаптация */
@media (max-width: 480px) {
    .icon { font-size: 28px; }
    .number { font-size: 18px; padding: 1px 10px; }
    #wheel-pointer { border-left-width: 16px; border-right-width: 16px; border-top-width: 38px; top: -22px; }
    .wheel-center { font-size: 16px; border-width: 4px; }
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
    display: flex;
    flex-direction: column;
    align-items: center;
    line-height: 1.2;
}
#spin-btn:active { transform: scale(0.95); }
#spin-btn span { font-size: 14px; font-weight: 400; }
#result-message {
    margin: 10px 0;
    font-size: 18px;
    font-weight: 600;
    min-height: 40px;
    text-align: center;
    z-index: 2;
    color: var(--accent-color);
    text-shadow: 0 0 10px var(--accent-glow);
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
.bet-control label { font-size: 14px; color: #ccc; }
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
#slot-multiplier b { color: var(--accent-color); }
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
    width: 100%;
    max-width: 280px;
}
#spin-slot-btn:active { transform: scale(0.95); }
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
    margin-bottom: 5px;
}
#rocket-bet-input {
    width: 100%;
    max-width: 200px;
    padding: 8px;
    border-radius: 8px;
    border: 1px solid var(--accent-color);
    background: #222;
    color: #fff;
    font-size: 16px;
    text-align: center;
}
#rocket-bet-input:focus {
    outline: none;
    box-shadow: 0 0 10px var(--accent-glow);
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
#rocket-timer span { color: var(--accent-color); }
#rocket-result {
    margin-top: 10px;
    font-size: 18px;
    font-weight: 600;
    text-align: center;
    color: var(--accent-color);
    min-height: 30px;
}

/* Битва подарков */
#battle-gifts {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
}
.battle-gift-card {
    background: #1a1a1a;
    border: 2px solid var(--border-color);
    border-radius: 16px;
    padding: 12px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
}
.battle-gift-card.selected {
    border-color: var(--accent-color);
    box-shadow: 0 0 20px var(--accent-glow);
}
.battle-gift-card .emoji {
    font-size: 36px;
}
.battle-gift-card .name {
    font-size: 14px;
    color: #ccc;
}
.battle-gift-card .cost {
    font-size: 12px;
    color: var(--accent-color);
}
#battle-send-btn {
    background: var(--accent-color);
    color: #0a0a0a;
    border: none;
    padding: 12px 30px;
    border-radius: 30px;
    font-weight: 700;
    font-size: 18px;
    cursor: pointer;
    box-shadow: 0 0 20px var(--accent-glow);
    width: 100%;
    max-width: 280px;
    margin: 10px auto;
}
#battle-send-btn:active { transform: scale(0.95); }
#battle-status {
    min-height: 40px;
    text-align: center;
    font-weight: 600;
}
#battle-animation canvas {
    width: 100%;
    height: auto;
    border-radius: 12px;
    background: #0a0a0a;
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
    box-shadow: 0 0 10px var(--accent-glow);
}
#promo-btn:active { transform: scale(0.95); }
#promo-message {
    width: 100%;
    font-size: 14px;
    text-align: center;
    min-height: 20px;
    color: var(--accent-color);
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
    padding: 6px 12px;
    border-radius: 20px;
    cursor: pointer;
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
#bets-modal ul li span.positive { color: #4CAF50; }
#bets-modal ul li span.negative { color: #f44336; }
""",
    "script.js": """const BASE_URL = window.location.origin;
let user_id = null;
let balance = 0;
let currentMode = 'light';
let isSpinning = false;
let currentRotation = 0;

// === Битва подарков ===
let selectedGiftId = null;
let battleAnimationId = null;

function showAuthError(message) {
    document.body.innerHTML = `
        <div style="display:flex; justify-content:center; align-items:center; height:100vh; flex-direction:column; background:#0a0a0a; color:#fff; text-align:center; padding:20px;">
            <h1 style="color:var(--accent-color);">⛔ Ошибка авторизации</h1>
            <p style="color:#ccc; margin:20px 0;">${message}</p>
            <p style="color:#888; font-size:14px;">Пожалуйста, откройте это приложение через бота Telegram.</p>
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
        const placeholder = document.getElementById('avatar-placeholder');
        const name = tgUser.first_name || 'U';
        placeholder.textContent = name.charAt(0).toUpperCase();
    } else {
        showAuthError('Не удалось получить данные пользователя из Telegram.');
    }
} else {
    const savedId = localStorage.getItem('starDrop_userId');
    if (savedId) {
        user_id = parseInt(savedId);
        document.getElementById('username').textContent = '@user_' + user_id;
        document.getElementById('avatar-placeholder').textContent = 'U';
        console.warn('Гостевой режим: используем сохранённый ID');
    } else {
        showAuthError('Это приложение работает только в Telegram. Пожалуйста, откройте его через бота.');
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
    } catch (e) {
        console.error('Avatar load error:', e);
    }
}

async function fetchUserData() {
    if (!user_id) return;
    try {
        const resp = await fetch(`/api/user/${user_id}`);
        if (!resp.ok) throw new Error('User not found');
        const data = await resp.json();
        balance = data.balance;
        document.getElementById('balance-amount').textContent = balance;
        if (data.username && data.username !== '') {
            document.getElementById('username').textContent = '@' + data.username;
        }
        if (!data.phone) {
            showRegistrationForm();
        }
    } catch (e) {
        console.error('Ошибка загрузки пользователя:', e);
    }
}

function showRegistrationForm() {
    const form = document.createElement('div');
    form.id = 'registration-form';
    form.style.cssText = 'position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.9); display:flex; flex-direction:column; align-items:center; justify-content:center; z-index:9999;';
    form.innerHTML = `
        <div style="background:#1a1a1a; padding:30px; border-radius:12px; max-width:320px; width:90%; text-align:center; border:1px solid var(--accent-color);">
            <h2 style="color:var(--accent-color); margin-bottom:10px;">Регистрация</h2>
            <p style="color:#ccc; font-size:14px;">Введите ваш номер телефона для регистрации:</p>
            <input type="tel" id="phone-input" placeholder="+7XXXXXXXXXX" style="width:100%; padding:12px; margin:15px 0; border-radius:8px; border:1px solid var(--accent-color); background:#222; color:#fff; font-size:16px; text-align:center;">
            <button id="register-submit" style="background:var(--accent-color); border:none; padding:12px 30px; border-radius:8px; font-weight:bold; cursor:pointer; width:100%;">Зарегистрироваться</button>
        </div>
    `;
    document.body.appendChild(form);

    document.getElementById('register-submit').addEventListener('click', async () => {
        const phone = document.getElementById('phone-input').value.trim();
        if (!phone) {
            alert('Введите номер телефона');
            return;
        }
        try {
            const resp = await fetch('/api/register', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ telegram_id: user_id, phone })
            });
            const data = await resp.json();
            if (resp.ok) {
                alert('Регистрация успешна!');
                document.getElementById('registration-form').remove();
                fetchUserData();
            } else {
                alert('Ошибка: ' + data.detail);
            }
        } catch (e) {
            alert('Ошибка соединения');
        }
    });
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
    if (!user_id) return;
    try {
        const resp = await fetch(`/api/user_bets/${user_id}`);
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
            balance = data.new_balance;
            document.getElementById('balance-amount').textContent = balance;
        } else msg.textContent = '❌ ' + data.detail;
    } catch (e) { msg.textContent = 'Ошибка соединения'; console.error(e); }
});

function initGames() {
    applyTheme('light');
    updateWheel(currentMode);
    updateSpinCost();
    const initialBet = parseInt(document.getElementById('bet-range').value);
    document.getElementById('bet-display').textContent = initialBet;
    drawRocket(0, 'idle');
    document.getElementById('rocket-countdown').textContent = '0';
    startAutoRocket();
    loadGifts(); // загружаем подарки для битвы
}

let autoRocketTimer = null;
function startAutoRocket() {
    if (autoRocketTimer) clearInterval(autoRocketTimer);
    autoRocketTimer = setInterval(() => {
        if (!rocketActive) {
            const fakeBet = 500 + Math.floor(Math.random() * 500) * 10;
            simulateRocketRound(fakeBet);
        }
    }, 10000 + Math.random() * 15000);
}

function simulateRocketRound(bet) {
    const win = Math.random() < 0.35;
    const crashMultiplier = win ? 1.1 + Math.random() * 2.0 : 0.5 + Math.random() * 0.5;
    let progress = 0;
    const interval = setInterval(() => {
        progress += 0.02;
        if (progress >= 1) {
            clearInterval(interval);
            if (win) {
                const winAmount = Math.floor(bet * crashMultiplier);
                addFakeWin(winAmount);
            }
            document.getElementById('rocket-multiplier').textContent = '0.00';
            document.getElementById('rocket-status').textContent = 'Ожидание';
            drawRocket(0, 'idle');
            return;
        }
        const currentMultiplier = win ? 1 + progress * crashMultiplier : progress * 0.8;
        document.getElementById('rocket-multiplier').textContent = currentMultiplier.toFixed(2);
        if (win) {
            document.getElementById('rocket-status').textContent = '🚀 Взлёт!';
            drawRocket(currentMultiplier, 'active');
        } else {
            if (progress > 0.6) {
                document.getElementById('rocket-status').textContent = '💥 Упала!';
                drawRocket(currentMultiplier, 'crashed');
            } else {
                document.getElementById('rocket-status').textContent = '🚀 Взлёт!';
                drawRocket(currentMultiplier, 'active');
            }
        }
    }, 200);
}

function addFakeWin(amount) {
    const fakeUsers = ['user_' + (100000 + Math.floor(Math.random()*900000)), 'player_' + (200000 + Math.floor(Math.random()*800000)), 'gamer_' + (300000 + Math.floor(Math.random()*700000))];
    const username = fakeUsers[Math.floor(Math.random()*fakeUsers.length)];
    const prizeName = '🎰 Слот';
    const list = document.getElementById('feed-list');
    const li = document.createElement('li');
    li.textContent = '@' + username + ' выиграл ' + prizeName + ' (+' + amount + ' токенов)';
    list.insertBefore(li, list.firstChild);
    if (list.children.length > 10) list.removeChild(list.lastChild);
}

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
        updateWheel(currentMode);
        document.getElementById('wheel').style.transform = 'rotate(0deg)';
        currentRotation = 0;
    });
});

function updateSpinCost() {
    const costs = { light: 25, normal: 50, hard: 100 };
    const cost = costs[currentMode];
    document.getElementById('spin-cost').textContent = cost;
    document.getElementById('spin-cost-label').textContent = cost + ' Токенов';
}

async function updateWheel(mode) {
    try {
        const resp = await fetch(`/api/prizes/${mode}`);
        const prizes = await resp.json();
        const sectors = document.querySelectorAll('.sector');
        sectors.forEach((sector, index) => {
            const content = sector.querySelector('.sector-content');
            const icon = content.querySelector('.icon');
            const number = content.querySelector('.number');
            const prize = prizes[index];
            if (prize.value > 0) {
                icon.textContent = '🎁';
                number.textContent = prize.value;
            } else {
                icon.textContent = '✕';
                number.textContent = '';
            }
        });
    } catch (e) {
        console.error('Ошибка загрузки призов:', e);
    }
}

document.getElementById('spin-btn').addEventListener('click', async () => {
    if (!user_id || isSpinning) return;
    isSpinning = true;
    const btn = document.getElementById('spin-btn');
    btn.disabled = true;
    btn.innerHTML = 'КРУТИТЬ <span>Загрузка...</span>';
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
            const targetRotation = currentRotation + extraSpins * 360 + randomAngle;
            currentRotation = targetRotation;
            const wheel = document.getElementById('wheel');
            wheel.style.transform = `rotate(${targetRotation}deg)`;
            setTimeout(() => {
                document.getElementById('result-message').textContent = data.message;
                document.getElementById('result-message').style.color = data.win ? '#4CAF50' : '#f44336';
                if (data.win) fetchFeed();
                isSpinning = false;
                btn.disabled = false;
                const cost = { light:25, normal:50, hard:100 }[currentMode];
                btn.innerHTML = 'КРУТИТЬ <span>' + cost + ' Токенов</span>';
            }, 4000);
        } else {
            document.getElementById('result-message').textContent = '❌ ' + data.detail;
            isSpinning = false;
            btn.disabled = false;
            const cost = { light:25, normal:50, hard:100 }[currentMode];
            btn.innerHTML = 'КРУТИТЬ <span>' + cost + ' Токенов</span>';
        }
    } catch (e) {
        document.getElementById('result-message').textContent = 'Ошибка соединения';
        console.error(e);
        isSpinning = false;
        btn.disabled = false;
        const cost = { light:25, normal:50, hard:100 }[currentMode];
        btn.innerHTML = 'КРУТИТЬ <span>' + cost + ' Токенов</span>';
    }
});

// === СЛОТ ===
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
    if (!user_id || slotSpinning) return;
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
let rocketInterval = null, rocketRoundId = null, rocketActive = false;
let rocketCountdown = 5, countdownInterval = null, rocketAnimationFrame = null;
const rocketCanvas = document.getElementById('rocketCanvas');
const rctx = rocketCanvas.getContext('2d');
let rocketX = 30, rocketY = 160;
let rocketSpeed = 2.5;
let rocketTrail = [];
let isCrashed = false;
let falling = false;
let fallY = 0;
let explosionX = 0, explosionY = 0;

function drawRocket(multiplier, status) {
    rctx.clearRect(0,0,rocketCanvas.width,rocketCanvas.height);
    if (rocketTrail.length > 1 && status !== 'crashed' && status !== 'idle') {
        rctx.beginPath();
        rctx.moveTo(rocketTrail[0].x, rocketTrail[0].y);
        for (let i=1; i<rocketTrail.length; i++) {
            rctx.lineTo(rocketTrail[i].x, rocketTrail[i].y);
        }
        rctx.strokeStyle = 'rgba(255,215,0,0.4)';
        rctx.lineWidth = 2;
        rctx.stroke();
    }
    if (status === 'crashed') {
        rctx.font = '50px sans-serif';
        rctx.textAlign = 'center';
        rctx.fillText('💥', explosionX, explosionY);
        if (falling) {
            rctx.font = '30px sans-serif';
            rctx.fillText('🚀', rocketX, fallY);
        }
        return;
    }
    if (status === 'idle') {
        rctx.font = '30px sans-serif';
        rctx.textAlign = 'center';
        rctx.fillText('🚀', rocketX, rocketY);
        return;
    }
    rctx.font = '30px sans-serif';
    rctx.textAlign = 'center';
    rctx.fillText('🚀', rocketX, rocketY);
    rctx.fillStyle = '#ffd700';
    rctx.font = '14px sans-serif';
    rctx.fillText(multiplier.toFixed(2)+'x', rocketX, rocketY-30);
}

document.getElementById('rocket-start-btn').addEventListener('click', async () => {
    if (!user_id || rocketActive) return;
    const betInput = document.getElementById('rocket-bet-input');
    const bet = parseInt(betInput.value);
    if (isNaN(bet) || bet < 1) {
        alert('Введите корректную ставку (минимум 1 токен)');
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
            isCrashed = false;
            falling = false;
            document.getElementById('rocket-start-btn').disabled = true;
            document.getElementById('rocket-cashout-btn').disabled = false;
            document.getElementById('rocket-result').textContent = '';
            document.getElementById('rocket-status').textContent = '🚀 Взлёт!';
            rocketX = 30;
            rocketY = 160;
            rocketTrail = [{x:rocketX, y:rocketY}];
            if (rocketInterval) clearInterval(rocketInterval);
            rocketInterval = setInterval(updateRocketStatus, 150);
            if (rocketAnimationFrame) cancelAnimationFrame(rocketAnimationFrame);
            animateRocket();
        } else alert('❌ ' + data.detail);
    } catch (e) { alert('Ошибка соединения'); console.error(e); }
});

function animateRocket() {
    if (!rocketActive && !falling) return;
    if (isCrashed && !falling) {
        falling = true;
        fallY = rocketY;
        explosionX = rocketX;
        explosionY = rocketY - 20;
    }
    if (falling) {
        fallY += 3;
        if (fallY > rocketCanvas.height + 50) {
            falling = false;
            isCrashed = false;
            drawRocket(0, 'idle');
            return;
        }
        drawRocket(0, 'crashed');
        rocketAnimationFrame = requestAnimationFrame(animateRocket);
        return;
    }
    if (!rocketActive) return;
    rocketX += rocketSpeed * 0.8;
    rocketY -= rocketSpeed * 0.6;
    if (rocketX > rocketCanvas.width - 20) rocketX = rocketCanvas.width - 20;
    if (rocketY < 20) rocketY = 20;
    rocketTrail.push({x:rocketX, y:rocketY});
    if (rocketTrail.length > 100) rocketTrail.shift();
    drawRocket(parseFloat(document.getElementById('rocket-multiplier').textContent) || 0, 'active');
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
                isCrashed = true;
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
                if (rocketInterval) clearInterval(rocketInterval);
                if (rocketAnimationFrame) cancelAnimationFrame(rocketAnimationFrame);
                fetchUserData();
                startCountdown();
            } else {
                drawRocket(display, 'active');
            }
        } else console.error('Status error:', data);
    } catch (e) { console.error(e); }
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
            if (rocketInterval) clearInterval(rocketInterval);
            if (rocketAnimationFrame) cancelAnimationFrame(rocketAnimationFrame);
            updateBalanceUI(data.new_balance);
            fetchFeed();
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
            document.getElementById('rocket-start-btn').click();
        }
    }, 1000);
}

// === БИТВА ПОДАРКОВ ===
async function loadGifts() {
    try {
        const resp = await fetch('/api/gifts');
        const gifts = await resp.json();
        const container = document.getElementById('battle-gifts');
        container.innerHTML = '';
        gifts.forEach(g => {
            const card = document.createElement('div');
            card.className = 'battle-gift-card';
            card.dataset.id = g.id;
            card.innerHTML = `
                <div class="emoji">${g.emoji}</div>
                <div class="name">${g.name}</div>
                <div class="cost">⭐ ${g.cost}</div>
            `;
            card.addEventListener('click', () => {
                document.querySelectorAll('.battle-gift-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                selectedGiftId = g.id;
                document.getElementById('battle-send-btn').style.display = 'block';
                document.getElementById('battle-status').textContent = `Выбран: ${g.emoji} ${g.name} (${g.cost} токенов)`;
            });
            container.appendChild(card);
        });
    } catch (e) {
        console.error('Ошибка загрузки подарков:', e);
    }
}

document.getElementById('battle-send-btn').addEventListener('click', async () => {
    if (!user_id || !selectedGiftId) return;
    const btn = document.getElementById('battle-send-btn');
    btn.disabled = true;
    btn.textContent = 'Отправка...';
    document.getElementById('battle-status').textContent = '⏳ Битва началась...';
    try {
        const resp = await fetch('/api/gift_battle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id, gift_id: selectedGiftId })
        });
        const data = await resp.json();
        if (resp.ok) {
            updateBalanceUI(data.new_balance);
            document.getElementById('battle-status').textContent = '🎉 ' + data.message;
            startBattleAnimation(data.gift);
            fetchFeed();
            document.querySelectorAll('.battle-gift-card').forEach(c => c.classList.remove('selected'));
            selectedGiftId = null;
            btn.style.display = 'none';
        } else {
            document.getElementById('battle-status').textContent = '❌ ' + data.detail;
        }
    } catch (e) {
        document.getElementById('battle-status').textContent = 'Ошибка соединения';
        console.error(e);
    }
    btn.disabled = false;
    btn.textContent = 'Отправить в битву';
});

function startBattleAnimation(gift) {
    const canvas = document.getElementById('battleCanvas');
    const ctx = canvas.getContext('2d');
    canvas.width = 300;
    canvas.height = 200;
    document.getElementById('battle-animation').style.display = 'block';
    let frame = 0;

    if (battleAnimationId) cancelAnimationFrame(battleAnimationId);

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const t = frame / 60;
        const x1 = 50 + 120 * (0.5 + 0.5 * Math.sin(t * 2.5));
        const x2 = 250 - 120 * (0.5 + 0.5 * Math.sin(t * 2.5));
        const y = 100 + 30 * Math.sin(t * 4);

        ctx.font = '50px serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(gift.emoji, x1, y);
        ctx.fillText('⚔️', 150, y - 10);
        ctx.fillText('🎁', x2, y);

        for (let i = 0; i < 8; i++) {
            const angle = t * 8 + i * 1.2;
            const r = 30 + 15 * Math.sin(t * 6 + i);
            ctx.fillStyle = `hsl(${i * 45}, 100%, 60%)`;
            ctx.beginPath();
            ctx.arc(150 + r * Math.cos(angle), y + r * Math.sin(angle), 3, 0, Math.PI * 2);
            ctx.fill();
        }

        frame++;
        if (frame < 120) {
            battleAnimationId = requestAnimationFrame(animate);
        } else {
            document.getElementById('battle-animation').style.display = 'none';
            battleAnimationId = null;
        }
    }
    animate();
}

// === ОБЩИЕ ФУНКЦИИ ===
document.getElementById('deposit-btn').addEventListener('click', () => {
    const menu = document.getElementById('deposit-menu');
    menu.style.display = menu.style.display === 'none' ? 'flex' : 'none';
});

document.querySelectorAll('.deposit-option').forEach(btn => {
    btn.addEventListener('click', () => {
        const amount = parseInt(btn.dataset.amount);
        const links = {
            100: 'https://yookassa.ru/my/i/amMy2QzHTXRI/l',
            200: 'https://yookassa.ru/my/i/amMzHkXK55Uk/l',
            500: 'https://yookassa.ru/my/i/amMzSdZUSmIm/l',
            1000: 'https://yookassa.ru/my/i/amMzbZDBr9y2/l'
        };
        if (links[amount]) window.open(links[amount], '_blank');
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
    } catch (e) { console.error(e); }
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
        document.getElementById('battle-page').style.display = tab==='battle' ? 'block' : 'none';
        if (tab==='rocket' || tab==='battle') fetchUserData();
    });
});

fetchUserData().then(() => {
    initGames();
}).catch(() => {
    initGames();
});
"""
}

for filename, content in static_files.items():
    filepath = os.path.join(STATIC_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Создан {filepath}")

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
