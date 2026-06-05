"""
Click to'lov moduli (PostgreSQL versiyasi)
==========================================
- To'lov linki generatsiya
- Click prepare/complete callback
- Balans — database.py orqali
"""

import os
import hashlib
import logging
from datetime import datetime

from aiohttp import web
import database as db

logger = logging.getLogger(__name__)

# ── Click sozlamalari ────────────────────────────────────────────
CLICK_SERVICE_ID = os.getenv("CLICK_SERVICE_ID", "")
CLICK_MERCHANT_ID = os.getenv("CLICK_MERCHANT_ID", "")
CLICK_SECRET_KEY = os.getenv("CLICK_SECRET_KEY", "")
CLICK_MERCHANT_USER_ID = os.getenv("CLICK_MERCHANT_USER_ID", "")


# ── Sync wrapperlar (bot.py da sync chaqiruvlar uchun) ───────────
# Bot.py da get_balance va deduct_balance sync chaqiriladi,
# lekin asyncpg async — shuning uchun bot.py ni ham async qilamiz.
# Hozircha compatibility uchun qoldiramiz.

def get_balance(user_id: int) -> int:
    """DEPRECATED — db.get_balance(user_id) async ishlatiladi"""
    raise RuntimeError("get_balance sync emas — await db.get_balance() ishlatilsin")


def deduct_balance(user_id: int, amount: int) -> bool:
    """DEPRECATED — db.deduct_balance(user_id, amount) async ishlatiladi"""
    raise RuntimeError("deduct_balance sync emas — await db.deduct_balance() ishlatilsin")


# ── To'lov linki generatsiya ─────────────────────────────────────

def generate_payment_link(user_id: int, amount: int) -> str:
    url = (
        f"https://my.click.uz/services/pay"
        f"?service_id={CLICK_SERVICE_ID}"
        f"&merchant_id={CLICK_MERCHANT_ID}"
        f"&amount={amount}"
        f"&transaction_param={user_id}"
        f"&return_url=https://t.me/testuzum_bot"
    )
    return url


# ── Click sign tekshiruvi ────────────────────────────────────────

def _check_sign(data: dict) -> str:
    action = data.get('action', '0')
    if str(action) == '0':
        sign_string = (
            f"{data.get('click_trans_id', '')}"
            f"{data.get('service_id', '')}"
            f"{CLICK_SECRET_KEY}"
            f"{data.get('merchant_trans_id', '')}"
            f"{data.get('amount', '')}"
            f"{data.get('action', '')}"
            f"{data.get('sign_time', '')}"
        )
    else:
        sign_string = (
            f"{data.get('click_trans_id', '')}"
            f"{data.get('service_id', '')}"
            f"{CLICK_SECRET_KEY}"
            f"{data.get('merchant_trans_id', '')}"
            f"{data.get('merchant_prepare_id', '')}"
            f"{data.get('amount', '')}"
            f"{data.get('action', '')}"
            f"{data.get('sign_time', '')}"
        )
    return hashlib.md5(sign_string.encode()).hexdigest()


# ── Bot instance ─────────────────────────────────────────────────

_bot_instance = None
_bot_notify_callback = None


def set_bot(bot_instance, notify_callback=None):
    global _bot_instance, _bot_notify_callback
    _bot_instance = bot_instance
    _bot_notify_callback = notify_callback


# ── Click callback handlerlari ───────────────────────────────────

async def handle_prepare(request: web.Request) -> web.Response:
    try:
        data = dict(await request.post())
        logger.info(f"Click prepare: {data}")

        click_trans_id = data.get("click_trans_id", "")
        merchant_trans_id = data.get("merchant_trans_id", "")
        amount = data.get("amount", "0")
        sign_string = data.get("sign_string", "")
        error = data.get("error", "0")

        if sign_string != _check_sign(data):
            return web.json_response({
                "click_trans_id": click_trans_id,
                "merchant_trans_id": merchant_trans_id,
                "merchant_prepare_id": "",
                "error": -1,
                "error_note": "Sign check failed",
            })

        if str(error) != "0":
            return web.json_response({
                "click_trans_id": click_trans_id,
                "merchant_trans_id": merchant_trans_id,
                "merchant_prepare_id": "",
                "error": -9,
                "error_note": "Transaction cancelled",
            })

        await db.save_transaction({
            "click_trans_id": click_trans_id,
            "merchant_trans_id": merchant_trans_id,
            "amount": amount,
        })

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
    try:
        data = dict(await request.post())
        logger.info(f"Click complete: {data}")

        click_trans_id = data.get("click_trans_id", "")
        merchant_trans_id = data.get("merchant_trans_id", "")
        amount = data.get("amount", "0")
        sign_string = data.get("sign_string", "")
        error = data.get("error", "0")

        if sign_string != _check_sign(data):
            return web.json_response({
                "click_trans_id": click_trans_id,
                "merchant_trans_id": merchant_trans_id,
                "merchant_confirm_id": "",
                "error": -1,
                "error_note": "Sign check failed",
            })

        if str(error) != "0":
            return web.json_response({
                "click_trans_id": click_trans_id,
                "merchant_trans_id": merchant_trans_id,
                "merchant_confirm_id": "",
                "error": -9,
                "error_note": "Transaction cancelled",
            })

        user_id = int(merchant_trans_id)
        pay_amount = int(float(amount))
        new_balance = await db.add_balance(user_id, pay_amount, click_trans_id)

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

# ── Admin panel ──────────────────────────────────────────────────

import json
import secrets
import database as db
from pathlib import Path

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_TOKEN = secrets.token_hex(32)  # Runtime da yangilanadi
_admin_tokens: set = set()


def _auth(request) -> bool:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:] in _admin_tokens
    return False


async def admin_login(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        if data.get("password") == ADMIN_PASSWORD:
            tok = secrets.token_hex(32)
            _admin_tokens.add(tok)
            return web.json_response({"token": tok})
        return web.json_response({"error": "Wrong password"}, status=401)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def admin_stats(request: web.Request) -> web.Response:
    if not _auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        stats = await db.get_stats()
        # datetime serialization
        for r in stats.get("daily_revenue", []):
            if hasattr(r.get("day"), "isoformat"):
                r["day"] = r["day"].isoformat()
        for r in stats.get("recent_txns", []):
            if hasattr(r.get("created_at"), "isoformat"):
                r["created_at"] = r["created_at"].isoformat()
        return web.json_response(stats)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def admin_get_tariffs(request: web.Request) -> web.Response:
    if not _auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        tariffs = await db.get_all_tariffs()
        for t in tariffs:
            if hasattr(t.get("updated_at"), "isoformat"):
                t["updated_at"] = t["updated_at"].isoformat()
        return web.json_response(tariffs)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def admin_update_tariff(request: web.Request) -> web.Response:
    if not _auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        tariff_id = int(request.match_info["id"])
        data = await request.json()
        await db.update_tariff(
            tariff_id,
            data["name_uz"], data["name_ru"],
            int(data["price"]), bool(data.get("is_active", True))
        )
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def admin_get_users(request: web.Request) -> web.Response:
    if not _auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        users = await db.get_all_users(limit=100)
        for u in users:
            if hasattr(u.get("created_at"), "isoformat"):
                u["created_at"] = u["created_at"].isoformat()
            if hasattr(u.get("updated_at"), "isoformat"):
                u["updated_at"] = u["updated_at"].isoformat()
        return web.json_response(users)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def admin_set_user_balance(request: web.Request) -> web.Response:
    if not _auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        user_id = int(request.match_info["uid"])
        data = await request.json()
        amount = int(data["amount"])
        await db.admin_set_balance(user_id, amount, "admin_panel")
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def admin_html(request: web.Request) -> web.Response:
    html_path = Path(__file__).parent / "admin.html"
    if html_path.exists():
        return web.Response(text=html_path.read_text(encoding="utf-8"), content_type="text/html")
    return web.Response(text="admin.html not found", status=404)


def create_web_app() -> web.Application:
    app = web.Application()
    # Click callbacks
    app.router.add_post("/click/prepare", handle_prepare)
    app.router.add_post("/click/complete", handle_complete)
    # Admin panel
    app.router.add_get("/admin", admin_html)
    app.router.add_post("/admin/login", admin_login)
    app.router.add_get("/admin/stats", admin_stats)
    app.router.add_get("/admin/tariffs", admin_get_tariffs)
    app.router.add_put("/admin/tariffs/{id}", admin_update_tariff)
    app.router.add_get("/admin/users", admin_get_users)
    app.router.add_put("/admin/users/{uid}/balance", admin_set_user_balance)
    # Health
    async def health(request):
        return web.json_response({"status": "ok"})
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    return app