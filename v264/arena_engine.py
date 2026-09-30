from __future__ import annotations

import random
import sqlite3
from shared_economy import connect_shared
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from admin_engine import event_multiplier, cooldowns_enabled

ARENA_RANKS = [(0, "Bronze"), (500, "Argent"), (1200, "Or"), (2200, "Platine"), (3500, "Maître"), (5000, "Légende")]
CHAMPION_ACHIEVEMENT_LEVELS = {1:1, 3:2, 5:3, 7:4, 10:5}

CLASSES = {
    "ravageur": {
        "name": "Ravageur", "emoji": "🐯", "animal": "Tigre",
        "hp": 100, "attack": 1.15, "passive_reduction": 0.05, "evade": 0.05, "speed": 100,
        "skills": {
            "light": {"name": "Griffes vives", "emoji": "🐾", "power": 14, "accuracy": 1.0},
            "heavy": {"name": "Lacération", "emoji": "🩸", "power": 30, "accuracy": 0.70},
            "ultimate": {"name": "Fureur du Prédateur", "emoji": "🔥", "power": 36, "accuracy": 0.90},
            "defend": {"name": "Instinct sauvage", "emoji": "🐯"},
        },
    },
    "gardien": {
        "name": "Gardien", "emoji": "🐻", "animal": "Ours",
        "hp": 120, "attack": 0.92, "passive_reduction": 0.14, "evade": 0.03, "speed": 80,
        "skills": {
            "light": {"name": "Patte du Colosse", "emoji": "👊", "power": 14, "accuracy": 1.0},
            "heavy": {"name": "Fracas terrestre", "emoji": "💥", "power": 27, "accuracy": 0.68},
            "ultimate": {"name": "Courroux du Gardien", "emoji": "🌋", "power": 31, "accuracy": 0.95},
            "defend": {"name": "Forteresse", "emoji": "🛡️"},
        },
    },
    "traqueur": {
        "name": "Traqueur", "emoji": "🐺", "animal": "Loup",
        "hp": 95, "attack": 1.05, "passive_reduction": 0.05, "evade": 0.15, "speed": 120,
        "skills": {
            "light": {"name": "Croc éclair", "emoji": "⚡", "power": 13, "accuracy": 1.0},
            "heavy": {"name": "Assaut lunaire", "emoji": "🌙", "power": 26, "accuracy": 0.78},
            "ultimate": {"name": "Chasse Fantôme", "emoji": "🌑", "power": 31, "accuracy": 0.98},
            "defend": {"name": "Pas Fantôme", "emoji": "💨"},
        },
    },
}


# V1.63 — chaque Champion possède désormais une identité, une classe fixe et une stratégie.
CHAMPION_PROFILES = {
    1: {"name":"Rokhan le Croc", "class_key":"ravageur", "strategy":"aggressive", "style":"Attaquant frontal — privilégie les enchaînements rapides."},
    2: {"name":"Brom Mur-de-Fer", "class_key":"gardien", "strategy":"defensive", "style":"Défenseur patient — protège ses ouvertures avant de frapper."},
    3: {"name":"Lyss la Louve", "class_key":"traqueur", "strategy":"evasive", "style":"Traqueuse mobile — cherche l’esquive puis la punition."},
    4: {"name":"Kael Sang-Fauve", "class_key":"ravageur", "strategy":"combo", "style":"Ravageur technique — prépare ses grosses attaques avec Griffes vives."},
    5: {"name":"Doran l’Inébranlable", "class_key":"gardien", "strategy":"wall", "style":"Premier mur de l’Arène — défense lourde et contre-attaque."},
    6: {"name":"Nyra Cendrelune", "class_key":"traqueur", "strategy":"opportunist", "style":"Attend une faiblesse et déclenche son ultime au bon moment."},
    7: {"name":"Tharos le Rouge", "class_key":"ravageur", "strategy":"finisher", "style":"Très agressif quand l’adversaire passe sous 50 % PV."},
    8: {"name":"Ormund le Bastion", "class_key":"gardien", "strategy":"counter", "style":"Absorbe les gros impacts et cherche la riposte."},
    9: {"name":"Selka l’Ombre", "class_key":"traqueur", "strategy":"tactical", "style":"Change constamment de rythme et évite les choix prévisibles."},
    10:{"name":"Asterion, Roi de l’Arène", "class_key":"ravageur", "strategy":"boss", "style":"Boss final — offensif, patient et capable de finir un combat très vite."},
}

@dataclass
class Fighter:
    user_id: int | None
    name: str
    class_key: str
    hp: int = 0
    max_hp: int = 0
    ultimate_cd: int = 0
    defending: bool = False
    defend_reduction: float = 0.0
    temp_evade: float = 0.0
    next_damage_bonus: float = 0.0
    ravager_light_stacks: int = 0
    shaken: bool = False
    evaded_last_attack: bool = False
    counter_ready: bool = False
    bleed_pending: int = 0
    champion_level: int = 0
    equipment_hp_pct: float = 0.0
    equipment_atk_pct: float = 0.0
    equipment_def_pct: float = 0.0
    equipment_speed_pct: float = 0.0

    def __post_init__(self):
        cfg = CLASSES[self.class_key]
        if not self.max_hp:
            self.max_hp = cfg["hp"]
        if self.champion_level:
            # I→X : Champion X ≈ +25% PV, calibré face à un set légendaire complet.
            self.max_hp = round(self.max_hp * (1 + 0.028 * (self.champion_level - 1)))
        elif self.equipment_hp_pct:
            self.max_hp = round(self.max_hp * (1 + self.equipment_hp_pct / 100.0))
        if not self.hp:
            self.hp = self.max_hp

    @property
    def cfg(self):
        return CLASSES[self.class_key]

    @property
    def alive(self):
        return self.hp > 0

@dataclass
class BattleState:
    battle_id: str
    mode: str  # champion | friend
    wager: int
    fighters: list[Fighter]
    current: int
    turn_no: int = 1
    log: list[str] = field(default_factory=list)
    finished: bool = False
    winner_index: int | None = None
    message_id: int | None = None

    def actor(self) -> Fighter:
        return self.fighters[self.current]

    def target(self) -> Fighter:
        return self.fighters[1 - self.current]

    def switch(self):
        self.current = 1 - self.current
        self.turn_no += 1


def class_line(class_key: str) -> str:
    c = CLASSES[class_key]
    return f"{c['emoji']} **{c['name']}** — {c['animal']}"


def choose_first(a: Fighter, b: Fighter) -> int:
    sa = a.cfg["speed"] * (1 + (0.011 * (a.champion_level - 1) if a.champion_level else a.equipment_speed_pct / 100.0))
    sb = b.cfg["speed"] * (1 + (0.011 * (b.champion_level - 1) if b.champion_level else b.equipment_speed_pct / 100.0))
    if sa == sb:
        return random.randint(0, 1)
    # La vitesse favorise l'initiative sans la garantir à 100 %.
    chance_a = sa / (sa + sb)
    return 0 if random.random() < chance_a else 1


def _hit_roll(actor: Fighter, target: Fighter, action: str) -> tuple[bool, bool]:
    skill = actor.cfg["skills"][action]
    accuracy = skill.get("accuracy", 1.0)
    if action == "light":
        return True, False  # règle: l'attaque légère touche toujours
    if random.random() > accuracy:
        return False, False
    equip_evade = min(0.05, target.equipment_speed_pct / 200.0)
    evade = min(0.15, target.cfg["evade"] + target.temp_evade + equip_evade)
    if random.random() < evade:
        target.evaded_last_attack = True
        return False, True
    target.evaded_last_attack = False
    return True, False


def _compute_damage(actor: Fighter, target: Fighter, action: str) -> tuple[int, bool]:
    skill = actor.cfg["skills"][action]
    power = skill["power"]
    mult = actor.cfg["attack"]
    if actor.champion_level:
        mult *= 1 + 0.011 * (actor.champion_level - 1)
    else:
        mult *= 1 + actor.equipment_atk_pct / 100.0

    if actor.shaken:
        mult *= 0.90
        actor.shaken = False
    if actor.next_damage_bonus:
        mult *= 1 + actor.next_damage_bonus
        actor.next_damage_bonus = 0.0
    if actor.counter_ready:
        mult *= 1.15
        actor.counter_ready = False
    if actor.class_key == "traqueur" and action == "heavy" and actor.evaded_last_attack:
        mult *= 1.30
        actor.evaded_last_attack = False

    # petite variance pour garder le combat vivant sans le rendre chaotique
    raw = power * mult * random.uniform(0.94, 1.06)
    crit = action == "ultimate" and random.random() < 0.50
    if crit:
        raw *= 1.60

    reduction = target.cfg["passive_reduction"]
    if target.champion_level:
        reduction = min(0.30, reduction + 0.008 * (target.champion_level - 1))
    else:
        reduction = min(0.30, reduction + min(0.10, target.equipment_def_pct / 100.0))
    if action == "light" and actor.class_key == "gardien":
        reduction = max(0.0, reduction - 0.08)  # Patte du Colosse ignore 8 points de réduction
    if target.defending:
        reduction = 1 - (1 - reduction) * (1 - target.defend_reduction)

    dmg = max(1, round(raw * (1 - reduction)))
    return dmg, crit


def resolve_action(state: BattleState, action: str) -> list[str]:
    actor, target = state.actor(), state.target()
    lines: list[str] = []

    # Les dégâts de saignement arrivent au début du tour de la victime.
    if actor.bleed_pending > 0:
        bleed = actor.bleed_pending
        actor.bleed_pending = 0
        actor.hp = max(0, actor.hp - bleed)
        lines.append(f"🩸 {actor.name} subit **{bleed} dégâts** de saignement.")
        if not actor.alive:
            state.finished = True
            state.winner_index = 1 - state.current
            return lines

    # Le bonus d'esquive du tour précédent s'efface lorsque le joueur commence son nouveau tour.
    actor.temp_evade = 0.0

    if action == "defend":
        actor.defending = True
        if actor.class_key == "ravageur":
            actor.defend_reduction = 0.45
            actor.next_damage_bonus = max(actor.next_damage_bonus, 0.10)
            lines.append(f"🐯 **{actor.name}** adopte *Instinct sauvage* : forte garde + riposte renforcée.")
        elif actor.class_key == "gardien":
            actor.defend_reduction = 0.60
            lines.append(f"🛡️ **{actor.name}** érige *Forteresse* : énorme réduction sur le prochain impact.")
        else:
            actor.defend_reduction = 0.30
            actor.temp_evade = 0.35
            lines.append(f"💨 **{actor.name}** utilise *Pas Fantôme* : garde légère + forte esquive temporaire.")
    else:
        skill = actor.cfg["skills"][action]
        if action == "ultimate" and actor.ultimate_cd > 0:
            lines.append(f"⏳ L'ultime de **{actor.name}** recharge encore ({actor.ultimate_cd} tour(s)).")
            return lines

        hit, evaded = _hit_roll(actor, target, action)
        if not hit:
            if evaded:
                lines.append(f"💨 **{target.name} esquive {skill['name']}** !")
            else:
                lines.append(f"❌ **{actor.name} rate {skill['name']}**.")
        else:
            dmg, crit = _compute_damage(actor, target, action)
            target.hp = max(0, target.hp - dmg)
            crit_text = " 💥 **CRITIQUE !**" if crit else ""
            lines.append(f"{skill['emoji']} **{actor.name}** utilise **{skill['name']}** : **{dmg} dégâts**.{crit_text}")

            # Effets de classe
            if actor.class_key == "ravageur":
                if action == "light":
                    actor.ravager_light_stacks = min(2, actor.ravager_light_stacks + 1)
                    actor.next_damage_bonus = max(actor.next_damage_bonus, 0.05 * actor.ravager_light_stacks)
                elif action == "heavy":
                    target.bleed_pending = max(target.bleed_pending, 4)
                elif action == "ultimate" and crit:
                    actor.next_damage_bonus = max(actor.next_damage_bonus, 0.10)
            elif actor.class_key == "gardien":
                if action == "heavy":
                    target.shaken = True
                elif action == "ultimate":
                    actor.defending = True
                    actor.defend_reduction = max(actor.defend_reduction, 0.20)
            elif actor.class_key == "traqueur":
                if action == "light":
                    actor.temp_evade = max(actor.temp_evade, 0.10)
                elif action == "ultimate" and target.defending:
                    # Chasse Fantôme punit les gardes trop prévisibles.
                    bonus = max(1, round(dmg * 0.20))
                    target.hp = max(0, target.hp - bonus)
                    lines.append(f"🌑 *Chasse Fantôme* traverse la garde : **+{bonus} dégâts**.")

            # Une défense est consommée par le premier impact réellement reçu.
            if target.defending:
                if target.class_key == "gardien":
                    target.counter_ready = True
                target.defending = False
                target.defend_reduction = 0.0
                target.temp_evade = 0.0

        if action == "ultimate":
            actor.ultimate_cd = 2

    # Après une action normale, on réduit le cooldown posé lors de tours précédents.
    if action != "ultimate" and actor.ultimate_cd > 0:
        actor.ultimate_cd -= 1

    if not target.alive:
        state.finished = True
        state.winner_index = state.current
    return lines


def bot_choose_action(bot: Fighter, enemy: Fighter) -> str:
    """IA contextuelle. Les Champions I→X ont chacun un vrai profil tactique."""
    hp_ratio = bot.hp / max(1, bot.max_hp)
    enemy_ratio = enemy.hp / max(1, enemy.max_hp)
    strategy = CHAMPION_PROFILES.get(bot.champion_level, {}).get("strategy", "balanced")

    weights = {"light": 0.32, "heavy": 0.30, "defend": 0.18}
    if bot.ultimate_cd == 0:
        weights["ultimate"] = 0.22

    if strategy == "aggressive":
        weights["heavy"] *= 1.35; weights["defend"] *= 0.65
    elif strategy == "defensive":
        weights["defend"] *= 1.55
        if hp_ratio < .60: weights["defend"] *= 1.25
    elif strategy == "evasive":
        weights["light"] *= 1.35; weights["defend"] *= 1.20
    elif strategy == "combo":
        # Le Ravageur prépare Lacération / ultime avec ses stacks de Griffes vives.
        if bot.ravager_light_stacks < 2: weights["light"] *= 1.8
        else: weights["heavy"] *= 1.45
    elif strategy == "wall":
        weights["defend"] *= 2.0
        if enemy_ratio < .45 and bot.ultimate_cd == 0: weights["ultimate"] *= 1.7
    elif strategy == "opportunist":
        weights["light"] *= 1.25
        if enemy_ratio < .60 and bot.ultimate_cd == 0: weights["ultimate"] *= 2.0
    elif strategy == "finisher":
        if enemy_ratio < .50:
            weights["heavy"] *= 1.7
            if bot.ultimate_cd == 0: weights["ultimate"] *= 2.2
    elif strategy == "counter":
        weights["defend"] *= 1.75
        if bot.counter_ready: weights["heavy"] *= 1.6
    elif strategy == "tactical":
        if enemy.defending and bot.ultimate_cd == 0: weights["ultimate"] *= 2.1
        elif hp_ratio < .45: weights["defend"] *= 1.6
        else: weights["light"] *= 1.2; weights["heavy"] *= 1.2
    elif strategy == "boss":
        # Champion X : pas de spam aveugle. Il défend bas en PV et cherche l'exécution.
        weights["heavy"] *= 1.35
        if hp_ratio < .35: weights["defend"] *= 1.8
        if enemy_ratio < .65 and bot.ultimate_cd == 0: weights["ultimate"] *= 2.4

    if hp_ratio < 0.30:
        weights["defend"] *= 1.45
    if enemy_ratio < 0.30 and bot.ultimate_cd == 0:
        weights["ultimate"] *= 1.45

    choices=[(k,w) for k,w in weights.items() if w > 0 and not (k == "ultimate" and bot.ultimate_cd > 0)]
    total=sum(w for _,w in choices)
    r=random.random()*total; acc=0.0
    for action,weight in choices:
        acc += weight
        if r <= acc:
            return action
    return "light"


class ArenaStore:
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
                CREATE TABLE IF NOT EXISTS arena_daily (
                    user_id INTEGER NOT NULL,
                    day TEXT NOT NULL,
                    friend_fights INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(user_id, day)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS arena_champion (
                    user_id INTEGER PRIMARY KEY,
                    last_started_utc TEXT
                )
            """)
            conn.execute("""CREATE TABLE IF NOT EXISTS arena_progress (
                user_id INTEGER PRIMARY KEY,
                rating INTEGER NOT NULL DEFAULT 0,
                champion_wins INTEGER NOT NULL DEFAULT 0
            )""")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS arena_battles (
                    battle_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    p1 INTEGER NOT NULL,
                    p2 INTEGER,
                    wager INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    winner INTEGER,
                    created_utc TEXT NOT NULL
                )
            """)
            conn.commit()

    def _ensure_player(self, conn, user_id: int):
        conn.execute("INSERT OR IGNORE INTO players(user_id) VALUES (?)", (int(user_id),))

    def progress(self, user_id: int) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT rating,champion_wins FROM arena_progress WHERE user_id=?", (int(user_id),)).fetchone()
        rating = int(row["rating"]) if row else 0
        wins = int(row["champion_wins"]) if row else 0
        rank = "Bronze"
        for needed, label in ARENA_RANKS:
            if rating >= needed: rank = label
        return {"rating": rating, "rank": rank, "champion_wins": wins, "champion_level": min(10, wins + 1)}

    @staticmethod
    def _change_rating(conn, user_id: int, delta: int):
        conn.execute("INSERT OR IGNORE INTO arena_progress(user_id,rating,champion_wins) VALUES(?,0,0)", (int(user_id),))
        conn.execute("UPDATE arena_progress SET rating=MAX(0,rating+?) WHERE user_id=?", (int(delta), int(user_id)))

    def friend_remaining(self, user_id: int) -> int:
        day = datetime.now().date().isoformat()
        with self._connect() as conn:
            row = conn.execute("SELECT friend_fights FROM arena_daily WHERE user_id=? AND day=?", (int(user_id), day)).fetchone()
        return max(0, 3 - (int(row["friend_fights"]) if row else 0))

    def champion_remaining_seconds(self, user_id: int) -> int:
        if not cooldowns_enabled(self.db_path):
            return 0
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            row = conn.execute("SELECT last_started_utc FROM arena_champion WHERE user_id=?", (int(user_id),)).fetchone()
        if not row or not row["last_started_utc"]:
            return 0
        last = datetime.fromisoformat(row["last_started_utc"])
        elapsed = (now - last).total_seconds()
        return max(0, int(3600 - elapsed))

    def _has_active(self, conn, user_id: int) -> bool:
        row = conn.execute(
            "SELECT 1 FROM arena_battles WHERE status='active' AND (p1=? OR p2=?) LIMIT 1",
            (int(user_id), int(user_id)),
        ).fetchone()
        return row is not None

    def start_friend(self, p1: int, p2: int, wager: int) -> tuple[bool, str, str | None]:
        wager = max(0, min(500, int(wager)))
        day = datetime.now().date().isoformat()
        battle_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_player(conn, p1); self._ensure_player(conn, p2)
            if self._has_active(conn, p1) or self._has_active(conn, p2):
                conn.rollback(); return False, "Un des deux joueurs participe déjà à un combat.", None
            counts = {}
            for uid in (p1, p2):
                row = conn.execute("SELECT friend_fights FROM arena_daily WHERE user_id=? AND day=?", (int(uid), day)).fetchone()
                counts[uid] = int(row["friend_fights"]) if row else 0
                if counts[uid] >= 3:
                    conn.rollback(); return False, f"<@{uid}> a déjà utilisé ses 3 combats amicaux du jour.", None
            if wager > 0:
                for uid in (p1, p2):
                    wallet = conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (int(uid),)).fetchone()[0]
                    if wallet < wager:
                        conn.rollback(); return False, f"<@{uid}> n'a pas assez de Gold pour la mise de {wager}.", None
                conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id IN (?,?)", (wager, int(p1), int(p2)))
            for uid in (p1, p2):
                conn.execute("INSERT INTO arena_daily(user_id,day,friend_fights) VALUES(?,?,1) ON CONFLICT(user_id,day) DO UPDATE SET friend_fights=friend_fights+1", (int(uid), day))
            conn.execute("INSERT INTO arena_battles VALUES(?,?,?,?,?,'active',NULL,?)", (battle_id, "friend", int(p1), int(p2), wager, datetime.now(timezone.utc).isoformat()))
            conn.commit()
        return True, "Combat lancé.", battle_id

    def start_champion(self, user_id: int, wager: int) -> tuple[bool, str, str | None]:
        wager = max(0, min(500, int(wager)))
        now = datetime.now(timezone.utc)
        battle_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_player(conn, user_id)
            if self._has_active(conn, user_id):
                conn.rollback(); return False, "Tu participes déjà à un combat.", None
            if cooldowns_enabled(self.db_path):
                row = conn.execute("SELECT last_started_utc FROM arena_champion WHERE user_id=?", (int(user_id),)).fetchone()
                if row and row["last_started_utc"]:
                    last = datetime.fromisoformat(row["last_started_utc"])
                    remaining = int(3600 - (now - last).total_seconds())
                    if remaining > 0:
                        conn.rollback(); return False, f"Le Champion sera disponible dans {remaining//60} min {remaining%60:02d} s.", None
            wallet = conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (int(user_id),)).fetchone()[0]
            if wallet < wager:
                conn.rollback(); return False, f"Tu n'as pas assez de Gold pour miser {wager}.", None
            if wager > 0:
                conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?", (wager, int(user_id)))
            conn.execute("INSERT INTO arena_champion(user_id,last_started_utc) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET last_started_utc=excluded.last_started_utc", (int(user_id), now.isoformat()))
            conn.execute("INSERT INTO arena_battles VALUES(?,?,?,?,?,'active',NULL,?)", (battle_id, "champion", int(user_id), None, wager, now.isoformat()))
            conn.commit()
        return True, "Combat lancé.", battle_id

    def finish(self, battle_id: str, winner_user_id: int | None) -> tuple[bool, int]:
        """Retourne (paiement_effectué, montant_crédité). Idempotent."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM arena_battles WHERE battle_id=?", (battle_id,)).fetchone()
            if not row or row["status"] != "active":
                conn.rollback(); return False, 0
            wager = int(row["wager"])
            payout = 0
            if winner_user_id is not None:
                self._ensure_player(conn, winner_user_id)
                if row["mode"] == "friend":
                    payout = wager * 2
                elif row["mode"] == "champion" and int(row["p1"]) == int(winner_user_id):
                    # Le x2 Gold double le bénéfice du Champion, pas la mise rendue.
                    payout = wager + wager * event_multiplier(self.db_path, 'gold_x2')
                if payout:
                    conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (payout, int(winner_user_id)))
            # Classement d'Arène : chaque combat terminé fait gagner/perdre des points.
            p1, p2 = int(row["p1"]), (int(row["p2"]) if row["p2"] is not None else None)
            if row["mode"] == "friend" and winner_user_id is not None and p2 is not None:
                loser = p2 if int(winner_user_id) == p1 else p1
                self._change_rating(conn, int(winner_user_id), +25)
                self._change_rating(conn, loser, -15)
            elif row["mode"] == "champion":
                if winner_user_id is not None and int(winner_user_id) == p1:
                    self._change_rating(conn, p1, +30)
                    conn.execute("INSERT OR IGNORE INTO arena_progress(user_id,rating,champion_wins) VALUES(?,0,0)", (p1,))
                    conn.execute("UPDATE arena_progress SET champion_wins=MIN(10,champion_wins+1) WHERE user_id=?", (p1,))
                else:
                    self._change_rating(conn, p1, -10)
            conn.execute("UPDATE arena_battles SET status='finished', winner=? WHERE battle_id=?", (winner_user_id, battle_id))
            conn.commit()
        return True, payout

    def recover_unfinished(self) -> int:
        """En cas de redémarrage du bot, rembourse les mises des combats interrompus."""
        recovered = 0
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT * FROM arena_battles WHERE status='active'").fetchall()
            for row in rows:
                wager = int(row["wager"])
                if wager > 0:
                    self._ensure_player(conn, int(row["p1"]))
                    conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (wager, int(row["p1"])))
                    if row["mode"] == "friend" and row["p2"] is not None:
                        self._ensure_player(conn, int(row["p2"]))
                        conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (wager, int(row["p2"])))
                conn.execute("UPDATE arena_battles SET status='cancelled' WHERE battle_id=?", (row["battle_id"],))
                recovered += 1
            conn.commit()
        return recovered
