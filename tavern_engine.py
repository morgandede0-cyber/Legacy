from __future__ import annotations

import random
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from admin_engine import event_multiplier, cooldowns_enabled

MIN_TAVERN_BET = 1
MAX_TAVERN_BET = 500

TAVERN_REPUTATION_TIERS = [
    (5, "Client discret"),
    (25, "Habitué du comptoir"),
    (75, "Pilier de taverne"),
    (150, "Ivrogne notoire"),
    (300, "Alcoolique du coin"),
]
TAVERN_DRINK_COOLDOWN = 60 * 60
# V1.57 — la limite quotidienne dépend désormais de la réputation de Taverne.
TAVERN_DAILY_LIMITS = {0: 2, 1: 3, 2: 4, 3: 5, 4: 6, 5: 8}
TAVERN_ROUND_COST = 300

# V1.57 — Ivresse narrative. Aucun bonus de statistiques : boire ouvre des scènes,
# des conséquences, des secrets et des objets mystérieux.
DRUNK_STATES = [
    (0, "Sobre"), (1, "Détendu"), (2, "Pompette"), (3, "Éméché"),
    (4, "Ivre"), (5, "Bien bourré"), (6, "Complètement bourré"),
    (7, "Catastrophique"), (8, "Mais qu'est-ce que j'ai foutu hier soir ?"),
]

# Le type de boisson favorise seulement une famille d'événements. Les probabilités
# exactes restent volontairement invisibles aux joueurs.
DRINK_FAVORED_CATEGORIES = {
    "beer": "social", "cider": "fun", "mead": "challenge",
    "red_wine": "secret", "spiced_rum": "alley", "whisky": "chaos",
}

# 36 scènes, dont 12 servent de déclencheurs aux 2 succès secrets de chacun des 6 paliers.
# min_tier = réputation minimale, min_drinks = ivresse minimale du jour.
DRUNK_EVENTS = [
    # Sobre / nouveau
    {"id":"floor_bed","cat":"fun","min_tier":0,"min_drinks":2,"weight":9,"title":"🪑 Le sol avait l'air confortable","text":"Tu clignes des yeux... et réalises que tu viens de passer plusieurs minutes allongé sous une table. Personne ne t'explique pourquoi.","achievement":"tavern_secret:0:1"},
    {"id":"not_my_pretzel","cat":"social","min_tier":0,"min_drinks":2,"weight":9,"title":"🥨 C'était pas à moi ?","text":"Tu termines fièrement un énorme bretzel. Le silence autour de toi devient étrange. Il appartenait au mercenaire assis juste derrière.","achievement":"tavern_secret:0:2"},
    {"id":"wrong_toast","cat":"social","min_tier":0,"min_drinks":1,"weight":14,"title":"🍻 Santé... à qui déjà ?","text":"Tu portes un toast passionné à quelqu'un dont tu as oublié le nom avant même la fin de ta phrase."},
    {"id":"chair_duel","cat":"fun","min_tier":0,"min_drinks":2,"weight":12,"title":"🪑 Duel contre une chaise","text":"La chaise a gagné. Personne ne semble surpris."},
    {"id":"coin_floor","cat":"fun","min_tier":0,"min_drinks":2,"weight":7,"title":"🪙 Coup de chance","text":"En cherchant ton équilibre, tu trouves quelques Gold sous une table.","gold":18},
    {"id":"bad_tip","cat":"fun","min_tier":0,"min_drinks":2,"weight":7,"title":"💸 Pourboire généreux","text":"Tu laisses un pourboire beaucoup trop enthousiaste au Tavernier.","gold":-12},
    # Client discret
    {"id":"why_chicken","cat":"fun","min_tier":1,"min_drinks":3,"weight":6,"title":"🐔 Pourquoi j'ai une poule ?","text":"Une poule te suit depuis plusieurs minutes. Le plus inquiétant : elle répond quand tu l'appelles « Gérard ».","item":"Poule nommée Gérard","achievement":"tavern_secret:1:1"},
    {"id":"wrong_shoe","cat":"fun","min_tier":1,"min_drinks":3,"weight":6,"title":"👞 C'est pas ma chaussure","text":"Tu regardes tes pieds. Deux chaussures. Deux tailles différentes. Deux propriétaires probablement différents.","item":"Chaussure inconnue","achievement":"tavern_secret:1:2"},
    {"id":"new_best_friend","cat":"social","min_tier":1,"min_drinks":2,"weight":12,"title":"🤝 Meilleur ami depuis 4 minutes","text":"Tu jures fidélité éternelle à un client que tu viens de rencontrer. Vous oubliez vos prénoms presque immédiatement."},
    {"id":"tavern_debt","cat":"social","min_tier":1,"min_drinks":3,"weight":7,"title":"🧾 Une petite dette","text":"Le Tavernier te montre une ardoise. Ton écriture est dessus. Tu n'as aucun souvenir de l'avoir signée."},
    {"id":"lucky_pouch","cat":"social","min_tier":1,"min_drinks":3,"weight":6,"title":"👝 Une bourse sous le banc","text":"Une petite bourse oubliée glisse jusqu'à tes pieds. Personne ne la réclame.","gold":32},
    {"id":"napkin_map","cat":"secret","min_tier":1,"min_drinks":3,"weight":4,"title":"🗺️ Une carte sur une serviette","text":"Quelqu'un a dessiné un plan incompréhensible sur une serviette. Un X rouge est entouré trois fois.","item":"Serviette cartographiée"},
    # Habitué
    {"id":"short_career","cat":"social","min_tier":2,"min_drinks":4,"weight":5,"title":"🎤 Une carrière très courte","text":"Tu prends le luth du Troubadour et annonces ton premier concert. Ton dernier concert a lieu environ quarante secondes plus tard.","achievement":"tavern_secret:2:1"},
    {"id":"ring_what","cat":"secret","min_tier":2,"min_drinks":4,"weight":4,"title":"💍 J'ai fait QUOI ?!","text":"Une bague inconnue est passée à ton doigt. Le Tavernier refuse catégoriquement de répondre à tes questions.","item":"Bague sans propriétaire","achievement":"tavern_secret:2:2"},
    {"id":"arm_wrestle","cat":"challenge","min_tier":2,"min_drinks":3,"weight":9,"title":"💪 Mauvaise idée, excellent souvenir","text":"Tu provoques un bûcheron au bras de fer. Il accepte. Ton bras regrette immédiatement la décision."},
    {"id":"free_round_memory","cat":"social","min_tier":2,"min_drinks":4,"weight":6,"title":"🍻 C'est moi qui régale ?","text":"Tout le comptoir t'applaudit. Apparemment tu avais promis de payer quelque chose. Tu décides de ne pas poser de question.","gold":-35},
    {"id":"old_coin","cat":"secret","min_tier":2,"min_drinks":4,"weight":4,"title":"🪙 Une monnaie qui n'existe plus","text":"Un vieil habitué te glisse une pièce frappée d'un blason inconnu puis disparaît dans la foule.","item":"Ancienne pièce de Legacy"},
    {"id":"dice_luck","cat":"challenge","min_tier":2,"min_drinks":4,"weight":5,"title":"🎲 Tu ne sais même pas à quoi tu jouais","text":"Quelqu'un te félicite pour ta victoire aux dés et te donne ta part.","gold":48},
    # Pilier
    {"id":"horse_judges","cat":"chaos","min_tier":3,"min_drinks":5,"weight":4,"title":"🐴 Il juge mes choix de vie","text":"Tu te réveilles dans une écurie. Un cheval te fixe avec une déception si profonde que tu t'excuses spontanément.","achievement":"tavern_secret:3:1"},
    {"id":"door_not_there","cat":"secret","min_tier":3,"min_drinks":5,"weight":3,"title":"🚪 Cette porte n'était pas là hier","text":"Au fond d'un couloir que tu ne te souviens pas avoir emprunté, tu aperçois une vieille porte sans poignée. Quand tu clignes des yeux, elle a disparu.","item":"Souvenir de la porte","achievement":"tavern_secret:3:2"},
    {"id":"alley_wakeup","cat":"alley","min_tier":3,"min_drinks":5,"weight":6,"title":"🌑 Mauvais chemin","text":"Tu reprends tes esprits à l'entrée de la Ruelle Sombre. Tu avais pourtant juré être parti dans l'autre direction."},
    {"id":"mysterious_note","cat":"secret","min_tier":3,"min_drinks":5,"weight":4,"title":"📜 Ne fais confiance à personne","text":"Un papier plié est dans ta poche : « Quand la cloche sonnera trois fois, regarde sous la pierre fendue. »","item":"Note chiffonnée"},
    {"id":"broken_stool","cat":"challenge","min_tier":3,"min_drinks":5,"weight":6,"title":"🪑 Le tabouret n'a pas survécu","text":"Le Tavernier te présente les restes d'un tabouret. Tu paies les dégâts sans demander la version complète.","gold":-45},
    {"id":"strange_bet","cat":"challenge","min_tier":3,"min_drinks":5,"weight":4,"title":"🎲 Le pari impossible","text":"Tu ne sais plus ce que tu avais parié, mais quelqu'un te remet une petite récompense avec un respect inquiétant.","gold":62},
    # Ivrogne notoire
    {"id":"your_majesty","cat":"chaos","min_tier":4,"min_drinks":6,"weight":3,"title":"👑 Votre Majesté...","text":"Tu viens de tenir une conversation diplomatique extrêmement sérieuse avec une statue. Tu l'as même laissée gagner le débat.","achievement":"tavern_secret:4:1"},
    {"id":"technically_alive","cat":"chaos","min_tier":4,"min_drinks":6,"weight":3,"title":"⚰️ Techniquement, je suis vivant","text":"Tu ouvres les yeux dans un cercueil vide entreposé derrière une échoppe. Une étiquette indique : « Réservé ». Tu préfères partir.","achievement":"tavern_secret:4:2"},
    {"id":"someone_pouch","cat":"alley","min_tier":4,"min_drinks":6,"weight":5,"title":"👝 Cette bourse n'est clairement pas à toi","text":"Tu trouves une bourse pleine dans ta veste. Quelqu'un, quelque part, doit être très énervé.","gold":73},
    {"id":"wolf_mark","cat":"alley","min_tier":4,"min_drinks":6,"weight":3,"title":"🐺 La marque du loup","text":"Un symbole de loup a été tracé sur ton poignet à l'encre noire. Il ne part pas avec de l'eau.","item":"Marque du loup"},
    {"id":"barrel_passenger","cat":"chaos","min_tier":4,"min_drinks":6,"weight":4,"title":"🛢️ Voyage en première classe","text":"Tu te réveilles assis dans un tonneau. Le tonneau se trouve à cinquante mètres de la Taverne. Belle performance."},
    {"id":"unknown_tab","cat":"social","min_tier":4,"min_drinks":6,"weight":4,"title":"🧾 Qui a commandé tout ça ?","text":"L'addition porte ton nom. La moitié des commandes ne te dit absolument rien."},
    # Alcoolique du coin
    {"id":"no_memory_key","cat":"secret","min_tier":5,"min_drinks":7,"weight":2,"title":"🗝️ Aucun souvenir","text":"Tu reprends conscience avec une clé noire et froide posée devant toi. Le Tavernier détourne immédiatement le regard.","item":"Clé sans nom","achievement":"tavern_secret:5:1","legendary":True},
    {"id":"never_again","cat":"chaos","min_tier":5,"min_drinks":8,"weight":2,"title":"💀 Plus jamais.","text":"Boue sur les bottes. Une plume dans les cheveux. Une dette griffonnée sur ton bras. Une cloche miniature dans ta poche. Tu murmures « plus jamais »... devant une nouvelle chope.","item":"Clochette miniature","achievement":"tavern_secret:5:2","legendary":True},
    {"id":"nameless_letter","cat":"secret","min_tier":5,"min_drinks":7,"weight":2,"title":"✉️ La lettre sans destinataire","text":"Une enveloppe scellée porte seulement ces mots : « Tu sauras quand l'ouvrir. »","item":"Lettre scellée"},
    {"id":"roof_wakeup","cat":"chaos","min_tier":5,"min_drinks":7,"weight":3,"title":"🏠 Comment je suis monté là ?","text":"Tu reprends tes esprits sur un toit, enlacé à une girouette. La question de la descente devient soudain prioritaire."},
    {"id":"three_lands_token","cat":"secret","min_tier":5,"min_drinks":8,"weight":1,"title":"🌒 Le jeton des Trois Terres","text":"Un jeton en métal sombre est dans ta paume. Trois royaumes y sont gravés, mais aucun artisan du coin ne reconnaît l'objet.","item":"Jeton des Trois Terres","legendary":True},
    {"id":"legendary_tip","cat":"chaos","min_tier":5,"min_drinks":8,"weight":2,"title":"💰 Le matin est parfois généreux","text":"Tu ne sais pas ce que tu as fait cette nuit, mais quelqu'un a glissé une belle somme dans ta poche avec le mot « pour services rendus ».","gold":110,"legendary":True},
]


class TavernGameStore:
    """Transactions atomiques pour les jeux de la taverne."""
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
                CREATE TABLE IF NOT EXISTS players (
                    user_id INTEGER PRIMARY KEY,
                    wallet_gold INTEGER NOT NULL DEFAULT 0 CHECK(wallet_gold >= 0),
                    bank_gold INTEGER NOT NULL DEFAULT 0 CHECK(bank_gold >= 0),
                    last_withdrawal_date TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tavern_sessions (
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tavern_user_status ON tavern_sessions(user_id,status)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tavern_pvp_sessions (
                    session_id TEXT PRIMARY KEY,
                    challenger_id INTEGER NOT NULL,
                    opponent_id INTEGER NOT NULL,
                    game_type TEXT NOT NULL,
                    wager INTEGER NOT NULL CHECK(wager > 0),
                    status TEXT NOT NULL DEFAULT 'pending',
                    winner_id INTEGER,
                    created_at INTEGER NOT NULL,
                    finished_at INTEGER
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tavern_pvp_status ON tavern_pvp_sessions(status)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tavern_reputation (
                    user_id INTEGER PRIMARY KEY,
                    drinks INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tavern_drink_limits (
                    user_id INTEGER PRIMARY KEY,
                    day TEXT NOT NULL,
                    drinks_today INTEGER NOT NULL DEFAULT 0,
                    last_drink_at INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tavern_rounds (
                    user_id INTEGER PRIMARY KEY,
                    rounds INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tavern_drunk_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    drink_key TEXT NOT NULL,
                    drunkenness INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tavern_mystery_items (
                    user_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    obtained_at INTEGER NOT NULL,
                    PRIMARY KEY(user_id, item_name)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tavern_delayed_consequences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    consequence_key TEXT NOT NULL,
                    source_event_id TEXT NOT NULL,
                    target_place TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    available_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    payload TEXT,
                    created_at INTEGER NOT NULL,
                    resolved_at INTEGER
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tavern_delayed_user_place ON tavern_delayed_consequences(user_id,target_place,status,available_at)")
            conn.commit()

    @staticmethod
    def _ensure_player(conn, user_id: int):
        conn.execute("INSERT OR IGNORE INTO players(user_id) VALUES (?)", (int(user_id),))

    @staticmethod
    def _reputation_from_drinks(drinks: int) -> tuple[int, str]:
        tier, label = 0, "Sobre"
        for i, (needed, name) in enumerate(TAVERN_REPUTATION_TIERS, 1):
            if drinks >= needed:
                tier, label = i, name
        return tier, label

    def tavern_reputation(self, user_id: int) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT drinks FROM tavern_reputation WHERE user_id=?", (int(user_id),)).fetchone()
        drinks = int(row[0]) if row else 0
        tier, label = self._reputation_from_drinks(drinks)
        next_at = TAVERN_REPUTATION_TIERS[tier][0] if tier < len(TAVERN_REPUTATION_TIERS) else None
        return {"drinks": drinks, "tier": tier, "label": label, "next_at": next_at}

    def daily_drink_limit(self, user_id: int) -> int:
        rep = self.tavern_reputation(user_id)
        return int(TAVERN_DAILY_LIMITS.get(int(rep["tier"]), 2))

    @staticmethod
    def drunk_state(drinks_today: int) -> str:
        drinks_today = max(0, int(drinks_today))
        for threshold, label in reversed(DRUNK_STATES):
            if drinks_today >= threshold:
                return label
        return "Sobre"

    @staticmethod
    def _event_chance(drinks_today: int) -> float:
        # Les valeurs ne sont jamais affichées côté joueur.
        return {1:0.10, 2:0.18, 3:0.28, 4:0.40, 5:0.52, 6:0.65, 7:0.78, 8:0.90}.get(int(drinks_today), 0.90)

    def _roll_drunk_event(self, tier: int, drinks_today: int, drink_key: str) -> dict | None:
        if random.random() > self._event_chance(drinks_today):
            return None
        pool = [e for e in DRUNK_EVENTS if int(e["min_tier"]) <= int(tier) and int(e["min_drinks"]) <= int(drinks_today)]
        if not pool:
            return None
        favored = DRINK_FAVORED_CATEGORIES.get(str(drink_key), "fun")
        weights = [int(e.get("weight", 1)) * (3 if e.get("cat") == favored else 1) for e in pool]
        return dict(random.choices(pool, weights=weights, k=1)[0])

    def mystery_items(self, user_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT item_name,quantity FROM tavern_mystery_items WHERE user_id=? ORDER BY obtained_at", (int(user_id),)).fetchall()
        return [{"name": str(r["item_name"]), "quantity": int(r["quantity"])} for r in rows]

    def tavern_rounds(self, user_id: int) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT rounds FROM tavern_rounds WHERE user_id=?", (int(user_id),)).fetchone()
        return int(row[0]) if row else 0

    def buy_round(self, user_id: int) -> dict:
        user_id = int(user_id)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_player(conn, user_id)
            wallet = int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (user_id,)).fetchone()[0])
            if wallet < TAVERN_ROUND_COST:
                conn.rollback()
                return {"ok": False, "message": f"Une tournée coûte {TAVERN_ROUND_COST} Gold. Tu n'as que {wallet} Gold."}
            conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?", (TAVERN_ROUND_COST, user_id))
            conn.execute("""INSERT INTO tavern_rounds(user_id,rounds) VALUES(?,1)
                         ON CONFLICT(user_id) DO UPDATE SET rounds=rounds+1""", (user_id,))
            rounds = int(conn.execute("SELECT rounds FROM tavern_rounds WHERE user_id=?", (user_id,)).fetchone()[0])
            conn.commit()
        return {"ok": True, "rounds": rounds, "cost": TAVERN_ROUND_COST, "wallet": wallet-TAVERN_ROUND_COST}

    def drink_status(self, user_id: int) -> dict:
        """Retourne l'état du service d'alcool pour aujourd'hui (heure locale du serveur)."""
        user_id = int(user_id)
        today = datetime.now().date().isoformat()
        now = int(time.time())
        daily_limit = self.daily_drink_limit(user_id)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT day,drinks_today,last_drink_at FROM tavern_drink_limits WHERE user_id=?",
                (user_id,),
            ).fetchone()
        if not row or str(row["day"]) != today:
            return {"drinks_today": 0, "remaining_today": daily_limit, "cooldown_seconds": 0, "daily_limit": False, "limit": daily_limit}
        drinks_today = int(row["drinks_today"] or 0)
        last_drink_at = int(row["last_drink_at"] or 0)
        cooldown = 0
        if cooldowns_enabled(self.db_path) and last_drink_at:
            cooldown = max(0, TAVERN_DRINK_COOLDOWN - (now - last_drink_at))
        return {
            "drinks_today": drinks_today,
            "remaining_today": max(0, daily_limit - drinks_today),
            "cooldown_seconds": cooldown,
            "daily_limit": drinks_today >= daily_limit,
            "limit": daily_limit,
        }

    def drink(self, user_id: int, drink_key: str = "beer") -> dict:
        """Boit un verre si le cooldown et la limite journalière l'autorisent. Transaction atomique."""
        user_id = int(user_id)
        today = datetime.now().date().isoformat()
        now = int(time.time())
        daily_limit = self.daily_drink_limit(user_id)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT day,drinks_today,last_drink_at FROM tavern_drink_limits WHERE user_id=?",
                (user_id,),
            ).fetchone()
            drinks_today = 0
            last_drink_at = 0
            if row and str(row["day"]) == today:
                drinks_today = int(row["drinks_today"] or 0)
                last_drink_at = int(row["last_drink_at"] or 0)

            if drinks_today >= daily_limit:
                conn.rollback()
                return {"ok": False, "reason": "daily_limit", "drinks_today": drinks_today, "remaining_today": 0}

            if cooldowns_enabled(self.db_path) and last_drink_at:
                remaining = TAVERN_DRINK_COOLDOWN - (now - last_drink_at)
                if remaining > 0:
                    conn.rollback()
                    return {"ok": False, "reason": "cooldown", "cooldown_seconds": int(remaining), "drinks_today": drinks_today, "remaining_today": daily_limit - drinks_today, "limit": daily_limit}

            conn.execute(
                """INSERT INTO tavern_drink_limits(user_id,day,drinks_today,last_drink_at) VALUES(?,?,1,?)
                   ON CONFLICT(user_id) DO UPDATE SET day=excluded.day,
                       drinks_today=CASE WHEN tavern_drink_limits.day=excluded.day THEN tavern_drink_limits.drinks_today+1 ELSE 1 END,
                       last_drink_at=excluded.last_drink_at""",
                (user_id, today, now),
            )
            conn.execute(
                """INSERT INTO tavern_reputation(user_id,drinks) VALUES(?,1)
                   ON CONFLICT(user_id) DO UPDATE SET drinks=drinks+1""",
                (user_id,),
            )
            rep_row = conn.execute("SELECT drinks FROM tavern_reputation WHERE user_id=?", (user_id,)).fetchone()
            lim_row = conn.execute("SELECT drinks_today FROM tavern_drink_limits WHERE user_id=?", (user_id,)).fetchone()
            drinks = int(rep_row[0])
            drinks_today = int(lim_row[0])
            tier, label = self._reputation_from_drinks(drinks)
            # Si ce verre fait franchir un palier, la nouvelle limite est active immédiatement.
            daily_limit = int(TAVERN_DAILY_LIMITS.get(tier, daily_limit))
            event = self._roll_drunk_event(tier, drinks_today, drink_key)
            if event:
                self._ensure_player(conn, user_id)
                if event.get("gold"):
                    wallet = int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (user_id,)).fetchone()[0])
                    requested = int(event["gold"])
                    actual = requested if requested >= 0 else -min(wallet, abs(requested))
                    conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (actual, user_id))
                    event["gold_actual"] = actual
                if event.get("item"):
                    conn.execute("""INSERT INTO tavern_mystery_items(user_id,item_name,quantity,obtained_at) VALUES(?,?,1,?)
                                  ON CONFLICT(user_id,item_name) DO UPDATE SET quantity=quantity+1, obtained_at=excluded.obtained_at""",
                                 (user_id, str(event["item"]), now))
                conn.execute("INSERT INTO tavern_drunk_events(user_id,event_id,drink_key,drunkenness,created_at) VALUES(?,?,?,?,?)",
                             (user_id, str(event["id"]), str(drink_key), drinks_today, now))
            conn.commit()
        # La conséquence naît uniquement d'une scène d'alcool existante.
        if event:
            self.schedule_delayed_from_event(user_id, str(event.get("id", "")))

        return {
            "ok": True, "drinks": drinks, "tier": tier, "label": label,
            "drinks_today": drinks_today, "drunk_state": self.drunk_state(drinks_today),
            "remaining_today": max(0, daily_limit - drinks_today), "limit": daily_limit,
            "event": event,
        }

    # V1.59 — conséquences différées exclusivement créées par les scènes d'ivresse.
    DELAYED_BY_EVENT = {
        "why_chicken": ("gerard_owner", "market", 6*3600, 5*24*3600),
        "tavern_debt": ("merchant_debt", "market", 8*3600, 7*24*3600),
        "ring_what": ("ring_recognized", "market", 10*3600, 8*24*3600),
        "arm_wrestle": ("arm_rematch", "tavern", 6*3600, 6*24*3600),
        "horse_judges": ("stable_remembers", "expeditions", 12*3600, 8*24*3600),
        "someone_pouch": ("pouch_owner", "market", 8*3600, 7*24*3600),
        "unknown_tab": ("tavern_bill", "tavern", 8*3600, 7*24*3600),
        "wolf_mark": ("wolf_mark", "alley", 12*3600, 10*24*3600),
        "no_memory_key": ("nameless_key", "alley", 18*3600, 14*24*3600),
        "never_again": ("they_waited", "tavern", 18*3600, 10*24*3600),
    }

    def schedule_delayed_from_event(self, user_id: int, event_id: str) -> bool:
        spec = self.DELAYED_BY_EVENT.get(str(event_id))
        if not spec:
            return False
        key, place, min_delay, ttl = spec
        now = int(time.time())
        # Une scène déjà en attente ne se duplique jamais.
        with self._connect() as conn:
            exists = conn.execute("SELECT 1 FROM tavern_delayed_consequences WHERE user_id=? AND consequence_key=? AND status='pending' LIMIT 1", (int(user_id), key)).fetchone()
            if exists:
                return False
            # Fenêtre volontairement imprévisible : entre le délai mini et ~2,5 jours.
            available = now + random.randint(int(min_delay), int(min_delay + 54*3600))
            expires = available + int(ttl)
            conn.execute("INSERT INTO tavern_delayed_consequences(user_id,consequence_key,source_event_id,target_place,status,available_at,expires_at,payload,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                         (int(user_id), key, str(event_id), place, 'pending', available, expires, '{}', now))
            conn.commit()
        return True

    def pending_consequence(self, user_id: int, target_place: str) -> dict | None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("UPDATE tavern_delayed_consequences SET status='expired', resolved_at=? WHERE user_id=? AND status='pending' AND expires_at<?", (now, int(user_id), now))
            row = conn.execute("SELECT * FROM tavern_delayed_consequences WHERE user_id=? AND target_place=? AND status='pending' AND available_at<=? AND expires_at>=? ORDER BY available_at,id LIMIT 1",
                               (int(user_id), str(target_place), now, now)).fetchone()
            conn.commit()
        return dict(row) if row else None

    def resolve_consequence(self, consequence_id: int, user_id: int, status: str='resolved') -> bool:
        now = int(time.time())
        with self._connect() as conn:
            cur = conn.execute("UPDATE tavern_delayed_consequences SET status=?, resolved_at=? WHERE id=? AND user_id=? AND status='pending'",
                               (str(status), now, int(consequence_id), int(user_id)))
            conn.commit()
            return cur.rowcount > 0

    def charge_wallet(self, user_id: int, amount: int) -> int:
        amount=max(0,int(amount))
        with self._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            self._ensure_player(conn,user_id)
            wallet=int(conn.execute('SELECT wallet_gold FROM players WHERE user_id=?',(int(user_id),)).fetchone()[0])
            paid=min(wallet,amount)
            conn.execute('UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?',(paid,int(user_id)))
            conn.commit()
        return paid

    def wallet(self, user_id: int) -> int:
        with self._connect() as conn:
            self._ensure_player(conn, user_id)
            row = conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (int(user_id),)).fetchone()
            conn.commit()
            return int(row[0])

    def start(self, user_id: int, game_type: str, wager: int) -> dict:
        try:
            wager = int(wager)
        except (TypeError, ValueError):
            return {"ok": False, "message": "La mise doit être un nombre entier."}
        if not MIN_TAVERN_BET <= wager <= MAX_TAVERN_BET:
            return {"ok": False, "message": f"La mise doit être comprise entre {MIN_TAVERN_BET} et {MAX_TAVERN_BET} Gold."}
        sid = uuid.uuid4().hex
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_player(conn, user_id)
            wallet = int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (int(user_id),)).fetchone()[0])
            if wallet < wager:
                conn.rollback()
                return {"ok": False, "message": f"Tu n'as que {wallet} Gold sur toi. Mise demandée : {wager} Gold."}
            conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?", (wager, int(user_id)))
            conn.execute("INSERT INTO tavern_sessions(session_id,user_id,game_type,wager,status,created_at) VALUES (?,?,?,?,?,?)",
                         (sid, int(user_id), str(game_type), wager, "active", now))
            conn.commit()
        return {"ok": True, "session_id": sid, "wager": wager, "wallet_after": wallet-wager}

    def settle(self, session_id: str, payout: int, status: str = "finished") -> dict:
        payout = max(0, int(payout))
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tavern_sessions WHERE session_id=?", (str(session_id),)).fetchone()
            if not row:
                conn.rollback(); return {"ok": False, "message": "Partie introuvable."}
            if str(row["status"]) != "active":
                conn.rollback(); return {"ok": False, "message": "Cette partie est déjà terminée.", "already": True}
            user_id, wager = int(row["user_id"]), int(row["wager"])
            if payout > wager:
                payout = wager + (payout-wager) * event_multiplier(self.db_path, "gold_x2")
            self._ensure_player(conn, user_id)
            if payout:
                conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (payout, user_id))
            conn.execute("UPDATE tavern_sessions SET status=?,payout=?,finished_at=? WHERE session_id=?",
                         (status,payout,now,str(session_id)))
            wallet = int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (user_id,)).fetchone()[0])
            conn.commit()
        return {"ok": True, "payout": payout, "wager": wager, "wallet": wallet, "user_id": user_id}

    def refund(self, session_id: str) -> dict:
        with self._connect() as conn:
            row = conn.execute("SELECT wager FROM tavern_sessions WHERE session_id=? AND status='active'", (str(session_id),)).fetchone()
        if not row:
            return {"ok": False}
        return self.settle(session_id, int(row["wager"]), status="refunded")

    def pvp_create(self, challenger_id: int, opponent_id: int, game_type: str, wager: int) -> dict:
        try:
            wager = int(wager)
        except (TypeError, ValueError):
            return {"ok": False, "message": "La mise doit être un nombre entier."}
        challenger_id, opponent_id = int(challenger_id), int(opponent_id)
        if challenger_id == opponent_id:
            return {"ok": False, "message": "Tu ne peux pas te défier toi-même."}
        if not MIN_TAVERN_BET <= wager <= MAX_TAVERN_BET:
            return {"ok": False, "message": f"La mise doit être comprise entre {MIN_TAVERN_BET} et {MAX_TAVERN_BET} Gold."}
        sid = uuid.uuid4().hex
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._ensure_player(conn, challenger_id)
            wallet = int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (challenger_id,)).fetchone()[0])
            if wallet < wager:
                conn.rollback()
                return {"ok": False, "message": f"Tu n'as que {wallet} Gold sur toi. Mise demandée : {wager} Gold."}
            conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?", (wager, challenger_id))
            conn.execute("INSERT INTO tavern_pvp_sessions(session_id,challenger_id,opponent_id,game_type,wager,status,created_at) VALUES (?,?,?,?,?,'pending',?)",
                         (sid, challenger_id, opponent_id, str(game_type), wager, now))
            conn.commit()
        return {"ok": True, "session_id": sid, "wager": wager, "wallet_after": wallet-wager}

    def pvp_accept(self, session_id: str, opponent_id: int) -> dict:
        opponent_id = int(opponent_id)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tavern_pvp_sessions WHERE session_id=?", (str(session_id),)).fetchone()
            if not row:
                conn.rollback(); return {"ok": False, "message": "Défi introuvable."}
            if str(row["status"]) != "pending":
                conn.rollback(); return {"ok": False, "message": "Ce défi n'est plus disponible."}
            if int(row["opponent_id"]) != opponent_id:
                conn.rollback(); return {"ok": False, "message": "Ce défi ne t'est pas destiné."}
            wager = int(row["wager"])
            self._ensure_player(conn, opponent_id)
            wallet = int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (opponent_id,)).fetchone()[0])
            if wallet < wager:
                conn.rollback(); return {"ok": False, "message": f"Tu n'as que {wallet} Gold sur toi. Il faut {wager} Gold pour accepter."}
            conn.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?", (wager, opponent_id))
            conn.execute("UPDATE tavern_pvp_sessions SET status='accepted' WHERE session_id=?", (str(session_id),))
            conn.commit()
        return {"ok": True, "wager": wager, "challenger_id": int(row["challenger_id"]), "opponent_id": opponent_id, "game_type": str(row["game_type"])}

    def pvp_refund(self, session_id: str) -> dict:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tavern_pvp_sessions WHERE session_id=?", (str(session_id),)).fetchone()
            if not row or str(row["status"]) not in ("pending", "accepted"):
                conn.rollback(); return {"ok": False}
            wager = int(row["wager"]); c = int(row["challenger_id"]); o = int(row["opponent_id"])
            self._ensure_player(conn, c)
            conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (wager, c))
            if str(row["status"]) == "accepted":
                self._ensure_player(conn, o)
                conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (wager, o))
            conn.execute("UPDATE tavern_pvp_sessions SET status='refunded',finished_at=? WHERE session_id=?", (now, str(session_id)))
            conn.commit()
        return {"ok": True}

    def pvp_settle(self, session_id: str, winner_id: int | None) -> dict:
        """Règle un duel. Le PvP redistribue uniquement le pot : Gold x2 ne crée pas de Gold ici."""
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tavern_pvp_sessions WHERE session_id=?", (str(session_id),)).fetchone()
            if not row or str(row["status"]) != "accepted":
                conn.rollback(); return {"ok": False, "message": "Duel déjà terminé ou invalide."}
            wager = int(row["wager"]); c = int(row["challenger_id"]); o = int(row["opponent_id"])
            self._ensure_player(conn, c); self._ensure_player(conn, o)
            if winner_id is None:
                conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id IN (?,?)", (wager, c, o))
                status = "draw"
            else:
                winner_id = int(winner_id)
                if winner_id not in (c, o):
                    conn.rollback(); return {"ok": False, "message": "Gagnant invalide."}
                conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (wager*2, winner_id))
                status = "finished"
            conn.execute("UPDATE tavern_pvp_sessions SET status=?,winner_id=?,finished_at=? WHERE session_id=?", (status, winner_id, now, str(session_id)))
            wallets = {uid:int(conn.execute("SELECT wallet_gold FROM players WHERE user_id=?", (uid,)).fetchone()[0]) for uid in (c,o)}
            conn.commit()
        return {"ok": True, "wager": wager, "challenger_id": c, "opponent_id": o, "winner_id": winner_id, "wallets": wallets}

    def recover_unfinished(self) -> int:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("SELECT session_id,user_id,wager FROM tavern_sessions WHERE status='active'").fetchall()
            now = int(time.time())
            for row in rows:
                self._ensure_player(conn, int(row["user_id"]))
                conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (int(row["wager"]), int(row["user_id"])))
                conn.execute("UPDATE tavern_sessions SET status='refunded',payout=?,finished_at=? WHERE session_id=?",
                             (int(row["wager"]), now, str(row["session_id"])))
            pvp_rows = conn.execute("SELECT * FROM tavern_pvp_sessions WHERE status IN ('pending','accepted')").fetchall()
            for row in pvp_rows:
                wager = int(row["wager"]); c = int(row["challenger_id"]); o = int(row["opponent_id"])
                self._ensure_player(conn, c)
                conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (wager, c))
                if str(row["status"]) == "accepted":
                    self._ensure_player(conn, o)
                    conn.execute("UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?", (wager, o))
                conn.execute("UPDATE tavern_pvp_sessions SET status='refunded',finished_at=? WHERE session_id=?", (now, str(row["session_id"])))
            conn.commit()
            return len(rows) + len(pvp_rows)


def roll_die() -> int:
    return random.randint(1, 6)


def flip_coin() -> str:
    return random.choice(("pile", "face"))


def rps_bot() -> str:
    return random.choice(("pierre", "feuille", "ciseaux"))


def rps_result(player: str, bot: str) -> int:
    """1 victoire, 0 égalité, -1 défaite."""
    if player == bot:
        return 0
    wins = {("pierre", "ciseaux"), ("ciseaux", "feuille"), ("feuille", "pierre")}
    return 1 if (player, bot) in wins else -1
