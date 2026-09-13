from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Achievement:
    key: str
    branch: str
    branch_label: str
    branch_emoji: str
    tier: int
    rarity: str
    rarity_emoji: str
    color: int
    title: str
    description: str


RARITIES = {
    1: ("Commun", "⚪", 0x95A5A6),
    2: ("Rare", "🟢", 0x2ECC71),
    3: ("Épique", "🔵", 0x3498DB),
    4: ("Mythique", "🟣", 0x9B59B6),
    5: ("Légendaire", "🟡", 0xF1C40F),
}

GEAR = {
    "pickaxe": ("Pioche", "⛏️"),
    "axe": ("Hache", "🪓"),
    "spear": ("Lance", "🗡️"),
    "bag": ("Sac", "🎒"),
}

TITLES = {
    "pickaxe": ["Premier coup de pioche", "Mineur débutant", "Mineur confirmé", "Maître mineur", "Pioche de légende"],
    "axe": ["Première hache", "Bûcheron débutant", "Bûcheron confirmé", "Maître bûcheron", "Hache de légende"],
    "spear": ["Première lance", "Chasseur débutant", "Chasseur confirmé", "Maître chasseur", "Lance de légende"],
    "bag": ["Premier sac", "Voyageur équipé", "Aventurier préparé", "Explorateur aguerri", "Sac de légende"],
}


def _description(branch: str, tier: int) -> str:
    label = GEAR[branch][0].lower()
    if tier == 1:
        return f"Achète ta première {label}." if branch != "bag" else "Achète ton premier sac d'expédition."
    if tier == 5:
        return f"Améliore ta {label} au niveau maximum." if branch != "bag" else "Améliore ton sac au niveau maximum."
    return f"Améliore ta {label} au niveau {tier}." if branch != "bag" else f"Améliore ton sac au niveau {tier}."


ACHIEVEMENTS: dict[str, Achievement] = {}
for branch, (label, emoji) in GEAR.items():
    for tier in range(1, 6):
        rarity, rarity_emoji, color = RARITIES[tier]
        key = f"gear:{branch}:{tier}"
        ACHIEVEMENTS[key] = Achievement(
            key=key,
            branch=branch,
            branch_label=label,
            branch_emoji=emoji,
            tier=tier,
            rarity=rarity,
            rarity_emoji=rarity_emoji,
            color=color,
            title=TITLES[branch][tier - 1],
            description=_description(branch, tier),
        )

# Branche de succès du Troubadour — progression de la Saison 1.
# Les cinq paliers couvrent le voyage du premier récit jusqu'au chapitre final.
TROUBADOUR_ACHIEVEMENTS = [
    (1, 1, "Première histoire", "Débloque le chapitre 1 auprès du Troubadour."),
    (2, 5, "À l'écoute du vieux renard", "Débloque 5 chapitres de la Saison 1."),
    (3, 10, "Collectionneur de récits", "Débloque 10 chapitres de la Saison 1."),
    (4, 20, "Gardien des chroniques", "Débloque 20 chapitres de la Saison 1."),
    (5, 30, "Légende des Trois Terres", "Débloque les 30 chapitres de la Saison 1."),
]
for tier, chapter_goal, title, description in TROUBADOUR_ACHIEVEMENTS:
    rarity, rarity_emoji, color = RARITIES[tier]
    key = f"troubadour:{tier}"
    ACHIEVEMENTS[key] = Achievement(
        key=key,
        branch="troubadour",
        branch_label="Troubadour",
        branch_emoji="📖",
        tier=tier,
        rarity=rarity,
        rarity_emoji=rarity_emoji,
        color=color,
        title=title,
        description=description,
    )

# Branches de progression supplémentaires — V1.48.
EXTRA_ACHIEVEMENT_BRANCHES = {
    "tavern_reputation": ("Réputation de Taverne", "🍺", [
        (1, "Client discret", "Bois 5 verres à la Taverne de Altherya."),
        (2, "Habitué du comptoir", "Atteins le palier Habitué du comptoir."),
        (3, "Pilier de taverne", "Atteins le palier Pilier de taverne."),
        (4, "Ivrogne notoire", "Atteins le palier Ivrogne notoire."),
        (5, "Alcoolique du coin", "Atteins le dernier palier de réputation de la Taverne."),
    ]),
    "tavern_rounds": ("Tournées générales", "🍻", [
        (1, "La première est pour moi !", "Offre ta première tournée générale à la Taverne."),
        (2, "Généreux du comptoir", "Offre 5 tournées générales à la Taverne."),
        (3, "Mécène de la Taverne", "Offre 20 tournées générales à la Taverne."),
    ]),
    "arena_champion": ("Champion de l'Arène", "👑", [
        (1, "Le Champion saigne", "Bats le Champion I."),
        (2, "Rival de l'Arène", "Bats le Champion III."),
        (3, "Briseur de couronne", "Bats le Champion V."),
        (4, "Terreur du Champion", "Bats le Champion VII."),
        (5, "Au-dessus du Champion", "Bats le Champion X."),
    ]),
    "criminal_reputation": ("Réputation criminelle", "🐺", [
        (1, "Un nom dans l'ombre", "Réussis 5 méfaits et entre dans les rumeurs de la Ruelle."),
        (2, "Petite frappe", "Atteins le rang Petite frappe."),
        (3, "Bandit", "Atteins le rang Bandit."),
        (4, "Criminel", "Atteins le rang Criminel."),
        (5, "Seigneur de la Ruelle", "Atteins le rang Seigneur de la Ruelle."),
    ]),
}
for branch, (label, emoji, rows) in EXTRA_ACHIEVEMENT_BRANCHES.items():
    for tier, title, description in rows:
        rarity, rarity_emoji, color = RARITIES[tier]
        key = f"{branch}:{tier}"
        ACHIEVEMENTS[key] = Achievement(
            key=key, branch=branch, branch_label=label, branch_emoji=emoji, tier=tier,
            rarity=rarity, rarity_emoji=rarity_emoji, color=color, title=title, description=description,
        )


# V1.57 — 12 succès secrets d'ivresse (2 par palier de réputation).
# Leur condition n'est volontairement pas décrite avant découverte dans l'interface joueur.
TAVERN_SECRET_ACHIEVEMENTS = [
    (0,1,1,"Le sol avait l'air confortable","Tu ne sais toujours pas pourquoi tu étais sous cette table."),
    (0,2,1,"C'était pas à moi ?","Un bretzel, un mercenaire, et une très mauvaise lecture de la situation."),
    (1,1,2,"Pourquoi j'ai une poule ?","Gérard fait désormais partie de l'histoire. Ne pose pas de question."),
    (1,2,2,"C'est pas ma chaussure","Deux pieds, deux chaussures, probablement trois propriétaires."),
    (2,1,3,"Une carrière très courte","Altherya se souviendra de ces quarante secondes de musique."),
    (2,2,3,"J'ai fait QUOI ?!","Une bague inconnue. Aucun témoin coopératif."),
    (3,1,4,"Il juge mes choix de vie","Le cheval avait l'air profondément déçu."),
    (3,2,4,"Cette porte n'était pas là hier","Tu l'as vue. Tu en es certain. Enfin... presque."),
    (4,1,5,"Votre Majesté...","La statue n'a jamais répondu. Ça ne t'a pas empêché de perdre le débat."),
    (4,2,5,"Techniquement, je suis vivant","Le cercueil était vide. Jusqu'à ton arrivée."),
    (5,1,5,"Aucun souvenir","Tu possèdes maintenant une clé que personne ne veut reconnaître."),
    (5,2,5,"Plus jamais.","Tu l'as juré. Puis tu as commandé une autre chope."),
]
for rep_tier, secret_no, rarity_tier, title, description in TAVERN_SECRET_ACHIEVEMENTS:
    rarity, rarity_emoji, color = RARITIES[rarity_tier]
    key = f"tavern_secret:{rep_tier}:{secret_no}"
    ACHIEVEMENTS[key] = Achievement(
        key=key, branch="tavern_secrets", branch_label="Secrets de la Taverne", branch_emoji="🔒",
        tier=rarity_tier, rarity=rarity, rarity_emoji=rarity_emoji, color=color, title=title, description=description,
    )


class AchievementStore:
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS achievement_channels (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS log_channels (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS achievements_unlocked (
                    user_id INTEGER NOT NULL,
                    achievement_key TEXT NOT NULL,
                    unlocked_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, achievement_key)
                )
                """
            )
            conn.commit()

    def set_channel(self, guild_id: int, channel_id: int):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO achievement_channels(guild_id, channel_id) VALUES(?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id
                """,
                (int(guild_id), int(channel_id)),
            )
            conn.commit()

    def get_channel(self, guild_id: int) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT channel_id FROM achievement_channels WHERE guild_id=?",
                (int(guild_id),),
            ).fetchone()
        return int(row["channel_id"]) if row else None


    def set_log_channel(self, guild_id: int, channel_id: int):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO log_channels(guild_id, channel_id) VALUES(?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id
                """,
                (int(guild_id), int(channel_id)),
            )
            conn.commit()

    def get_log_channel(self, guild_id: int) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT channel_id FROM log_channels WHERE guild_id=?",
                (int(guild_id),),
            ).fetchone()
        return int(row["channel_id"]) if row else None

    def unlock(self, user_id: int, achievement_key: str) -> bool:
        if achievement_key not in ACHIEVEMENTS:
            return False
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO achievements_unlocked(user_id, achievement_key, unlocked_at) VALUES(?,?,?)",
                (int(user_id), achievement_key, datetime.now().isoformat(timespec="seconds")),
            )
            conn.commit()
            return cur.rowcount > 0

    def remove(self, user_id: int, achievement_key: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM achievements_unlocked WHERE user_id=? AND achievement_key=?",
                (int(user_id), str(achievement_key)),
            )
            conn.commit()
            return cur.rowcount > 0

    def unlocked_keys(self, user_id: int) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT achievement_key FROM achievements_unlocked WHERE user_id=?",
                (int(user_id),),
            ).fetchall()
        return {str(r["achievement_key"]) for r in rows}

    def branch_progress(self, user_id: int, branch: str) -> int:
        unlocked = self.unlocked_keys(user_id)
        # Fonctionne pour toutes les branches (équipements, Troubadour, futures branches).
        return sum(
            1 for key, ach in ACHIEVEMENTS.items()
            if ach.branch == branch and key in unlocked
        )
