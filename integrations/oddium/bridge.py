from __future__ import annotations

import hmac
import sqlite3
from shared_economy import connect_shared
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from aiohttp import web


@dataclass(frozen=True)
class GoldResult:
    ok: bool
    balance: int
    duplicate: bool = False
    error: str | None = None


class AltheryaGoldStore:
    """Authoritative Gold wallet for external Altherya games.

    Only ``players.wallet_gold`` is shared. ``bank_gold`` remains private to
    Altherya. Every external mutation is idempotent and atomic.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = connect_shared(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS external_gold_transactions (
                    source TEXT NOT NULL,
                    reference TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(source, reason, reference)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS external_bridge_events (
                    event_key TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def claim_event(self, event_key: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("INSERT OR IGNORE INTO external_bridge_events(event_key) VALUES(?)", (str(event_key),))
            conn.commit()
            return cur.rowcount > 0

    def balance(self, user_id: int) -> int:
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO players(user_id) VALUES(?)", (int(user_id),))
            row = conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            conn.commit()
            return int(row["wallet_gold"])

    def mutate(self, *, user_id: int, amount: int, reason: str, reference: str, source: str = "ODDIUM") -> GoldResult:
        amount = int(amount)
        if amount == 0 or not reference:
            return GoldResult(False, self.balance(user_id), error="invalid_transaction")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT OR IGNORE INTO players(user_id) VALUES(?)", (int(user_id),))
            duplicate = conn.execute(
                "SELECT 1 FROM external_gold_transactions WHERE source=? AND reason=? AND reference=?",
                (source, str(reason), reference),
            ).fetchone()
            row = conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            balance = int(row["wallet_gold"])
            if duplicate:
                conn.rollback()
                return GoldResult(True, balance, duplicate=True)
            if amount < 0 and balance < abs(amount):
                conn.rollback()
                return GoldResult(False, balance, error="insufficient_funds")
            new_balance = balance + amount
            conn.execute("UPDATE players SET wallet_gold=? WHERE user_id=?", (new_balance, int(user_id)))
            conn.execute(
                "INSERT INTO external_gold_transactions(source,reference,user_id,amount,reason) VALUES(?,?,?,?,?)",
                (source, reference, int(user_id), amount, str(reason)),
            )
            conn.commit()
            return GoldResult(True, new_balance)


class OddiumBridgeServer:
    def __init__(
        self,
        *,
        db_path: str | Path,
        token: str,
        host: str,
        port: int,
        event_handler: Callable[[dict], Awaitable[None]],
    ):
        self.store = AltheryaGoldStore(db_path)
        self.token = token
        self.host = host
        self.port = int(port)
        self.event_handler = event_handler
        self.runner: web.AppRunner | None = None

    def _authorized(self, request: web.Request) -> bool:
        supplied = request.headers.get("Authorization", "")
        expected = f"Bearer {self.token}"
        return bool(self.token) and hmac.compare_digest(supplied, expected)

    async def _json(self, request: web.Request) -> dict:
        try:
            return await request.json()
        except Exception:
            raise web.HTTPBadRequest(text="invalid_json")

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "service": "altherya-oddium-bridge"})

    async def balance(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            raise web.HTTPUnauthorized()
        uid = int(request.match_info["user_id"])
        return web.json_response({"ok": True, "user_id": uid, "balance": self.store.balance(uid)})

    async def transaction(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            raise web.HTTPUnauthorized()
        body = await self._json(request)
        result = self.store.mutate(
            user_id=int(body["user_id"]), amount=int(body["amount"]),
            reason=str(body.get("reason") or "ODDIUM"), reference=str(body["reference"]),
        )
        status = 200 if result.ok else (409 if result.error == "insufficient_funds" else 400)
        return web.json_response({"ok": result.ok, "balance": result.balance, "duplicate": result.duplicate, "error": result.error}, status=status)

    async def event(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            raise web.HTTPUnauthorized()
        body = await self._json(request)
        kind = str(body.get("type") or "event")
        ref = str(body.get("reference") or (f"COMBO-{body.get('combo_id')}" if body.get("combo_id") else f"BET-{body.get('bet_id')}" if body.get("bet_id") else ""))
        event_key = f"{kind}:{ref}" if ref else ""
        if event_key and not self.store.claim_event(event_key):
            return web.json_response({"ok": True, "duplicate": True})
        await self.event_handler(body)
        return web.json_response({"ok": True, "duplicate": False})

    async def start(self) -> None:
        if not self.token:
            print("[ODDIUM BRIDGE] Désactivé : ALTHERYA_BRIDGE_TOKEN absent")
            return
        app = web.Application(client_max_size=64 * 1024)
        app.add_routes([
            web.get("/health", self.health),
            web.get("/v1/gold/{user_id}", self.balance),
            web.post("/v1/gold/transaction", self.transaction),
            web.post("/v1/events", self.event),
        ])
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner, self.host, self.port).start()
        print(f"[ODDIUM BRIDGE] actif sur {self.host}:{self.port}")

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
