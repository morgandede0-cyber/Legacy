from __future__ import annotations

import json
import random
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from progression import level_from_xp, FORGE_LEVEL_REQUIREMENTS, FORGE_GOLD_COSTS


# =========================
# ÉQUIPEMENTS — 5 PALIERS
# =========================

TOOL_LEVELS = {
    1: {"material": "Bois", "pickaxe": "Pioche en bois", "axe": "Hache en bois", "spear": "Lance en bois"},
    2: {"material": "Pierre", "pickaxe": "Pioche en pierre", "axe": "Hache en pierre", "spear": "Lance en pierre"},
    3: {"material": "Fer", "pickaxe": "Pioche en fer", "axe": "Hache en fer", "spear": "Lance en fer"},
    4: {"material": "Or", "pickaxe": "Pioche en or", "axe": "Hache en or", "spear": "Lance en or"},
    5: {"material": "Diamant", "pickaxe": "Pioche en diamant", "axe": "Hache en diamant", "spear": "Lance en diamant"},
}

BAG_LEVELS = {
    1: {"name": "Sac de fortune", "capacity": 8},
    2: {"name": "Sac renforcé", "capacity": 14},
    3: {"name": "Sac d'aventurier", "capacity": 22},
    4: {"name": "Sac d'explorateur", "capacity": 32},
    5: {"name": "Sac du Pionnier", "capacity": 45},
}

# Une recette améliore UN équipement d'un palier au suivant.
UPGRADE_RECIPES = {
    2: {"Pierre brute": 12, "Bois de chêne": 6, "Peau de sanglier": 3},
    3: {"Minerai de fer": 10, "Bois de frêne": 6, "Peau de loup": 3},
    4: {"Minerai d'or": 8, "Bois d'ébène": 5, "Peau d'ours": 2},
    5: {"Diamant brut": 5, "Bois ancestral": 4, "Peau de bête Alpha": 2},
}

BAG_UPGRADE_RECIPES = {
    2: {"Pierre brute": 6, "Bois de chêne": 10, "Peau de sanglier": 6},
    3: {"Minerai de fer": 5, "Bois de frêne": 8, "Peau de loup": 5},
    4: {"Minerai d'or": 4, "Bois d'ébène": 6, "Peau d'ours": 4},
    5: {"Diamant brut": 3, "Bois ancestral": 5, "Peau de bête Alpha": 3},
}

TOOL_META = {
    "pickaxe": {"emoji": "⛏️", "label": "Pioche", "family": "mining"},
    "axe": {"emoji": "🪓", "label": "Hache", "family": "wood"},
    "spear": {"emoji": "🗡️", "label": "Lance", "family": "hunt"},
}

STARTER_GEAR = {
    "pickaxe": {"name": "Pioche en bois", "price": 100},
    "axe": {"name": "Hache en bois", "price": 100},
    "spear": {"name": "Lance en bois", "price": 100},
    "bag": {"name": "Sac de fortune", "price": 100},
}

# Prix de revente volontairement modérés : les matériaux de Forge ont plus de valeur
# conservés qu'écoulés immédiatement au Marché.
RESOURCE_SELL_PRICES = {
    "Pierre brute": 2, "Bois de chêne": 2, "Viande de sanglier": 2, "Peau de sanglier": 4, "Défense de sanglier": 5,
    "Minerai de fer": 5, "Bois de frêne": 5, "Viande de loup": 4, "Peau de loup": 6, "Croc de loup": 8,
    "Viande de crocodile": 5, "Peau de crocodile": 8, "Croc de crocodile": 9,
    "Minerai d'or": 11, "Bois d'ébène": 10, "Peau d'ours": 12, "Griffe d'ours": 13,
    "Peau de félin du désert": 11, "Croc de félin du désert": 13,
    "Diamant brut": 24, "Bois ancestral": 22, "Peau de bête Alpha": 26, "Croc Alpha": 28, "Griffe Alpha": 30,
    "Cristal ancien": 55, "Cœur de bois ancien": 55, "Trophée légendaire": 70,
}


# =========================
# EXPÉDITIONS
# =========================

EXPEDITIONS = {
    "forest": {"name": "Forêt des Brumes", "emoji": "🌲", "level": 1, "duration": 15 * 60, "duration_label": "15 min", "danger": "Faible"},
    "hills": {"name": "Collines Sauvages", "emoji": "⛰️", "level": 5, "duration": 30 * 60, "duration_label": "30 min", "danger": "Faible"},
    "ruins": {"name": "Ruines Anciennes", "emoji": "🏛️", "level": 10, "duration": 60 * 60, "duration_label": "1 h", "danger": "Moyen"},
    "swamp": {"name": "Marais Putrides", "emoji": "🐊", "level": 15, "duration": 2 * 60 * 60, "duration_label": "2 h", "danger": "Élevé"},
    "desert": {"name": "Désert Aride", "emoji": "🏜️", "level": 20, "duration": 4 * 60 * 60, "duration_label": "4 h", "danger": "Élevé"},
    "mountains": {"name": "Montagnes Glaciales", "emoji": "🏔️", "level": 25, "duration": 6 * 60 * 60, "duration_label": "6 h", "danger": "Extrême"},
}

# Entrée : (nom, niveau outil minimum, poids)
# Le niveau de zone et le niveau d'outil travaillent ensemble : un bon outil ne crée pas
# artificiellement un matériau rare dans une zone qui n'en contient pas.
LOOT_TABLES: Dict[str, Dict[str, List[Tuple[str, int, int]]]] = {
    "forest": {
        "pickaxe": [("Pierre brute", 1, 85), ("Minerai de fer", 2, 15)],
        "axe": [("Bois de chêne", 1, 88), ("Bois de frêne", 2, 12)],
        "spear": [("Viande de sanglier", 1, 55), ("Peau de sanglier", 1, 30), ("Défense de sanglier", 1, 10), ("Peau de loup", 2, 5)],
    },
    "hills": {
        "pickaxe": [("Pierre brute", 1, 55), ("Minerai de fer", 2, 40), ("Minerai d'or", 3, 5)],
        "axe": [("Bois de chêne", 1, 50), ("Bois de frêne", 2, 45), ("Bois d'ébène", 3, 5)],
        "spear": [("Viande de sanglier", 1, 25), ("Peau de sanglier", 1, 18), ("Viande de loup", 2, 27), ("Peau de loup", 2, 22), ("Croc de loup", 2, 8)],
    },
    "ruins": {
        "pickaxe": [("Pierre brute", 1, 25), ("Minerai de fer", 2, 62), ("Minerai d'or", 3, 13)],
        "axe": [("Bois de chêne", 1, 20), ("Bois de frêne", 2, 65), ("Bois d'ébène", 3, 15)],
        "spear": [("Viande de loup", 2, 40), ("Peau de loup", 2, 42), ("Croc de loup", 2, 15), ("Peau d'ours", 3, 3)],
    },
    "swamp": {
        "pickaxe": [("Minerai de fer", 2, 48), ("Minerai d'or", 3, 45), ("Diamant brut", 4, 7)],
        "axe": [("Bois de frêne", 2, 48), ("Bois d'ébène", 3, 46), ("Bois ancestral", 4, 6)],
        "spear": [("Viande de crocodile", 2, 30), ("Peau de crocodile", 2, 30), ("Croc de crocodile", 2, 12), ("Peau d'ours", 3, 22), ("Griffe d'ours", 3, 6)],
    },
    "desert": {
        "pickaxe": [("Minerai de fer", 2, 18), ("Minerai d'or", 3, 67), ("Diamant brut", 4, 15)],
        "axe": [("Bois de frêne", 2, 18), ("Bois d'ébène", 3, 67), ("Bois ancestral", 4, 15)],
        "spear": [("Peau d'ours", 3, 40), ("Griffe d'ours", 3, 18), ("Peau de félin du désert", 3, 24), ("Croc de félin du désert", 3, 14), ("Peau de bête Alpha", 4, 4)],
    },
    "mountains": {
        "pickaxe": [("Minerai d'or", 3, 38), ("Diamant brut", 4, 57), ("Cristal ancien", 5, 5)],
        "axe": [("Bois d'ébène", 3, 34), ("Bois ancestral", 4, 61), ("Cœur de bois ancien", 5, 5)],
        "spear": [("Peau d'ours", 3, 18), ("Peau de bête Alpha", 4, 54), ("Croc Alpha", 4, 18), ("Griffe Alpha", 4, 8), ("Trophée légendaire", 5, 2)],
    },
}

RARITY = {
    "Pierre brute": 1, "Bois de chêne": 1, "Viande de sanglier": 1, "Peau de sanglier": 2, "Défense de sanglier": 2,
    "Minerai de fer": 2, "Bois de frêne": 2, "Viande de loup": 2, "Peau de loup": 2, "Croc de loup": 3,
    "Viande de crocodile": 2, "Peau de crocodile": 3, "Croc de crocodile": 3,
    "Minerai d'or": 3, "Bois d'ébène": 3, "Peau d'ours": 3, "Griffe d'ours": 3, "Peau de félin du désert": 3, "Croc de félin du désert": 3,
    "Diamant brut": 4, "Bois ancestral": 4, "Peau de bête Alpha": 4, "Croc Alpha": 4, "Griffe Alpha": 4,
    "Cristal ancien": 5, "Cœur de bois ancien": 5, "Trophée légendaire": 5,
}

RARITY_EMOJI = {1: "⚪", 2: "🟢", 3: "🔵", 4: "🟣", 5: "🟡"}

# Objets de préparation : ils sont volontairement neutres pour le moment.
# Ils sont sauvegardés dans l'expédition et affichés dans le récapitulatif afin
# de pouvoir leur ajouter des bonus plus tard sans refaire l'interface.
EXPEDITION_OBJECTS = {
    "none": {"emoji": "◻️", "name": "Aucun objet", "description": "Emplacement laissé libre."},
    "rope": {"emoji": "🪢", "name": "Corde solide", "description": "Matériel de progression et de sécurisation."},
    "torch": {"emoji": "🔥", "name": "Torche renforcée", "description": "Éclaire les zones dangereuses."},
    "rations": {"emoji": "🥖", "name": "Rations de voyage", "description": "Provisions pour les longues expéditions."},
    "compass": {"emoji": "🧭", "name": "Boussole d'explorateur", "description": "Aide à conserver le cap."},
}


@dataclass(frozen=True)
class Gear:
    pickaxe_level: int
    axe_level: int
    spear_level: int
    bag_level: int

    def tool_level(self, tool_key: str) -> int:
        return {"pickaxe": self.pickaxe_level, "axe": self.axe_level, "spear": self.spear_level}[tool_key]


@dataclass(frozen=True)
class ExpeditionRun:
    run_id: str
    user_id: int
    expedition_key: str
    tool_key: str
    tool_level: int
    bag_level: int
    capacity: int
    started_at: int
    ends_at: int
    claimed: bool
    loot: Dict[str, int]
    object1_key: str = "none"
    object2_key: str = "none"
    status_channel_id: int | None = None
    status_message_id: int | None = None

    @property
    def finished(self) -> bool:
        return int(time.time()) >= self.ends_at

    @property
    def remaining_seconds(self) -> int:
        return max(0, self.ends_at - int(time.time()))


class ExpeditionStore:
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS expedition_profiles (
                    user_id INTEGER PRIMARY KEY,
                    player_level INTEGER NOT NULL DEFAULT 1 CHECK(player_level >= 1),
                    pickaxe_level INTEGER NOT NULL DEFAULT 1 CHECK(pickaxe_level BETWEEN 1 AND 5),
                    axe_level INTEGER NOT NULL DEFAULT 1 CHECK(axe_level BETWEEN 1 AND 5),
                    spear_level INTEGER NOT NULL DEFAULT 1 CHECK(spear_level BETWEEN 1 AND 5),
                    bag_level INTEGER NOT NULL DEFAULT 1 CHECK(bag_level BETWEEN 1 AND 5)
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
                CREATE TABLE IF NOT EXISTS equipment_ownership (
                    user_id INTEGER PRIMARY KEY,
                    pickaxe_owned INTEGER NOT NULL DEFAULT 0,
                    axe_owned INTEGER NOT NULL DEFAULT 0,
                    spear_owned INTEGER NOT NULL DEFAULT 0,
                    bag_owned INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS expedition_runs (
                    run_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expedition_key TEXT NOT NULL,
                    tool_key TEXT NOT NULL,
                    tool_level INTEGER NOT NULL,
                    bag_level INTEGER NOT NULL,
                    capacity INTEGER NOT NULL,
                    started_at INTEGER NOT NULL,
                    ends_at INTEGER NOT NULL,
                    claimed INTEGER NOT NULL DEFAULT 0,
                    loot_json TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expedition_runs_user ON expedition_runs(user_id, started_at DESC)")
            # Migrations souples pour les anciennes bases Legacy.
            columns = {str(r["name"]) for r in conn.execute("PRAGMA table_info(expedition_runs)").fetchall()}
            for name, sql_type, default in (
                ("object1_key", "TEXT", "'none'"),
                ("object2_key", "TEXT", "'none'"),
                ("status_channel_id", "INTEGER", "NULL"),
                ("status_message_id", "INTEGER", "NULL"),
            ):
                if name not in columns:
                    conn.execute(f"ALTER TABLE expedition_runs ADD COLUMN {name} {sql_type} DEFAULT {default}")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS expedition_drop_events (
                    run_id TEXT NOT NULL,
                    event_index INTEGER NOT NULL,
                    drop_at INTEGER NOT NULL,
                    resource_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    revealed INTEGER NOT NULL DEFAULT 0,
                    revealed_at INTEGER,
                    PRIMARY KEY(run_id, event_index)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expedition_drop_due ON expedition_drop_events(run_id, revealed, drop_at)")
            conn.commit()

    def ensure_profile(self, user_id: int):
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO expedition_profiles(user_id) VALUES (?)", (int(user_id),))
            conn.execute("INSERT OR IGNORE INTO equipment_ownership(user_id) VALUES (?)", (int(user_id),))
            conn.commit()

    def get_player_level(self, user_id: int) -> int:
        self.ensure_profile(user_id)
        with self._connect() as conn:
            row = conn.execute("SELECT xp FROM castle_profiles WHERE user_id=?", (int(user_id),)).fetchone()
            if row:
                level = level_from_xp(int(row["xp"]))[0]
                conn.execute("UPDATE expedition_profiles SET player_level=? WHERE user_id=?", (level, int(user_id)))
                conn.commit()
                return level
            row = conn.execute("SELECT player_level FROM expedition_profiles WHERE user_id=?", (int(user_id),)).fetchone()
        return int(row["player_level"])

    def owned_equipment(self, user_id: int) -> Dict[str, bool]:
        self.ensure_profile(user_id)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM equipment_ownership WHERE user_id=?", (int(user_id),)).fetchone()
        return {k: bool(row[f"{k}_owned"]) for k in ("pickaxe","axe","spear","bag")}

    def has_equipment(self, user_id: int, equipment: str) -> bool:
        return bool(self.owned_equipment(user_id).get(equipment, False))

    def buy_starter(self, user_id: int, equipment: str) -> tuple[bool, str]:
        if equipment not in STARTER_GEAR:
            return False, "Équipement inconnu."
        uid=int(user_id); price=int(STARTER_GEAR[equipment]["price"]); self.ensure_profile(uid)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            owned=conn.execute(f"SELECT {equipment}_owned v FROM equipment_ownership WHERE user_id=?",(uid,)).fetchone()
            if owned and int(owned["v"]):
                conn.rollback(); return False, "Tu possèdes déjà cet équipement. Il n'est plus disponible à l'achat."
            conn.execute("INSERT OR IGNORE INTO players(user_id) VALUES(?)",(uid,))
            wallet=int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?",(uid,)).fetchone()[0])
            if wallet < price:
                conn.rollback(); return False, f"Il te manque {price-wallet} Gold."
            conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?",(price,uid))
            conn.execute(f"UPDATE equipment_ownership SET {equipment}_owned=1 WHERE user_id=?",(uid,))
            conn.commit()
        return True, f"{STARTER_GEAR[equipment]['name']} acheté pour {price} Gold."

    def sell_resource(self, user_id: int, resource_name: str, quantity: int) -> tuple[bool, str, int]:
        uid=int(user_id); qty=max(0,int(quantity)); unit=RESOURCE_SELL_PRICES.get(resource_name)
        if not unit or qty <= 0:
            return False, "Vente invalide.", 0
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row=conn.execute("SELECT quantity FROM resources WHERE user_id=? AND resource_name=?",(uid,resource_name)).fetchone()
            have=int(row[0]) if row else 0
            if have < qty:
                conn.rollback(); return False, f"Stock insuffisant : {have} disponible(s).", 0
            total=unit*qty
            conn.execute("UPDATE resources SET quantity=quantity-? WHERE user_id=? AND resource_name=?",(qty,uid,resource_name))
            conn.execute("DELETE FROM resources WHERE user_id=? AND resource_name=? AND quantity<=0",(uid,resource_name))
            conn.execute("INSERT OR IGNORE INTO players(user_id) VALUES(?)",(uid,))
            conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?",(total,uid))
            conn.commit()
        return True, f"Vente effectuée : {qty} × {resource_name} pour {total} Gold.", total

    def get_gear(self, user_id: int) -> Gear:
        self.ensure_profile(user_id)
        with self._connect() as conn:
            row = conn.execute("SELECT pickaxe_level,axe_level,spear_level,bag_level FROM expedition_profiles WHERE user_id=?", (int(user_id),)).fetchone()
        return Gear(int(row[0]), int(row[1]), int(row[2]), int(row[3]))

    def get_resources(self, user_id: int) -> Dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT resource_name, quantity FROM resources WHERE user_id=? AND quantity>0 ORDER BY resource_name", (int(user_id),)).fetchall()
        return {str(r["resource_name"]): int(r["quantity"]) for r in rows}

    def add_resources(self, user_id: int, loot: Dict[str, int]):
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for name, qty in loot.items():
                qty = int(qty)
                if qty <= 0:
                    continue
                conn.execute("""
                    INSERT INTO resources(user_id, resource_name, quantity) VALUES (?,?,?)
                    ON CONFLICT(user_id, resource_name) DO UPDATE SET quantity=quantity+excluded.quantity
                """, (int(user_id), name, qty))
            conn.commit()

    def active_run(self, user_id: int) -> ExpeditionRun | None:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT * FROM expedition_runs
                WHERE user_id=? AND claimed=0
                ORDER BY started_at DESC LIMIT 1
            """, (int(user_id),)).fetchone()
        return self._row_to_run(row) if row else None

    def start(self, user_id: int, expedition_key: str, tool_key: str, bag_level: int | None = None, object1_key: str = "none", object2_key: str = "none") -> tuple[bool, str, ExpeditionRun | None]:
        uid = int(user_id)
        if expedition_key not in EXPEDITIONS or tool_key not in TOOL_META:
            return False, "Configuration d'expédition invalide.", None
        if object1_key not in EXPEDITION_OBJECTS or object2_key not in EXPEDITION_OBJECTS:
            return False, "Objet d'expédition invalide.", None
        if object1_key != "none" and object1_key == object2_key:
            return False, "Choisis deux objets différents ou laisse un emplacement vide.", None
        self.ensure_profile(uid)
        current = self.active_run(uid)
        if current:
            return False, "Tu as déjà une expédition en cours ou des loots à récupérer.", current
        if not self.has_equipment(uid, tool_key):
            return False, f"Tu dois d'abord acheter {STARTER_GEAR[tool_key]['name']} au Marché.", None
        if not self.has_equipment(uid, "bag"):
            return False, "Tu dois d'abord acheter le Sac de fortune au Marché.", None

        level = self.get_player_level(uid)
        zone = EXPEDITIONS[expedition_key]
        if level < zone["level"]:
            return False, f"Niveau {zone['level']} requis pour {zone['name']}.", None

        gear = self.get_gear(uid)
        tool_level = gear.tool_level(tool_key)
        selected_bag_level = gear.bag_level if bag_level is None else int(bag_level)
        if selected_bag_level < 1 or selected_bag_level > gear.bag_level or selected_bag_level not in BAG_LEVELS:
            return False, "Sac sélectionné invalide ou non débloqué.", None
        bag_level = selected_bag_level
        capacity = BAG_LEVELS[bag_level]["capacity"]
        loot = generate_loot(expedition_key, tool_key, tool_level, capacity)
        now = int(time.time())
        run = ExpeditionRun(
            run_id=uuid.uuid4().hex,
            user_id=uid,
            expedition_key=expedition_key,
            tool_key=tool_key,
            tool_level=tool_level,
            bag_level=bag_level,
            capacity=capacity,
            started_at=now,
            ends_at=now + int(zone["duration"]),
            claimed=False,
            loot=loot,
            object1_key=object1_key,
            object2_key=object2_key,
        )
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""
                INSERT INTO expedition_runs(
                    run_id,user_id,expedition_key,tool_key,tool_level,bag_level,capacity,started_at,ends_at,claimed,loot_json,
                    object1_key,object2_key,status_channel_id,status_message_id
                ) VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?,NULL,NULL)
            """, (run.run_id,uid,expedition_key,tool_key,tool_level,bag_level,capacity,run.started_at,run.ends_at,
                  json.dumps(loot,ensure_ascii=False),object1_key,object2_key))

            # Un événement = un vrai drop visible dans les logs. Les instants sont
            # répartis sur toute la durée avec une légère variation, puis triés.
            drops: List[str] = []
            for name, qty in loot.items():
                drops.extend([name] * int(qty))
            random.shuffle(drops)
            if drops:
                duration = max(60, run.ends_at - run.started_at)
                slots = len(drops) + 1
                times = []
                for idx in range(1, len(drops) + 1):
                    base = run.started_at + int(duration * idx / slots)
                    jitter_span = max(1, int(duration / slots * 0.22))
                    jitter = random.randint(-jitter_span, jitter_span)
                    times.append(max(run.started_at + 5, min(run.ends_at - 2, base + jitter)))
                times.sort()
                for idx, (drop_at, name) in enumerate(zip(times, drops), start=1):
                    conn.execute("""
                        INSERT INTO expedition_drop_events(run_id,event_index,drop_at,resource_name,quantity,revealed)
                        VALUES(?,?,?,?,1,0)
                    """, (run.run_id, idx, int(drop_at), name))
            conn.commit()
        return True, "Expédition lancée.", run

    def claim(self, user_id: int) -> tuple[bool, str, Dict[str, int]]:
        uid = int(user_id)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM expedition_runs WHERE user_id=? AND claimed=0 ORDER BY started_at DESC LIMIT 1", (uid,)).fetchone()
            if not row:
                conn.rollback(); return False, "Aucune expédition à récupérer.", {}
            if int(time.time()) < int(row["ends_at"]):
                conn.rollback(); return False, "Cette expédition n'est pas encore terminée.", {}
            loot = json.loads(row["loot_json"] or "{}")
            for name, qty in loot.items():
                conn.execute("""
                    INSERT INTO resources(user_id, resource_name, quantity) VALUES (?,?,?)
                    ON CONFLICT(user_id, resource_name) DO UPDATE SET quantity=quantity+excluded.quantity
                """, (uid, name, int(qty)))
            conn.execute("UPDATE expedition_runs SET claimed=1 WHERE run_id=?", (row["run_id"],))
            conn.commit()
        return True, "Loots ajoutés à ton inventaire.", {str(k): int(v) for k,v in loot.items()}

    def upgrade(self, user_id: int, equipment: str) -> tuple[bool, str]:
        """Forge atomique : revérifie niveau, ownership, Gold et ressources au clic."""
        if equipment not in ("pickaxe", "axe", "spear", "bag"):
            return False, "Équipement inconnu."
        uid=int(user_id); self.ensure_profile(uid)
        if not self.has_equipment(uid,equipment):
            return False, "Tu dois d'abord acheter cet équipement niveau 1 au Marché."
        gear=self.get_gear(uid); current=gear.bag_level if equipment=="bag" else gear.tool_level(equipment)
        if current>=5:
            return False, "Cet équipement est déjà au niveau maximum."
        target=current+1; required_level=FORGE_LEVEL_REQUIREMENTS[target]; player_level=self.get_player_level(uid)
        if player_level < required_level:
            return False, f"Niveau joueur {required_level} requis. Tu es niveau {player_level}."
        recipe=BAG_UPGRADE_RECIPES[target] if equipment=="bag" else UPGRADE_RECIPES[target]
        gold_cost=FORGE_GOLD_COSTS["bag" if equipment=="bag" else "tool"][target]
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows=conn.execute("SELECT resource_name,quantity FROM resources WHERE user_id=?",(uid,)).fetchall()
            owned={r["resource_name"]:int(r["quantity"]) for r in rows}
            missing={k:v-owned.get(k,0) for k,v in recipe.items() if owned.get(k,0)<v}
            if missing:
                conn.rollback(); return False, "Ressources manquantes : "+", ".join(f"{n} x{q}" for n,q in missing.items())
            conn.execute("INSERT OR IGNORE INTO players(user_id) VALUES(?)",(uid,))
            wallet=int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?",(uid,)).fetchone()[0])
            if wallet < gold_cost:
                conn.rollback(); return False, f"Gold insuffisant : {wallet}/{gold_cost}."
            for name,qty in recipe.items():
                conn.execute("UPDATE resources SET quantity=quantity-? WHERE user_id=? AND resource_name=?",(qty,uid,name))
                conn.execute("DELETE FROM resources WHERE user_id=? AND resource_name=? AND quantity<=0",(uid,name))
            conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?",(gold_cost,uid))
            column="bag_level" if equipment=="bag" else f"{equipment}_level"
            conn.execute(f"UPDATE expedition_profiles SET {column}=? WHERE user_id=?",(target,uid))
            conn.commit()
        return True, f"Amélioration réussie : niveau {target} pour {gold_cost} Gold."

    def _row_to_run(self, row) -> ExpeditionRun:
        keys = set(row.keys())
        return ExpeditionRun(
            str(row["run_id"]), int(row["user_id"]), str(row["expedition_key"]), str(row["tool_key"]),
            int(row["tool_level"]), int(row["bag_level"]), int(row["capacity"]), int(row["started_at"]),
            int(row["ends_at"]), bool(row["claimed"]), {str(k): int(v) for k,v in json.loads(row["loot_json"] or "{}").items()},
            str(row["object1_key"] or "none") if "object1_key" in keys else "none",
            str(row["object2_key"] or "none") if "object2_key" in keys else "none",
            int(row["status_channel_id"]) if "status_channel_id" in keys and row["status_channel_id"] is not None else None,
            int(row["status_message_id"]) if "status_message_id" in keys and row["status_message_id"] is not None else None,
        )

    def run_by_id(self, run_id: str) -> ExpeditionRun | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM expedition_runs WHERE run_id=?", (str(run_id),)).fetchone()
        return self._row_to_run(row) if row else None

    def active_runs(self) -> List[ExpeditionRun]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM expedition_runs WHERE claimed=0 ORDER BY started_at").fetchall()
        return [self._row_to_run(r) for r in rows]

    def bind_status_message(self, run_id: str, channel_id: int, message_id: int):
        with self._connect() as conn:
            conn.execute(
                "UPDATE expedition_runs SET status_channel_id=?, status_message_id=? WHERE run_id=?",
                (int(channel_id), int(message_id), str(run_id)),
            )
            conn.commit()

    def reveal_due_events(self, run_id: str, now: int | None = None) -> List[dict]:
        now = int(time.time()) if now is None else int(now)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("""
                SELECT event_index,drop_at,resource_name,quantity
                FROM expedition_drop_events
                WHERE run_id=? AND revealed=0 AND drop_at<=?
                ORDER BY drop_at,event_index
            """, (str(run_id), now)).fetchall()
            if rows:
                conn.execute("""
                    UPDATE expedition_drop_events SET revealed=1,revealed_at=?
                    WHERE run_id=? AND revealed=0 AND drop_at<=?
                """, (now, str(run_id), now))
            conn.commit()
        return [dict(r) for r in rows]

    def revealed_loot(self, run_id: str) -> Dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT resource_name,SUM(quantity) AS qty
                FROM expedition_drop_events WHERE run_id=? AND revealed=1
                GROUP BY resource_name ORDER BY resource_name
            """, (str(run_id),)).fetchall()
        return {str(r["resource_name"]): int(r["qty"] or 0) for r in rows}

    def drop_log(self, run_id: str, limit: int = 8) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT event_index,drop_at,resource_name,quantity,revealed_at
                FROM expedition_drop_events
                WHERE run_id=? AND revealed=1
                ORDER BY drop_at DESC,event_index DESC LIMIT ?
            """, (str(run_id), max(1, int(limit)))).fetchall()
        return [dict(r) for r in reversed(rows)]

    def next_drop_at(self, run_id: str) -> int | None:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT MIN(drop_at) AS ts FROM expedition_drop_events
                WHERE run_id=? AND revealed=0
            """, (str(run_id),)).fetchone()
        return int(row["ts"]) if row and row["ts"] is not None else None


def generate_loot(expedition_key: str, tool_key: str, tool_level: int, capacity: int) -> Dict[str, int]:
    table = [entry for entry in LOOT_TABLES[expedition_key][tool_key] if tool_level >= entry[1]]
    if not table:
        return {}
    names = [x[0] for x in table]
    weights = [x[2] for x in table]
    loot: Dict[str, int] = {}
    # 1 tirage = 1 emplacement. Pas de remplacement automatique des communs par des rares.
    for _ in range(int(capacity)):
        name = random.choices(names, weights=weights, k=1)[0]
        loot[name] = loot.get(name, 0) + 1
    return loot


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"


def loot_lines(loot: Dict[str, int]) -> str:
    if not loot:
        return "Aucun loot."
    ordered = sorted(loot.items(), key=lambda kv: (-RARITY.get(kv[0],1), kv[0]))
    return "\n".join(f"{RARITY_EMOJI.get(RARITY.get(name,1),'⚪')} **{name}** ×{qty}" for name, qty in ordered)
