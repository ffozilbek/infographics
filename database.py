"""
PostgreSQL Database moduli
===========================
- Foydalanuvchi sozlamalari (til, tarif)
- Balanslar
- Tranzaktsiyalar
"""

import os
import logging
from datetime import datetime

import asyncpg

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    return _pool


async def init_db():
    """Jadvallarni yaratish (agar yo'q bo'lsa)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     BIGINT PRIMARY KEY,
                ui_lang     VARCHAR(5)  DEFAULT 'uz',
                text_lang   VARCHAR(5)  DEFAULT 'ru',
                tariff      INTEGER     DEFAULT 0,
                balance     BIGINT      DEFAULT 0,
                created_at  TIMESTAMP   DEFAULT NOW(),
                updated_at  TIMESTAMP   DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id                  SERIAL PRIMARY KEY,
                user_id             BIGINT      NOT NULL,
                click_trans_id      VARCHAR(64),
                amount              INTEGER     NOT NULL,
                type                VARCHAR(20) NOT NULL,  -- 'topup' or 'deduct'
                status              VARCHAR(20) DEFAULT 'completed',
                created_at          TIMESTAMP   DEFAULT NOW()
            )
        """)
    logger.info("✅ DB jadvallar tayyor")


# ── Foydalanuvchi sozlamalari ────────────────────────────────────

async def ensure_user(user_id: int):
    """Foydalanuvchi yo'q bo'lsa yaratadi"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id) VALUES ($1)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id)


async def get_user_settings(user_id: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT ui_lang, text_lang, tariff, balance FROM users WHERE user_id=$1",
            user_id
        )
    if row:
        return dict(row)
    return {"ui_lang": "uz", "text_lang": "ru", "tariff": 0, "balance": 0}


async def set_user_setting(user_id: int, field: str, value):
    """Bitta maydonni yangilash"""
    allowed = {"ui_lang", "text_lang", "tariff"}
    if field not in allowed:
        raise ValueError(f"Ruxsat etilmagan maydon: {field}")
    await ensure_user(user_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE users SET {field}=$1, updated_at=NOW() WHERE user_id=$2",
            value, user_id
        )


# ── Balans ────────────────────────────────────────────────────────

async def get_balance(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT balance FROM users WHERE user_id=$1", user_id
        )
    return row["balance"] if row else 0


async def add_balance(user_id: int, amount: int, click_trans_id: str = "") -> int:
    await ensure_user(user_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "UPDATE users SET balance = balance + $1, updated_at=NOW() "
                "WHERE user_id=$2 RETURNING balance",
                amount, user_id
            )
            await conn.execute("""
                INSERT INTO transactions (user_id, click_trans_id, amount, type, status)
                VALUES ($1, $2, $3, 'topup', 'completed')
            """, user_id, click_trans_id, amount)
    new_balance = row["balance"]
    logger.info(f"Balans qo'shildi: user={user_id}, +{amount}, jami={new_balance}")
    return new_balance


async def deduct_balance(user_id: int, amount: int) -> bool:
    """Balansdan yechish. Yetarli bo'lsa True qaytaradi."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT balance FROM users WHERE user_id=$1 FOR UPDATE", user_id
            )
            if not row or row["balance"] < amount:
                return False
            await conn.execute(
                "UPDATE users SET balance = balance - $1, updated_at=NOW() WHERE user_id=$2",
                amount, user_id
            )
            await conn.execute("""
                INSERT INTO transactions (user_id, amount, type, status)
                VALUES ($1, $2, 'deduct', 'completed')
            """, user_id, amount)
    logger.info(f"Balans yechildi: user={user_id}, -{amount}")
    return True


async def save_transaction(data: dict):
    """Tranzaktsiyani saqlash (Click prepare uchun)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO transactions (user_id, click_trans_id, amount, type, status)
            VALUES ($1, $2, $3, 'topup', 'prepared')
            ON CONFLICT DO NOTHING
        """,
            int(data.get("merchant_trans_id", 0)),
            data.get("click_trans_id", ""),
            int(float(data.get("amount", 0))),
        )