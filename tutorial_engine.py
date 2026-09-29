from __future__ import annotations

import sqlite3
from pathlib import Path
from shared_economy import connect_shared, mutate as shared_mutate

TUTORIAL_GOLD = 100
TUTORIAL_XP = 25

class TutorialStore:
    """Progression + récompense du tutoriel.

    Sécurité:
    - completed et reward sont séparés;
    - Gold idempotent via economy_transactions (référence unique);
    - XP + drapeau XP sont écrits dans la même transaction SQLite;
    - refaire le tuto ne remet JAMAIS les drapeaux de récompense à zéro.
    """
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _c(self):
        c = connect_shared(self.db_path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._c() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS tutorial_progress(
                user_id INTEGER PRIMARY KEY,
                completed INTEGER NOT NULL DEFAULT 0,
                completed_at TEXT,
                reward_claimed INTEGER NOT NULL DEFAULT 0,
                gold_claimed INTEGER NOT NULL DEFAULT 0,
                xp_claimed INTEGER NOT NULL DEFAULT 0,
                runs INTEGER NOT NULL DEFAULT 0,
                last_started_at TEXT,
                last_completed_at TEXT
            )""")
            c.commit()

    def ensure(self, user_id: int):
        with self._c() as c:
            c.execute("INSERT OR IGNORE INTO tutorial_progress(user_id) VALUES(?)", (int(user_id),))
            c.commit()

    def state(self, user_id: int) -> dict:
        self.ensure(user_id)
        with self._c() as c:
            return dict(c.execute(
                "SELECT * FROM tutorial_progress WHERE user_id=?", (int(user_id),)
            ).fetchone())

    def start(self, user_id: int):
        self.ensure(user_id)
        with self._c() as c:
            c.execute("""UPDATE tutorial_progress
                         SET runs=runs+1,last_started_at=CURRENT_TIMESTAMP
                         WHERE user_id=?""", (int(user_id),))
            c.commit()

    def completed(self, user_id: int) -> bool:
        return bool(self.state(user_id)["completed"])

    def reward_claimed(self, user_id: int) -> bool:
        return bool(self.state(user_id)["reward_claimed"])

    def _grant_xp_once(self, user_id: int) -> bool:
        uid = int(user_id)
        with self._c() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT OR IGNORE INTO tutorial_progress(user_id) VALUES(?)", (uid,))
            row = c.execute(
                "SELECT xp_claimed FROM tutorial_progress WHERE user_id=?", (uid,)
            ).fetchone()
            if int(row["xp_claimed"]):
                c.commit()
                return False

            # Même transaction que le drapeau: impossible de doubler l'XP par double clic.
            c.execute("INSERT OR IGNORE INTO castle_profiles(user_id) VALUES(?)", (uid,))
            before = int(c.execute(
                "SELECT xp FROM castle_profiles WHERE user_id=?", (uid,)
            ).fetchone()["xp"])
            after = before + TUTORIAL_XP
            c.execute("UPDATE castle_profiles SET xp=? WHERE user_id=?", (after, uid))
            c.execute(
                "UPDATE tutorial_progress SET xp_claimed=1 WHERE user_id=?", (uid,)
            )
            c.commit()
            return True

    def _grant_gold_once(self, user_id: int) -> bool:
        uid = int(user_id)
        state = self.state(uid)
        if state["gold_claimed"]:
            return False

        # La référence est fixe par joueur. shared_economy.mutate est idempotent:
        # même après un crash/retry, cette transaction Gold ne peut exister qu'une fois.
        ok, _, _duplicate = shared_mutate(
            uid,
            TUTORIAL_GOLD,
            "TUTORIAL_WELCOME_REWARD",
            f"tutorial-welcome:{uid}",
            source="ALTHERYA",
        )
        if not ok:
            raise RuntimeError("Impossible d'attribuer la récompense Gold.")

        with self._c() as c:
            c.execute(
                "UPDATE tutorial_progress SET gold_claimed=1 WHERE user_id=?", (uid,)
            )
            c.commit()
        return True

    def finish_and_reward(self, user_id: int) -> dict:
        uid = int(user_id)
        self.ensure(uid)

        xp_new = self._grant_xp_once(uid)
        gold_new = self._grant_gold_once(uid)

        with self._c() as c:
            c.execute("""UPDATE tutorial_progress
                         SET completed=1,
                             completed_at=COALESCE(completed_at,CURRENT_TIMESTAMP),
                             last_completed_at=CURRENT_TIMESTAMP,
                             reward_claimed=CASE
                               WHEN gold_claimed=1 AND xp_claimed=1 THEN 1
                               ELSE reward_claimed
                             END
                         WHERE user_id=?""", (uid,))
            c.commit()

        state = self.state(uid)
        return {
            "first_reward": bool(xp_new or gold_new),
            "reward_claimed": bool(state["reward_claimed"]),
            "gold": TUTORIAL_GOLD,
            "xp": TUTORIAL_XP,
        }
