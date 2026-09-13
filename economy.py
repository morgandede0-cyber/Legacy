from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

@dataclass(frozen=True)
class Balance:
    wallet: int
    bank: int
    free_withdrawal_available: bool


@dataclass(frozen=True)
class TransactionResult:
    ok: bool
    message: str
    wallet: int
    bank: int
    requested: int = 0
    fee: int = 0
    received: int = 0
    was_free: bool = False


class Economy:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS players (
                    user_id INTEGER PRIMARY KEY,
                    wallet_gold INTEGER NOT NULL DEFAULT 0 CHECK(wallet_gold >= 0),
                    bank_gold INTEGER NOT NULL DEFAULT 0 CHECK(bank_gold >= 0),
                    last_withdrawal_date TEXT
                )
                """
            )
            conn.commit()

    def _today(self) -> str:
        return datetime.now().date().isoformat()

    def _ensure_player(self, conn: sqlite3.Connection, user_id: int) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO players(user_id) VALUES (?)",
            (int(user_id),),
        )

    def get_balance(self, user_id: int) -> Balance:
        with self._connect() as conn:
            self._ensure_player(conn, user_id)
            row = conn.execute(
                "SELECT wallet_gold, bank_gold, last_withdrawal_date FROM players WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            conn.commit()

        return Balance(
            wallet=int(row["wallet_gold"]),
            bank=int(row["bank_gold"]),
            free_withdrawal_available=row["last_withdrawal_date"] != self._today(),
        )

    def deposit(self, user_id: int, amount: int) -> TransactionResult:
        amount = int(amount)
        if amount <= 0:
            b = self.get_balance(user_id)
            return TransactionResult(False, "Le montant doit être supérieur à 0 Gold.", b.wallet, b.bank)

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_player(conn, user_id)
            row = conn.execute(
                "SELECT wallet_gold, bank_gold FROM players WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            wallet = int(row["wallet_gold"])
            bank = int(row["bank_gold"])

            if wallet < amount:
                conn.rollback()
                return TransactionResult(
                    False,
                    "Tu n'as pas assez de Gold sur toi pour effectuer ce dépôt.",
                    wallet,
                    bank,
                    requested=amount,
                )

            wallet -= amount
            bank += amount
            conn.execute(
                "UPDATE players SET wallet_gold = ?, bank_gold = ? WHERE user_id = ?",
                (wallet, bank, int(user_id)),
            )
            conn.commit()

        return TransactionResult(
            True,
            f"{amount} Gold ont été déposés à la banque.",
            wallet,
            bank,
            requested=amount,
            received=amount,
        )

    def withdraw(self, user_id: int, amount: int) -> TransactionResult:
        amount = int(amount)
        if amount <= 0:
            b = self.get_balance(user_id)
            return TransactionResult(False, "Le montant doit être supérieur à 0 Gold.", b.wallet, b.bank)

        today = self._today()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_player(conn, user_id)
            row = conn.execute(
                "SELECT wallet_gold, bank_gold, last_withdrawal_date FROM players WHERE user_id = ?",
                (int(user_id),),
            ).fetchone()
            wallet = int(row["wallet_gold"])
            bank = int(row["bank_gold"])
            last_date = row["last_withdrawal_date"]

            if bank < amount:
                conn.rollback()
                return TransactionResult(
                    False,
                    "Tu n'as pas assez de Gold à la banque pour effectuer ce retrait.",
                    wallet,
                    bank,
                    requested=amount,
                )

            free = last_date != today
            fee = 0 if free else max(1, amount * 5 // 100)
            received = amount - fee

            bank -= amount
            wallet += received
            conn.execute(
                """
                UPDATE players
                SET wallet_gold = ?, bank_gold = ?, last_withdrawal_date = ?
                WHERE user_id = ?
                """,
                (wallet, bank, today, int(user_id)),
            )
            conn.commit()

        return TransactionResult(
            True,
            "Retrait effectué.",
            wallet,
            bank,
            requested=amount,
            fee=fee,
            received=received,
            was_free=free,
        )
