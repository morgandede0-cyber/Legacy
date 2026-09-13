from __future__ import annotations

import random
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from admin_engine import event_multiplier, cooldowns_enabled

# =========================
# ÉQUILIBRAGE — RUELLE SOMBRE
# =========================
# Tout est centralisé ici pour pouvoir retoucher l'économie facilement.
ACTION_COOLDOWN = 60 * 60          # vol et crime : 1 fois / heure, séparément
ALLEY_BAN_SECONDS = 5 * 60 * 60    # échec du braquage : 5 h
HEIST_ATTEMPTS = 7
HEIST_CODE_LENGTH = 4
HEIST_REWARD_MIN = 450
HEIST_REWARD_MAX = 900
HEIST_FAIL_FINE = 250
GUARD_ENTRY_FEE = 150
INVITATION_ITEM = "Invitation clandestine"

CRIME_REWARD_MIN = 80
CRIME_REWARD_MAX = 160
CRIME_FINE = 75
THEFT_MIN = 10
THEFT_MAX = 100
THEFT_PERCENT = 0.10
NPC_THEFT_TARGETS = {
    # nom, min, max, réussite, échec discret, pris sur le fait, amende max
    "troubadour": ("Le Troubadour", 15, 55, 0.62, 0.30, 0.08, 20),
    "tavernier": ("Le Tavernier", 25, 80, 0.52, 0.33, 0.15, 40),
    "marchand": ("Le Marchand", 40, 115, 0.44, 0.34, 0.22, 65),
    "forgeron": ("Le Forgeron", 55, 145, 0.36, 0.34, 0.30, 90),
    "vigile": ("Le Vigile", 90, 220, 0.22, 0.28, 0.50, 150),
}
SPECIAL_CONTRACT_REWARD_MIN = 600
SPECIAL_CONTRACT_REWARD_MAX = 1100

CRIMINAL_REPUTATION_TIERS = [(5, "Inconnu"), (20, "Petite frappe"), (60, "Bandit"), (150, "Criminel"), (300, "Seigneur de la Ruelle")]


@dataclass(frozen=True)
class Heist:
    heist_id: str
    user_id: int
    code: str
    attempts_used: int
    status: str
    started_at: int

    @property
    def attempts_left(self) -> int:
        return max(0, HEIST_ATTEMPTS - self.attempts_used)


class DarkAlleyStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            # players et resources existent déjà dans les autres modules, mais ces CREATE rendent le module autonome.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    user_id INTEGER PRIMARY KEY,
                    wallet_gold INTEGER NOT NULL DEFAULT 0 CHECK(wallet_gold >= 0),
                    bank_gold INTEGER NOT NULL DEFAULT 0 CHECK(bank_gold >= 0),
                    last_withdrawal_date TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS resources (
                    user_id INTEGER NOT NULL,
                    resource_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0 CHECK(quantity >= 0),
                    PRIMARY KEY(user_id, resource_name)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dark_actions (
                    user_id INTEGER NOT NULL,
                    action_type TEXT NOT NULL,
                    last_used_at INTEGER NOT NULL,
                    PRIMARY KEY(user_id, action_type)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alley_bans (
                    user_id INTEGER PRIMARY KEY,
                    banned_until INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bank_heists (
                    heist_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    attempts_used INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    started_at INTEGER NOT NULL,
                    finished_at INTEGER
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_heist_user ON bank_heists(user_id, started_at DESC)")
            conn.execute("""CREATE TABLE IF NOT EXISTS criminal_reputation (
                user_id INTEGER PRIMARY KEY, successes INTEGER NOT NULL DEFAULT 0
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS criminal_record (
                user_id INTEGER PRIMARY KEY, theft_success INTEGER NOT NULL DEFAULT 0,
                theft_fail INTEGER NOT NULL DEFAULT 0, crimes_success INTEGER NOT NULL DEFAULT 0,
                heists_success INTEGER NOT NULL DEFAULT 0, gold_stolen INTEGER NOT NULL DEFAULT 0,
                biggest_loot INTEGER NOT NULL DEFAULT 0, caught INTEGER NOT NULL DEFAULT 0
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS criminal_contracts (
                user_id INTEGER PRIMARY KEY, contract_type TEXT NOT NULL, target INTEGER NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0, reward INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
            )""")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clandestine_access (
                    user_id INTEGER PRIMARY KEY,
                    granted_at INTEGER NOT NULL,
                    method TEXT NOT NULL
                )
            """)
            conn.commit()

    @staticmethod
    def _ensure_player(conn, user_id: int):
        conn.execute("INSERT OR IGNORE INTO players(user_id) VALUES (?)", (int(user_id),))

    @staticmethod
    def _criminal_tier(successes: int) -> tuple[int, str]:
        tier, label = 0, "Inconnu"
        for i, (needed, name) in enumerate(CRIMINAL_REPUTATION_TIERS, 1):
            if successes >= needed: tier, label = i, name
        return tier, label

    def criminal_reputation(self, user_id: int) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT successes FROM criminal_reputation WHERE user_id=?", (int(user_id),)).fetchone()
        successes = int(row[0]) if row else 0
        tier, label = self._criminal_tier(successes)
        return {"successes": successes, "tier": tier, "label": label}

    @staticmethod
    def _add_criminal_success(conn, user_id: int):
        conn.execute("""INSERT INTO criminal_reputation(user_id,successes) VALUES(?,1)
                     ON CONFLICT(user_id) DO UPDATE SET successes=successes+1""", (int(user_id),))

    @staticmethod
    def _record(conn, user_id: int, *, theft_success=0, theft_fail=0, crimes_success=0, heists_success=0, gold_stolen=0, loot=0, caught=0):
        conn.execute("INSERT OR IGNORE INTO criminal_record(user_id) VALUES (?)", (int(user_id),))
        conn.execute("""UPDATE criminal_record SET theft_success=theft_success+?, theft_fail=theft_fail+?,
                     crimes_success=crimes_success+?, heists_success=heists_success+?, gold_stolen=gold_stolen+?,
                     biggest_loot=MAX(biggest_loot,?), caught=caught+? WHERE user_id=?""",
                     (theft_success,theft_fail,crimes_success,heists_success,gold_stolen,loot,caught,int(user_id)))

    def criminal_record(self, user_id: int) -> dict:
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO criminal_record(user_id) VALUES (?)", (int(user_id),))
            row=conn.execute("SELECT * FROM criminal_record WHERE user_id=?",(int(user_id),)).fetchone(); conn.commit()
        return dict(row)

    def _contract_progress(self, conn, user_id: int, event: str):
        row=conn.execute("SELECT * FROM criminal_contracts WHERE user_id=? AND status='active'",(int(user_id),)).fetchone()
        if not row or int(row['expires_at']) <= int(time.time()): return
        mapping={'npc_theft':'steal_npc','crime':'crime','heist':'heist'}
        if mapping.get(event) != row['contract_type']: return
        progress=min(int(row['target']),int(row['progress'])+1)
        conn.execute("UPDATE criminal_contracts SET progress=? WHERE user_id=?",(progress,int(user_id)))

    def contract_info(self, user_id: int) -> dict | None:
        with self._connect() as conn:
            row=conn.execute("SELECT * FROM criminal_contracts WHERE user_id=?",(int(user_id),)).fetchone()
        if not row: return None
        d=dict(row); d['expired']=d['status']=='active' and int(d['expires_at'])<=int(time.time()); return d

    def casino_vip(self, user_id: int) -> bool:
        with self._connect() as conn:
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM casino_sessions WHERE user_id=? AND status='finished' AND payout>wager",
                    (int(user_id),),
                ).fetchone()
            except sqlite3.OperationalError:
                return False
        return bool(row and int(row[0]) >= 200)

    def ban_remaining(self, user_id: int) -> int:
        now = int(time.time())
        with self._connect() as conn:
            row = conn.execute("SELECT banned_until FROM alley_bans WHERE user_id=?", (int(user_id),)).fetchone()
            if not row:
                return 0
            remaining = int(row["banned_until"]) - now
            if remaining <= 0:
                conn.execute("DELETE FROM alley_bans WHERE user_id=?", (int(user_id),))
                conn.commit()
                return 0
            return remaining

    def cooldown_remaining(self, user_id: int, action_type: str) -> int:
        if not cooldowns_enabled(self.db_path):
            return 0
        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_used_at FROM dark_actions WHERE user_id=? AND action_type=?",
                (int(user_id), action_type),
            ).fetchone()
        if not row:
            return 0
        return max(0, int(row["last_used_at"]) + ACTION_COOLDOWN - int(time.time()))

    def _consume_action(self, conn, user_id: int, action_type: str) -> tuple[bool, int]:
        if not cooldowns_enabled(self.db_path):
            return True, 0
        now = int(time.time())
        row = conn.execute(
            "SELECT last_used_at FROM dark_actions WHERE user_id=? AND action_type=?",
            (int(user_id), action_type),
        ).fetchone()
        if row:
            remaining = int(row["last_used_at"]) + ACTION_COOLDOWN - now
            if remaining > 0:
                return False, remaining
        conn.execute("""
            INSERT INTO dark_actions(user_id,action_type,last_used_at) VALUES (?,?,?)
            ON CONFLICT(user_id,action_type) DO UPDATE SET last_used_at=excluded.last_used_at
        """, (int(user_id), action_type, now))
        return True, 0

    def petty_larceny(self, user_id: int) -> dict:
        """Action d'initiation permettant de progresser d'Inconnu vers Petite frappe."""
        user_id = int(user_id)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_player(conn, user_id)
            ok, remaining = self._consume_action(conn, user_id, "larceny")
            if not ok:
                conn.rollback(); return {"ok": False, "cooldown": remaining}
            reward = random.randint(10, 35) * event_multiplier(self.db_path, 'gold_x2')
            conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (reward, user_id))
            self._add_criminal_success(conn, user_id)
            conn.commit()
        return {"ok": True, "amount": reward}

    def steal_npc(self, user_id: int, target_key: str) -> dict:
        user_id = int(user_id)
        rep = self.criminal_reputation(user_id)
        if rep["label"] not in ("Petite frappe", "Bandit", "Criminel", "Seigneur de la Ruelle"):
            return {"ok": False, "message": "Atteins le rang Petite frappe pour voler les PNJ de Altherya."}
        target = NPC_THEFT_TARGETS.get(str(target_key))
        if not target: return {"ok": False, "message": "Cible inconnue."}
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_player(conn, user_id)
            ok, remaining = self._consume_action(conn, user_id, "steal")
            if not ok: conn.rollback(); return {"ok": False, "cooldown": remaining}
            roll=random.random(); success_p, fail_p = target[3], target[4]
            if roll < success_p:
                amount = random.randint(target[1], target[2]) * event_multiplier(self.db_path, 'gold_x2')
                conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (amount, user_id))
                self._add_criminal_success(conn, user_id); self._record(conn,user_id,theft_success=1,gold_stolen=amount,loot=amount)
                self._contract_progress(conn,user_id,'npc_theft'); conn.commit()
                return {"ok": True, "outcome": "success", "amount": amount, "target": target[0], "chance": success_p}
            if roll < success_p + fail_p:
                self._record(conn,user_id,theft_fail=1); conn.commit()
                return {"ok": True, "outcome": "fail", "amount": 0, "target": target[0], "chance": success_p}
            wallet=int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?",(user_id,)).fetchone()[0])
            fine=min(wallet,target[6])
            if fine: conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?",(fine,user_id))
            self._record(conn,user_id,theft_fail=1,caught=1); conn.commit()
            return {"ok": True, "outcome": "caught", "amount": fine, "target": target[0], "chance": success_p}

    def special_contract(self, user_id: int) -> dict:
        """Contrats criminels adaptés au rang de réputation du joueur.

        Petite frappe : petits vols ; Bandit : vols/crimes ; Criminel : crimes/braquage ;
        Seigneur : contrats lourds. Les contrats restent valables 24 h, avec une fenêtre
        totale de 72 h avant qu'un nouveau contrat puisse être obtenu.
        """
        user_id=int(user_id); rep=self.criminal_reputation(user_id)
        label=rep.get("label","Inconnu")
        rank_level={"Petite frappe":1,"Bandit":2,"Criminel":3,"Seigneur de la Ruelle":4}.get(label,0)
        if rank_level <= 0:
            return {"ok":False,"message":"🔒 Atteins au moins le rang **Petite frappe** pour recevoir des contrats criminels."}

        pools = {
            1: [("steal_npc",2,350)],
            2: [("steal_npc",4,550),("crime",2,700)],
            3: [("steal_npc",5,800),("crime",4,950),("heist",1,1200)],
            4: [("steal_npc",6,1400),("crime",6,1600),("heist",2,1900)],
            5: [("steal_npc",6,1400),("crime",6,1600),("heist",2,1900)],
        }
        now=int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row=conn.execute("SELECT * FROM criminal_contracts WHERE user_id=?",(user_id,)).fetchone()
            if row and row['status'] != 'active' and now < int(row['expires_at']) + 48*3600:
                conn.commit(); return {"ok":False,"message":f"📜 Aucun nouveau contrat pour le moment. Reviens dans environ {max(1,(int(row['expires_at'])+48*3600-now+3599)//3600)} h."}
            if row and row['status']=='active' and int(row['expires_at'])>now:
                if int(row['progress']) >= int(row['target']):
                    self._ensure_player(conn,user_id); reward=int(row['reward'])*event_multiplier(self.db_path,'gold_x2')
                    conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?",(reward,user_id))
                    conn.execute("UPDATE criminal_contracts SET status='claimed' WHERE user_id=?",(user_id,)); conn.commit()
                    return {"ok":True,"claimed":True,"amount":reward,"rank":label}
                conn.commit(); return {"ok":True,"active":True,"contract":dict(row),"rank":label}
            ctype,target,reward=random.choice(pools[min(rank_level,5)])
            expires=now+24*3600
            conn.execute("""INSERT INTO criminal_contracts(user_id,contract_type,target,progress,reward,expires_at,status)
                         VALUES(?,?,?,?,?,?,'active') ON CONFLICT(user_id) DO UPDATE SET contract_type=excluded.contract_type,
                         target=excluded.target,progress=0,reward=excluded.reward,expires_at=excluded.expires_at,status='active'""",
                         (user_id,ctype,target,0,reward,expires)); conn.commit()
            return {"ok":True,"new":True,"rank":label,"contract":{"contract_type":ctype,"target":target,"progress":0,"reward":reward,"expires_at":expires}}

    def steal(self, thief_id: int, victim_id: int) -> dict:
        thief_id, victim_id = int(thief_id), int(victim_id)
        if self.criminal_reputation(thief_id)["label"] not in ("Petite frappe", "Bandit", "Criminel", "Seigneur de la Ruelle"):
            return {"ok": False, "message": "Atteins le rang Petite frappe pour voler un joueur."}
        if thief_id == victim_id:
            return {"ok": False, "message": "Tu ne peux pas te voler toi-même."}
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_player(conn, thief_id)
            self._ensure_player(conn, victim_id)
            ok, remaining = self._consume_action(conn, thief_id, "steal")
            if not ok:
                conn.rollback()
                return {"ok": False, "cooldown": remaining}

            thief = int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (thief_id,)).fetchone()[0])
            victim = int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (victim_id,)).fetchone()[0])
            # La réputation criminelle de la cible représente son expérience de la rue.
            victim_rep=self.criminal_reputation(victim_id); tier=int(victim_rep['tier'])
            # faible réputation = facile/petit butin ; forte réputation = difficile/gros butin et riposte probable
            chances={0:(0.70,0.25,0.05),1:(0.62,0.28,0.10),2:(0.52,0.30,0.18),3:(0.42,0.30,0.28),4:(0.32,0.28,0.40),5:(0.22,0.23,0.55)}
            success_p,fail_p,caught_p=chances.get(tier,chances[5]); roll=random.random()
            steal_caps={0:45,1:65,2:90,3:125,4:165,5:220}; cap=steal_caps.get(tier,220)
            if roll < success_p:
                amount=min(cap,victim,max(THEFT_MIN,int(victim*(0.06+0.02*tier)))) if victim else 0
                if amount>0:
                    conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?",(amount,victim_id)); conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?",(amount,thief_id))
                self._add_criminal_success(conn,thief_id); self._record(conn,thief_id,theft_success=1,gold_stolen=amount,loot=amount); conn.commit()
                return {"ok":True,"outcome":"success","amount":amount,"victim_rep":victim_rep['label'],"chances":chances[tier]}
            if roll < success_p+fail_p:
                self._record(conn,thief_id,theft_fail=1); conn.commit()
                return {"ok":True,"outcome":"fail","amount":0,"victim_rep":victim_rep['label'],"chances":chances[tier]}
            retaliation_cap={0:20,1:35,2:55,3:85,4:125,5:180}.get(tier,180)
            amount=min(retaliation_cap,thief,max(5,int(thief*(0.04+0.015*tier)))) if thief else 0
            if amount>0:
                conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?",(amount,thief_id)); conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?",(amount,victim_id))
            self._record(conn,thief_id,theft_fail=1,caught=1); conn.commit()
            return {"ok":True,"outcome":"caught","amount":amount,"victim_rep":victim_rep['label'],"chances":chances[tier]}

    def commit_crime(self, user_id: int) -> dict:
        user_id = int(user_id)
        if self.criminal_reputation(user_id)["label"] not in ("Bandit", "Criminel", "Seigneur de la Ruelle"):
            return {"ok": False, "message": "Atteins le rang Bandit pour commettre des crimes."}
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_player(conn, user_id)
            ok, remaining = self._consume_action(conn, user_id, "crime")
            if not ok:
                conn.rollback()
                return {"ok": False, "cooldown": remaining}

            wallet = int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (user_id,)).fetchone()[0])
            outcome = random.randrange(3)
            if outcome == 0:
                amount = random.randint(CRIME_REWARD_MIN, CRIME_REWARD_MAX) * event_multiplier(self.db_path, 'gold_x2')
                conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (amount, user_id))
                self._add_criminal_success(conn, user_id); self._record(conn,user_id,crimes_success=1,loot=amount); self._contract_progress(conn,user_id,'crime')
                conn.commit()
                return {"ok": True, "outcome": "success", "amount": amount}
            if outcome == 1:
                conn.commit()
                return {"ok": True, "outcome": "fail", "amount": 0}

            fine = min(CRIME_FINE, wallet)
            if fine:
                conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?", (fine, user_id))
            conn.commit()
            return {"ok": True, "outcome": "caught", "amount": fine, "fine_nominal": CRIME_FINE}

    def active_heist(self, user_id: int) -> Heist | None:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT * FROM bank_heists WHERE user_id=? AND status='active'
                ORDER BY started_at DESC LIMIT 1
            """, (int(user_id),)).fetchone()
        if not row:
            return None
        return Heist(str(row["heist_id"]), int(row["user_id"]), str(row["code"]), int(row["attempts_used"]), str(row["status"]), int(row["started_at"]))

    def start_heist(self, user_id: int) -> tuple[bool, str, Heist | None]:
        user_id = int(user_id)
        if self.criminal_reputation(user_id)["label"] not in ("Criminel", "Seigneur de la Ruelle"):
            return False, "rank_locked", None
        remaining = self.ban_remaining(user_id)
        if remaining:
            return False, "banned", None
        current = self.active_heist(user_id)
        if current:
            return True, "existing", current
        # 4 chiffres tous différents : le feedback Mastermind reste parfaitement lisible.
        code = "".join(random.sample("0123456789", HEIST_CODE_LENGTH))
        heist = Heist(uuid.uuid4().hex, user_id, code, 0, "active", int(time.time()))
        with self._connect() as conn:
            conn.execute("INSERT INTO bank_heists(heist_id,user_id,code,attempts_used,status,started_at) VALUES (?,?,?,?,?,?)",
                         (heist.heist_id, user_id, code, 0, "active", heist.started_at))
            conn.commit()
        return True, "started", heist

    @staticmethod
    def _feedback(code: str, guess: str) -> tuple[int, int, int]:
        well = sum(a == b for a, b in zip(code, guess))
        # Comme le code est sans doublons, on compte les chiffres présents puis on retire les bien placés.
        present = sum(ch in code for ch in guess)
        misplaced = max(0, present - well)
        incorrect = len(guess) - well - misplaced
        return well, misplaced, incorrect

    @staticmethod
    def _feedback_details(code: str, guess: str) -> list[tuple[str, str]]:
        details = []
        for pos, ch in enumerate(guess):
            if code[pos] == ch:
                status = "bien placé"
            elif ch in code:
                status = "mal placé"
            else:
                status = "incorrect"
            details.append((ch, status))
        return details

    def guess_heist(self, user_id: int, guess: str) -> dict:
        user_id = int(user_id)
        guess = str(guess).strip()
        if len(guess) != HEIST_CODE_LENGTH or not guess.isdigit() or len(set(guess)) != HEIST_CODE_LENGTH:
            return {"ok": False, "message": f"Entre {HEIST_CODE_LENGTH} chiffres différents (exemple : 5072)."}

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("""
                SELECT * FROM bank_heists WHERE user_id=? AND status='active'
                ORDER BY started_at DESC LIMIT 1
            """, (user_id,)).fetchone()
            if not row:
                conn.rollback()
                return {"ok": False, "message": "Aucun braquage actif."}

            code = str(row["code"])
            used = int(row["attempts_used"]) + 1
            well, misplaced, incorrect = self._feedback(code, guess)
            details = self._feedback_details(code, guess)
            now = int(time.time())

            if guess == code:
                reward = random.randint(HEIST_REWARD_MIN, HEIST_REWARD_MAX) * event_multiplier(self.db_path, 'gold_x2')
                self._ensure_player(conn, user_id)
                conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (reward, user_id))
                conn.execute("UPDATE bank_heists SET attempts_used=?,status='won',finished_at=? WHERE heist_id=?",
                             (used, now, row["heist_id"]))
                self._add_criminal_success(conn, user_id); self._record(conn,user_id,heists_success=1,loot=reward); self._contract_progress(conn,user_id,'heist')
                conn.commit()
                return {"ok": True, "won": True, "reward": reward, "guess": guess, "well": well, "misplaced": misplaced, "incorrect": incorrect, "attempts_left": HEIST_ATTEMPTS-used, "details": details}

            if used >= HEIST_ATTEMPTS:
                self._ensure_player(conn, user_id)
                wallet = int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (user_id,)).fetchone()[0])
                fine = min(HEIST_FAIL_FINE, wallet)
                if fine:
                    conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?", (fine, user_id))
                conn.execute("UPDATE bank_heists SET attempts_used=?,status='lost',finished_at=? WHERE heist_id=?",
                             (used, now, row["heist_id"]))
                conn.execute("""
                    INSERT INTO alley_bans(user_id,banned_until) VALUES (?,?)
                    ON CONFLICT(user_id) DO UPDATE SET banned_until=excluded.banned_until
                """, (user_id, now + ALLEY_BAN_SECONDS))
                conn.commit()
                return {"ok": True, "won": False, "lost": True, "fine": fine, "fine_nominal": HEIST_FAIL_FINE,
                        "code": code, "guess": guess, "well": well, "misplaced": misplaced, "incorrect": incorrect, "attempts_left": 0, "details": details}

            conn.execute("UPDATE bank_heists SET attempts_used=? WHERE heist_id=?", (used, row["heist_id"]))
            conn.commit()
            return {"ok": True, "won": False, "lost": False, "guess": guess, "well": well,
                    "misplaced": misplaced, "incorrect": incorrect, "attempts_left": HEIST_ATTEMPTS-used, "details": details}

    def invitation_count(self, user_id: int) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT quantity FROM resources WHERE user_id=? AND resource_name=?",
                               (int(user_id), INVITATION_ITEM)).fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _server_day_from_timestamp(timestamp: int):
        return datetime.fromtimestamp(int(timestamp)).date()

    @staticmethod
    def seconds_until_server_midnight() -> int:
        now = datetime.now()
        tomorrow = now.date() + timedelta(days=1)
        midnight = datetime.combine(tomorrow, datetime.min.time())
        return max(0, int((midnight - now).total_seconds()))

    def clandestine_access_info(self, user_id: int) -> dict:
        """Retourne l'état du pass journalier de la salle clandestine.

        Un pass n'est valable que pour la date civile courante en heure locale du serveur.
        Dès 00:00, même si le joueur est déjà dans la salle, toute nouvelle action
        doit être refusée jusqu'à un nouveau paiement ou une nouvelle invitation.
        """
        user_id = int(user_id)
        now = int(time.time())
        today = datetime.now().date()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT granted_at, method FROM clandestine_access WHERE user_id=?",
                (user_id,),
            ).fetchone()
            if not row:
                return {"valid": False, "reason": "missing", "seconds_left": 0}

            granted_at = int(row["granted_at"])
            if self._server_day_from_timestamp(granted_at) != today:
                # Nettoyage paresseux : l'ancien pass est supprimé au premier contrôle après minuit.
                conn.execute("DELETE FROM clandestine_access WHERE user_id=?", (user_id,))
                conn.commit()
                return {"valid": False, "reason": "expired", "seconds_left": 0}

            return {
                "valid": True,
                "reason": "valid",
                "method": str(row["method"]),
                "granted_at": granted_at,
                "seconds_left": self.seconds_until_server_midnight(),
                "checked_at": now,
            }

    def enter_clandestine_room(self, user_id: int, use_invitation: bool) -> dict:
        user_id = int(user_id)

        # Un joueur qui a déjà payé/consommé un ticket aujourd'hui ne repaie pas.
        current = self.clandestine_access_info(user_id)
        if current.get("valid"):
            return {
                "ok": True,
                "already": True,
                "method": current.get("method"),
                "paid": 0,
                "seconds_left": current.get("seconds_left", 0),
            }

        vip = self.casino_vip(user_id)
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_player(conn, user_id)
            if vip:
                conn.execute("""
                    INSERT INTO clandestine_access(user_id,granted_at,method) VALUES (?,?,?)
                    ON CONFLICT(user_id) DO UPDATE SET granted_at=excluded.granted_at, method=excluded.method
                """, (user_id, now, "vip"))
                conn.commit()
                return {"ok": True, "already": False, "method": "vip", "paid": 0,
                        "seconds_left": self.seconds_until_server_midnight()}

            if use_invitation:
                row = conn.execute("SELECT quantity FROM resources WHERE user_id=? AND resource_name=?",
                                   (user_id, INVITATION_ITEM)).fetchone()
                qty = int(row[0]) if row else 0
                if qty <= 0:
                    conn.rollback()
                    return {"ok": False, "message": "Tu ne possèdes aucune invitation clandestine."}
                conn.execute("UPDATE resources SET quantity=quantity-1 WHERE user_id=? AND resource_name=?",
                             (user_id, INVITATION_ITEM))
                conn.execute("""
                    INSERT INTO clandestine_access(user_id,granted_at,method) VALUES (?,?,?)
                    ON CONFLICT(user_id) DO UPDATE SET granted_at=excluded.granted_at, method=excluded.method
                """, (user_id, now, "invitation"))
                conn.commit()
                return {
                    "ok": True, "already": False, "method": "invitation", "paid": 0,
                    "seconds_left": self.seconds_until_server_midnight(),
                }

            wallet = int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (user_id,)).fetchone()[0])
            if wallet < GUARD_ENTRY_FEE:
                conn.rollback()
                return {"ok": False, "message": f"Le Vigile réclame {GUARD_ENTRY_FEE} Gold. Tu n'en as pas assez."}
            conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?", (GUARD_ENTRY_FEE, user_id))
            conn.execute("""
                INSERT INTO clandestine_access(user_id,granted_at,method) VALUES (?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET granted_at=excluded.granted_at, method=excluded.method
            """, (user_id, now, "gold"))
            conn.commit()
            return {
                "ok": True, "already": False, "method": "gold", "paid": GUARD_ENTRY_FEE,
                "seconds_left": self.seconds_until_server_midnight(),
            }

    def has_clandestine_access(self, user_id: int) -> bool:
        return bool(self.clandestine_access_info(user_id).get("valid"))

    def consume_clandestine_access(self, user_id: int) -> bool:
        """Compatibilité avec le futur module de salle.

        Le pass est journalier et ne doit PAS être consommé à l'entrée. Cette méthode
        valide simplement le pass. À partir de 00:00 heure locale du serveur elle renvoie False,
        ce qui permettra au Vigile de remettre immédiatement le joueur dehors.
        """
        return self.has_clandestine_access(user_id)


def short_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"
