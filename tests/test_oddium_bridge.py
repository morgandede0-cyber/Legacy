import sqlite3
from pathlib import Path

from integrations.oddium.bridge import AltheryaGoldStore


def test_gold_is_atomic_and_idempotent(tmp_path: Path):
    db = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE players(user_id INTEGER PRIMARY KEY, wallet_gold INTEGER NOT NULL DEFAULT 0, bank_gold INTEGER NOT NULL DEFAULT 0)")
        c.execute("INSERT INTO players(user_id,wallet_gold,bank_gold) VALUES(1,1000,9000)")
    store = AltheryaGoldStore(db)
    r = store.mutate(user_id=1, amount=-400, reason="BET_STAKE", reference="BET-1")
    assert r.ok and r.balance == 600
    r2 = store.mutate(user_id=1, amount=-400, reason="BET_STAKE", reference="BET-1")
    assert r2.ok and r2.duplicate and r2.balance == 600
    win = store.mutate(user_id=1, amount=800, reason="BET_WIN", reference="BET-1")
    assert win.ok and win.balance == 1400
    assert store.balance(1) == 1400
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT bank_gold FROM players WHERE user_id=1").fetchone()[0] == 9000


def test_insufficient_funds_never_go_negative(tmp_path: Path):
    db = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE players(user_id INTEGER PRIMARY KEY, wallet_gold INTEGER NOT NULL DEFAULT 0, bank_gold INTEGER NOT NULL DEFAULT 0)")
        c.execute("INSERT INTO players(user_id,wallet_gold,bank_gold) VALUES(2,100,0)")
    store = AltheryaGoldStore(db)
    r = store.mutate(user_id=2, amount=-101, reason="BET_STAKE", reference="BET-2")
    assert not r.ok and r.error == "insufficient_funds" and store.balance(2) == 100
