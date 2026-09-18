from __future__ import annotations

import random
import sqlite3
from shared_economy import connect_shared
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from admin_engine import event_multiplier

MAX_BET = 500
VIP_MAX_BET = 1500
MIN_BET = 1

CASINO_LOYALTY_TIERS = [(0, "Visiteur"), (30, "Habitué"), (200, "VIP")]
CASINO_HABITUE_WINS = 30
CASINO_VIP_WINS = 200

SLOT_SYMBOLS = ["🍒", "🔔", "💎", "👑", "7️⃣"]
SLOT_WEIGHTS = [38, 28, 18, 11, 5]
SLOT_TRIPLE_MULTIPLIERS = {
    "🍒": 2,
    "🔔": 3,
    "💎": 5,
    "👑": 8,
    "7️⃣": 12,
}

@dataclass(frozen=True)
class CasinoSession:
    session_id: str
    user_id: int
    game_type: str
    wager: int
    status: str
    created_at: int


class CasinoStore:
    """Économie atomique des jeux de la salle clandestine.

    La mise est retirée au démarrage d'une partie. Le règlement crédite ensuite le
    montant TOTAL gagné (mise incluse). Les sessions restées actives après un crash
    sont remboursées au prochain démarrage du bot.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = connect_shared(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    user_id INTEGER PRIMARY KEY,
                    wallet_gold INTEGER NOT NULL DEFAULT 0 CHECK(wallet_gold >= 0),
                    bank_gold INTEGER NOT NULL DEFAULT 0 CHECK(bank_gold >= 0),
                    last_withdrawal_date TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS casino_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    game_type TEXT NOT NULL,
                    wager INTEGER NOT NULL CHECK(wager > 0),
                    status TEXT NOT NULL DEFAULT 'active',
                    payout INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    finished_at INTEGER
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_casino_user_status ON casino_sessions(user_id,status)")
            conn.execute("""CREATE TABLE IF NOT EXISTS casino_loyalty_admin (
                user_id INTEGER PRIMARY KEY, wins INTEGER NOT NULL CHECK(wins >= 0)
            )""")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS casino_stats (
                    user_id INTEGER NOT NULL,
                    game_type TEXT NOT NULL,
                    games INTEGER NOT NULL DEFAULT 0,
                    wagered INTEGER NOT NULL DEFAULT 0,
                    paid_out INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(user_id, game_type)
                )
            """)
            conn.commit()

    @staticmethod
    def _ensure_player(conn, user_id: int):
        conn.execute("INSERT OR IGNORE INTO players(user_id) VALUES (?)", (int(user_id),))

    def loyalty(self, user_id: int) -> dict:
        # La fidélité progresse uniquement sur les parties GAGNÉES.
        # Une égalité/remboursement (payout == wager) ne compte pas comme victoire.
        with self._connect() as conn:
            override = conn.execute("SELECT wins FROM casino_loyalty_admin WHERE user_id=?", (int(user_id),)).fetchone()
            row = conn.execute(
                "SELECT COUNT(*) FROM casino_sessions WHERE user_id=? AND status='finished' AND payout>wager",
                (int(user_id),),
            ).fetchone()
        wins = int(override[0]) if override is not None else (int(row[0]) if row else 0)
        label = "Visiteur"
        if wins >= CASINO_VIP_WINS: label = "VIP"
        elif wins >= CASINO_HABITUE_WINS: label = "Habitué"
        return {"wins": wins, "games": wins, "label": label, "vip": wins >= CASINO_VIP_WINS}

    def wallet(self, user_id: int) -> int:
        with self._connect() as conn:
            self._ensure_player(conn, int(user_id))
            row = conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            conn.commit()
            return int(row[0])

    def start(self, user_id: int, game_type: str, wager: int) -> dict:
        user_id = int(user_id)
        try:
            wager = int(wager)
        except (TypeError, ValueError):
            return {"ok": False, "message": "La mise doit être un nombre entier."}
        max_bet = VIP_MAX_BET if self.loyalty(user_id).get("vip") else MAX_BET
        if not MIN_BET <= wager <= max_bet:
            suffix = " (limite VIP)" if max_bet == VIP_MAX_BET else ""
            return {"ok": False, "message": f"La mise doit être comprise entre {MIN_BET} et {max_bet} Gold{suffix}."}

        session_id = uuid.uuid4().hex
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_player(conn, user_id)
            wallet = int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (user_id,)).fetchone()[0])
            if wallet < wager:
                conn.rollback()
                return {"ok": False, "message": f"Tu n'as que {wallet} Gold sur toi. Mise demandée : {wager} Gold."}
            conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?", (wager, user_id))
            conn.execute(
                "INSERT INTO casino_sessions(session_id,user_id,game_type,wager,status,created_at) VALUES (?,?,?,?,?,?)",
                (session_id, user_id, str(game_type), wager, "active", now),
            )
            conn.commit()
        return {"ok": True, "session_id": session_id, "wager": wager, "wallet_after": wallet - wager}

    def settle(self, session_id: str, payout: int, status: str = "finished") -> dict:
        payout = max(0, int(payout))
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM casino_sessions WHERE session_id=?", (str(session_id),)).fetchone()
            if not row:
                conn.rollback()
                return {"ok": False, "message": "Partie introuvable."}
            if str(row["status"]) != "active":
                conn.rollback()
                return {"ok": False, "message": "Cette partie est déjà terminée.", "already": True}
            user_id = int(row["user_id"])
            wager = int(row["wager"])
            # Gold x2 double uniquement le bénéfice, jamais le remboursement de la mise.
            if payout > wager:
                payout = wager + (payout - wager) * event_multiplier(self.db_path, "gold_x2")
            self._ensure_player(conn, user_id)
            if payout:
                conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (payout, user_id))
            conn.execute(
                "UPDATE casino_sessions SET status=?, payout=?, finished_at=? WHERE session_id=?",
                (status, payout, now, str(session_id)),
            )
            if status == "finished":
                conn.execute("""
                    INSERT INTO casino_stats(user_id,game_type,games,wagered,paid_out)
                    VALUES (?,?,?,?,?)
                    ON CONFLICT(user_id,game_type) DO UPDATE SET
                        games=casino_stats.games+1,
                        wagered=casino_stats.wagered+excluded.wagered,
                        paid_out=casino_stats.paid_out+excluded.paid_out
                """, (user_id, str(row["game_type"]), 1, wager, payout))
            wallet = int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (user_id,)).fetchone()[0])
            conn.commit()
            return {"ok": True, "payout": payout, "wager": wager, "wallet": wallet, "user_id": user_id}

    def refund(self, session_id: str) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT wager FROM casino_sessions WHERE session_id=? AND status='active'", (str(session_id),)).fetchone()
        if not row:
            return {"ok": False}
        return self.settle(session_id, int(row["wager"]), status="refunded")

    def recover_unfinished(self) -> int:
        """Rembourse toutes les parties interrompues lors d'un redémarrage."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT session_id,user_id,wager FROM casino_sessions WHERE status='active'").fetchall()
            now = int(time.time())
            for row in rows:
                self._ensure_player(conn, int(row["user_id"]))
                conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (int(row["wager"]), int(row["user_id"])))
                conn.execute("UPDATE casino_sessions SET status='refunded',payout=?,finished_at=? WHERE session_id=?",
                             (int(row["wager"]), now, str(row["session_id"])))
            conn.commit()
            return len(rows)


def draw_slot() -> list[str]:
    return random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=3)


def slot_multiplier(reels: list[str]) -> int:
    if len(reels) == 3 and reels[0] == reels[1] == reels[2]:
        return SLOT_TRIPLE_MULTIPLIERS.get(reels[0], 2)
    # Deux 7 : mise rendue. Petit suspense sans créer de gain net.
    if reels.count("7️⃣") == 2:
        return 1
    return 0


def roulette_spin() -> tuple[int, str]:
    number = random.randint(0, 36)
    if number == 0:
        return number, "green"
    red = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
    return number, "red" if number in red else "black"
