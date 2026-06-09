"""
PostgreSQL Database moduli
===========================
- Foydalanuvchi sozlamalari (til, tarif)
- Balanslar
- Tranzaktsiyalar
- Tarif sozlamalari (admin)
- Statistika (admin)
"""

import os
import logging
from datetime import datetime, date

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
                username    VARCHAR(64),
                full_name   VARCHAR(128),
                ui_lang     VARCHAR(5),
                text_lang   VARCHAR(5),
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
                type                VARCHAR(20) NOT NULL,
                status              VARCHAR(20) DEFAULT 'completed',
                created_at          TIMESTAMP   DEFAULT NOW()
            )
        """)
        # Tarif sozlamalari jadvali
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tariff_settings (
                tariff_id       INTEGER PRIMARY KEY,
                name_uz         VARCHAR(100) NOT NULL,
                name_ru         VARCHAR(100) NOT NULL,
                price           INTEGER      NOT NULL,
                is_active       BOOLEAN      DEFAULT TRUE,
                updated_at      TIMESTAMP    DEFAULT NOW()
            )
        """)
        # Default tariflar (agar bo'sh bo'lsa)
        await conn.execute("""
            INSERT INTO tariff_settings (tariff_id, name_uz, name_ru, price)
            VALUES
                (1, 'Infografika',                  'Инфографика',              7000),
                (2, 'Infografika + Matn',            'Инфографика + Текст',      12000),
                (3, 'Infografika + Reklama rasmlar', 'Инфографика + Рекл. фото', 17000),
                (4, 'To''liq paket',                 'Полный пакет',             25000)
            ON CONFLICT (tariff_id) DO NOTHING
        """)
        # Mavjud DB ga username ustunlarini qo'shish (agar yo'q bo'lsa)
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(64);
            ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(128);
        """)
        # text_lang va ui_lang DEFAULT ni olib tashlash
        await conn.execute("""
            ALTER TABLE users ALTER COLUMN text_lang DROP DEFAULT;
            ALTER TABLE users ALTER COLUMN ui_lang DROP DEFAULT;
        """)
    logger.info("✅ DB jadvallar tayyor")


# ── Foydalanuvchi sozlamalari ─────────────────────────────────────

async def ensure_user(user_id: int, username: str = None, full_name: str = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, full_name) VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE
            SET username = COALESCE($2, users.username),
                full_name = COALESCE($3, users.full_name)
        """, user_id, username, full_name)


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


# ── Tarif sozlamalari (admin) ─────────────────────────────────────

async def get_all_tariffs() -> list:
    """Barcha tariflarni qaytaradi"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM tariff_settings ORDER BY tariff_id"
        )
    return [dict(r) for r in rows]


async def get_tariff(tariff_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM tariff_settings WHERE tariff_id=$1", tariff_id
        )
    return dict(row) if row else None


async def update_tariff(tariff_id: int, name_uz: str, name_ru: str, price: int, is_active: bool):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE tariff_settings
            SET name_uz=$1, name_ru=$2, price=$3, is_active=$4, updated_at=NOW()
            WHERE tariff_id=$5
        """, name_uz, name_ru, price, is_active, tariff_id)
    logger.info(f"Tarif yangilandi: id={tariff_id}, price={price}")


# ── Statistika (admin) ────────────────────────────────────────────

async def get_stats() -> dict:
    """Umumiy statistika"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        today_users = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE DATE(created_at)=CURRENT_DATE"
        )
        total_revenue = await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions "
            "WHERE type='topup' AND status='completed' "
            "AND COALESCE(click_trans_id, '') NOT IN ('welcome_bonus', 'admin_panel', '')"
        )
        today_revenue = await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions "
            "WHERE type='topup' AND status='completed' AND DATE(created_at)=CURRENT_DATE "
            "AND COALESCE(click_trans_id, '') NOT IN ('welcome_bonus', 'admin_panel', '')"
        )
        total_orders = await conn.fetchval(
            "SELECT COUNT(*) FROM transactions WHERE type='deduct'"
        )
        today_orders = await conn.fetchval(
            "SELECT COUNT(*) FROM transactions WHERE type='deduct' AND DATE(created_at)=CURRENT_DATE"
        )
        # Tarif bo'yicha buyurtmalar (deduct tranzaktsiyalari)
        tariff_stats = await conn.fetch("""
            SELECT t.tariff_id, t.name_uz, COUNT(tr.id) as orders,
                   COALESCE(SUM(tr.amount), 0) as revenue
            FROM tariff_settings t
            LEFT JOIN transactions tr ON tr.amount = t.price AND tr.type='deduct'
            GROUP BY t.tariff_id, t.name_uz
            ORDER BY t.tariff_id
        """)
        # So'nggi 7 kun daromad
        daily_revenue = await conn.fetch("""
            SELECT DATE(created_at) as day,
                   COALESCE(SUM(amount), 0) as revenue,
                   COUNT(*) as orders
            FROM transactions
            WHERE type='topup' AND status='completed'
              AND created_at >= NOW() - INTERVAL '7 days'
            GROUP BY DATE(created_at)
            ORDER BY day DESC
        """)
        # So'nggi 10 ta tranzaktsiya
        recent_txns = await conn.fetch("""
            SELECT t.id, t.user_id, t.amount, t.type, t.status, t.created_at,
                   u.ui_lang
            FROM transactions t
            LEFT JOIN users u ON u.user_id = t.user_id
            ORDER BY t.created_at DESC
            LIMIT 10
        """)

    return {
        "total_users": total_users,
        "today_users": today_users,
        "total_revenue": total_revenue,
        "today_revenue": today_revenue,
        "total_orders": total_orders,
        "today_orders": today_orders,
        "tariff_stats": [dict(r) for r in tariff_stats],
        "daily_revenue": [dict(r) for r in daily_revenue],
        "recent_txns": [dict(r) for r in recent_txns],
    }


async def get_all_users(limit: int = 50, offset: int = 0) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT user_id, username, full_name, ui_lang, tariff, balance, created_at
            FROM users
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
        """, limit, offset)
    return [dict(r) for r in rows]


async def admin_set_balance(user_id: int, amount: int, admin_note: str = "admin"):
    """Admin tomonidan balans o'rnatish (to'g'ridan-to'g'ri)"""
    await ensure_user(user_id)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE users SET balance=$1, updated_at=NOW() WHERE user_id=$2",
                amount, user_id
            )
            await conn.execute("""
                INSERT INTO transactions (user_id, amount, type, status, click_trans_id)
                VALUES ($1, $2, 'topup', 'completed', $3)
            """, user_id, amount, admin_note)
    logger.info(f"Admin balans o'rnatdi: user={user_id}, balance={amount}")