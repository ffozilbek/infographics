"""
Click to'lov moduli
====================
- To'lov linki generatsiya
- Click prepare/complete callback
- Balans saqlash (JSON fayl)
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime

from aiohttp import web

logger = logging.getLogger(__name__)

# ── Click sozlamalari ────────────────────────────────────────────
CLICK_SERVICE_ID = os.getenv("CLICK_SERVICE_ID", "")
CLICK_MERCHANT_ID = os.getenv("CLICK_MERCHANT_ID", "")
CLICK_SECRET_KEY = os.getenv("CLICK_SECRET_KEY", "")
CLICK_MERCHANT_USER_ID = os.getenv("CLICK_MERCHANT_USER_ID", "")

# ── Balans saqlash (JSON fayl) ───────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
BALANCES_FILE = DATA_DIR / "balances.json"
TRANSACTIONS_FILE = DATA_DIR / "transactions.json"


def load_balances() -> dict:
    if BALANCES_FILE.exists():
        try:
            return json.loads(BALANCES_FILE.read_text())
        except:
            return {}
    return {}


def save_balances(balances: dict):
    BALANCES_FILE.write_text(json.dumps(balances, indent=2))


def get_balance(user_id: int) -> int:
    balances = load_balances()
    return balances.get(str(user_id), 0)


def add_balance(user_id: int, amount: int):
    balances = load_balances()
    uid = str(user_id)
    balances[uid] = balances.get(uid, 0) + amount
    save_balances(balances)
    logger.info(f"Balans qo'shildi: user={user_id}, +{amount}, jami={balances[uid]}")
    return balances[uid]


def deduct_balance(user_id: int, amount: int) -> bool:
    """Balansdan yechish. Yetarli bo'lsa True, aks holda False"""
    balances = load_balances()
    uid = str(user_id)
    current = balances.get(uid, 0)
    if current < amount:
        return False
    balances[uid] = current - amount
    save_balances(balances)
    logger.info(f"Balans yechildi: user={user_id}, -{amount}, qoldi={balances[uid]}")
    return True


def save_transaction(data: dict):
    """Tranzaktsiyani saqlash"""
    txns = []
    if TRANSACTIONS_FILE.exists():
        try:
            txns = json.loads(TRANSACTIONS_FILE.read_text())
        except:
            txns = []
    txns.append(data)
    TRANSACTIONS_FILE.write_text(json.dumps(txns, indent=2, default=str))


# ── To'lov linki generatsiya ────────────────────────────────────

def generate_payment_link(user_id: int, amount: int) -> str:
    """Click to'lov linkini yaratadi"""
    # transaction_param = user_id (to'lovni kimga bog'lash uchun)
    url = (
        f"https://my.click.uz/services/pay"
        f"?service_id={CLICK_SERVICE_ID}"
        f"&merchant_id={CLICK_MERCHANT_ID}"
        f"&amount={amount}"
        f"&transaction_param={user_id}"
        f"&return_url=https://t.me/testuzum_bot"
    )
    return url


# ── Click callback handlerlari ──────────────────────────────────

# Bot instance — bot.py dan set qilinadi
_bot_instance = None
_bot_notify_callback = None


def set_bot(bot_instance, notify_callback=None):
    """Bot instance ni set qilish (bot.py dan chaqiriladi)"""
    global _bot_instance, _bot_notify_callback
    _bot_instance = bot_instance
    _bot_notify_callback = notify_callback


def _check_sign(data: dict, action: int) -> str:
    """Click sign tekshiruvi"""
    sign_string = (
        f"{data.get('click_trans_id', '')}"
        f"{data.get('service_id', '')}"
        f"{CLICK_SECRET_KEY}"
        f"{data.get('merchant_trans_id', '')}"
    )
    if action == 1:  # prepare
        sign_string += f"{data.get('amount', '')}{action}"
    else:  # complete
        sign_string += f"{data.get('merchant_prepare_id', '')}{data.get('amount', '')}{action}"

    return hashlib.md5(sign_string.encode()).hexdigest()


async def handle_prepare(request: web.Request) -> web.Response:
    """Click prepare callback — to'lov tasdiqlanishidan oldin"""
    try:
        data = await request.post()
        data = dict(data)
        logger.info(f"Click prepare: {data}")

        click_trans_id = data.get("click_trans_id", "")
        service_id = data.get("service_id", "")
        merchant_trans_id = data.get("merchant_trans_id", "")  # user_id
        amount = data.get("amount", "0")
        sign_string = data.get("sign_string", "")
        error = data.get("error", "0")

        # Sign tekshiruvi
        expected_sign = _check_sign(data, 1)

        if sign_string != expected_sign:
            logger.warning(f"Click prepare: sign mismatch")
            return web.json_response({
                "click_trans_id": click_trans_id,
                "merchant_trans_id": merchant_trans_id,
                "merchant_prepare_id": "",
                "error": -1,
                "error_note": "Sign check failed",
            })

        if str(error) != "0":
            logger.warning(f"Click prepare: error={error}")
            return web.json_response({
                "click_trans_id": click_trans_id,
                "merchant_trans_id": merchant_trans_id,
                "merchant_prepare_id": "",
                "error": -9,
                "error_note": "Transaction cancelled",
            })

        # Tranzaktsiyani saqlash
        txn = {
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "amount": float(amount),
            "status": "prepared",
            "created_at": datetime.now().isoformat(),
        }
        save_transaction(txn)

        return web.json_response({
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "merchant_prepare_id": click_trans_id,
            "error": 0,
            "error_note": "Success",
        })

    except Exception as e:
        logger.error(f"Click prepare xatolik: {e}")
        return web.json_response({"error": -1, "error_note": str(e)})


async def handle_complete(request: web.Request) -> web.Response:
    """Click complete callback — to'lov tasdiqlandi"""
    try:
        data = await request.post()
        data = dict(data)
        logger.info(f"Click complete: {data}")

        click_trans_id = data.get("click_trans_id", "")
        service_id = data.get("service_id", "")
        merchant_trans_id = data.get("merchant_trans_id", "")  # user_id
        amount = data.get("amount", "0")
        sign_string = data.get("sign_string", "")
        error = data.get("error", "0")

        # Sign tekshiruvi
        expected_sign = _check_sign(data, 2)

        if sign_string != expected_sign:
            logger.warning(f"Click complete: sign mismatch")
            return web.json_response({
                "click_trans_id": click_trans_id,
                "merchant_trans_id": merchant_trans_id,
                "merchant_confirm_id": "",
                "error": -1,
                "error_note": "Sign check failed",
            })

        if str(error) != "0":
            logger.warning(f"Click complete: error={error}")
            return web.json_response({
                "click_trans_id": click_trans_id,
                "merchant_trans_id": merchant_trans_id,
                "merchant_confirm_id": "",
                "error": -9,
                "error_note": "Transaction cancelled",
            })

        # Balansni to'ldirish
        user_id = int(merchant_trans_id)
        pay_amount = int(float(amount))
        new_balance = add_balance(user_id, pay_amount)

        # Tranzaktsiyani saqlash
        txn = {
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "amount": pay_amount,
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
        }
        save_transaction(txn)

        # Foydalanuvchiga xabar yuborish
        if _bot_instance and _bot_notify_callback:
            try:
                await _bot_notify_callback(user_id, pay_amount, new_balance)
            except Exception as e:
                logger.error(f"Notify xatolik: {e}")

        return web.json_response({
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "merchant_confirm_id": click_trans_id,
            "error": 0,
            "error_note": "Success",
        })

    except Exception as e:
        logger.error(f"Click complete xatolik: {e}")
        return web.json_response({"error": -1, "error_note": str(e)})


# ── Web server ───────────────────────────────────────────────────

def create_web_app() -> web.Application:
    """aiohttp web app yaratadi"""
    app = web.Application()
    app.router.add_post("/click/prepare", handle_prepare)
    app.router.add_post("/click/complete", handle_complete)

    # Health check (Railway uchun)
    async def health(request):
        return web.json_response({"status": "ok"})
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    return app