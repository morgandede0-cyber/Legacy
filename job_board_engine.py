from __future__ import annotations

import json
import random
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

REFRESH_COOLDOWN_SECONDS = 60 * 60
BOARD_SIZE = 5

RARITIES: Dict[str, dict] = {
    "common": {
        "label": "Commun",
        "emoji": "⚪",
        "weight": 55,
        "gold_min": 8,
        "gold_max": 25,
    },
    "uncommon": {
        "label": "Peu commun",
        "emoji": "🟢",
        "weight": 25,
        "gold_min": 25,
        "gold_max": 60,
    },
    "rare": {
        "label": "Rare",
        "emoji": "🔵",
        "weight": 12,
        "gold_min": 60,
        "gold_max": 120,
    },
    "epic": {
        "label": "Épique",
        "emoji": "🟣",
        "weight": 6,
        "gold_min": 120,
        "gold_max": 240,
    },
    "legendary": {
        "label": "Légendaire",
        "emoji": "🟡",
        "weight": 2,
        "gold_min": 250,
        "gold_max": 500,
    },
}

# Les raretés sont tirées indépendamment pour chaque emplacement.
# Il n'y a donc aucun quota : un panneau peut contenir uniquement du commun,
# plusieurs légendaires, ou n'importe quelle combinaison entre les deux.
JOBS: Dict[str, Tuple[str, ...]] = {
    "common": (
        "Décharger les caisses du marché",
        "Balayer la cour de la taverne",
        "Livrer du pain dans le quartier nord",
        "Nettoyer la fontaine d'Altherya",
        "Nourrir les chevaux des écuries",
        "Ranger les réserves d'un commerçant",
        "Porter des sacs de grain au moulin",
        "Aider un artisan à déplacer son stock",
    ),
    "uncommon": (
        "Livrer un colis fragile hors des remparts",
        "Surveiller un entrepôt pendant la relève",
        "Aider à réparer une portion de palissade",
        "Retrouver des animaux échappés des écuries",
        "Escorter un marchand jusqu'à la porte de la ville",
        "Transporter des médicaments jusqu'à l'infirmerie",
        "Récupérer une cargaison abandonnée sur la route",
        "Faire l'inventaire d'une réserve municipale",
    ),
    "rare": (
        "Escorter une petite caravane commerciale",
        "Retrouver une sacoche volée dans les faubourgs",
        "Assurer une garde nocturne exceptionnelle",
        "Livrer un message scellé à un avant-poste",
        "Sécuriser un convoi de marchandises précieuses",
        "Rechercher un éclaireur porté disparu",
        "Inspecter un ancien passage sous les remparts",
        "Récupérer une caisse perdue sur une route dangereuse",
    ),
    "epic": (
        "Protéger le convoi privé d'un noble d'Altherya",
        "Récupérer une relique volée avant sa revente",
        "Escorter un émissaire à travers une zone hostile",
        "Sécuriser un dépôt après une tentative de pillage",
        "Retrouver la trace d'un groupe de contrebandiers",
        "Transporter un coffre scellé sans poser de questions",
        "Renforcer la garde d'un quartier pendant une alerte",
        "Récupérer des documents dérobés à l'administration",
    ),
    "legendary": (
        "Escorter discrètement le trésor royal d'Altherya",
        "Retrouver un artefact disparu des archives royales",
        "Protéger un messager porteur d'un secret d'État",
        "Récupérer un coffre royal volé aux portes de la ville",
        "Assurer la sécurité d'une rencontre diplomatique secrète",
        "Rapporter une relique historique promise à la couronne",
        "Démasquer le responsable d'un sabotage majeur",
        "Escorter un convoi royal sous menace directe",
    ),
}


@dataclass(frozen=True)
class BoardJob:
    job_id: str
    title: str
    rarity: str
    reward: int

    @property
    def rarity_meta(self) -> dict:
        return RARITIES[self.rarity]

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "rarity": self.rarity,
            "reward": int(self.reward),
        }

    @classmethod
    def from_dict(cls, value: dict) -> "BoardJob":
        return cls(
            job_id=str(value["job_id"]),
            title=str(value["title"]),
            rarity=str(value["rarity"]),
            reward=int(value["reward"]),
        )


@dataclass(frozen=True)
class BoardState:
    user_id: int
    batch_id: str
    jobs: Tuple[BoardJob, ...]
    generated_at: int
    next_board_at: int
    accepted_total: int

    @property
    def cooling_down(self) -> bool:
        return self.next_board_at > int(time.time())

    @property
    def remaining_seconds(self) -> int:
        return max(0, self.next_board_at - int(time.time()))


class JobBoardStore:
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
                CREATE TABLE IF NOT EXISTS job_board_state (
                    user_id INTEGER PRIMARY KEY,
                    batch_id TEXT NOT NULL DEFAULT '',
                    jobs_json TEXT NOT NULL DEFAULT '[]',
                    generated_at INTEGER NOT NULL DEFAULT 0,
                    next_board_at INTEGER NOT NULL DEFAULT 0,
                    accepted_total INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            # La table players existe déjà dans l'économie. On la crée aussi ici
            # pour garantir une installation propre si ce module est initialisé seul.
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

    @staticmethod
    def _rarity_roll() -> str:
        keys = list(RARITIES.keys())
        weights = [int(RARITIES[key]["weight"]) for key in keys]
        return random.choices(keys, weights=weights, k=1)[0]

    def _generate_batch(self) -> Tuple[str, List[BoardJob]]:
        batch_id = uuid.uuid4().hex[:12]
        used_titles: set[str] = set()
        jobs: List[BoardJob] = []

        for _ in range(BOARD_SIZE):
            rarity = self._rarity_roll()
            pool = [title for title in JOBS[rarity] if title not in used_titles]
            if not pool:
                pool = list(JOBS[rarity])
            title = random.choice(pool)
            used_titles.add(title)
            meta = RARITIES[rarity]
            reward = random.randint(int(meta["gold_min"]), int(meta["gold_max"]))
            jobs.append(
                BoardJob(
                    job_id=uuid.uuid4().hex[:10],
                    title=title,
                    rarity=rarity,
                    reward=reward,
                )
            )
        return batch_id, jobs

    @staticmethod
    def _decode_jobs(raw: str) -> Tuple[BoardJob, ...]:
        try:
            data = json.loads(raw or "[]")
            return tuple(BoardJob.from_dict(item) for item in data)
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return tuple()

    @staticmethod
    def _encode_jobs(jobs: List[BoardJob] | Tuple[BoardJob, ...]) -> str:
        return json.dumps([job.to_dict() for job in jobs], ensure_ascii=False, separators=(",", ":"))

    def _state_from_row(self, row: sqlite3.Row) -> BoardState:
        return BoardState(
            user_id=int(row["user_id"]),
            batch_id=str(row["batch_id"] or ""),
            jobs=self._decode_jobs(str(row["jobs_json"] or "[]")),
            generated_at=int(row["generated_at"] or 0),
            next_board_at=int(row["next_board_at"] or 0),
            accepted_total=int(row["accepted_total"] or 0),
        )

    def get_board(self, user_id: int) -> BoardState:
        """Retourne le panneau actuel et génère automatiquement le prochain lot si son heure est arrivée."""
        uid = int(user_id)
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT OR IGNORE INTO job_board_state(user_id) VALUES (?)", (uid,))
            row = conn.execute("SELECT * FROM job_board_state WHERE user_id=?", (uid,)).fetchone()
            jobs = self._decode_jobs(str(row["jobs_json"] or "[]"))
            next_at = int(row["next_board_at"] or 0)

            if not jobs and now >= next_at:
                batch_id, generated = self._generate_batch()
                conn.execute(
                    """
                    UPDATE job_board_state
                    SET batch_id=?, jobs_json=?, generated_at=?, next_board_at=0
                    WHERE user_id=?
                    """,
                    (batch_id, self._encode_jobs(generated), now, uid),
                )
                row = conn.execute("SELECT * FROM job_board_state WHERE user_id=?", (uid,)).fetchone()
            conn.commit()
            return self._state_from_row(row)

    def accept_job(self, user_id: int, batch_id: str, job_id: str) -> tuple[bool, str, BoardJob | None, BoardState]:
        """Accepte une annonce, crédite son Gold et vide le panneau pendant une heure."""
        uid = int(user_id)
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT OR IGNORE INTO job_board_state(user_id) VALUES (?)", (uid,))
            row = conn.execute("SELECT * FROM job_board_state WHERE user_id=?", (uid,)).fetchone()
            state = self._state_from_row(row)

            if state.next_board_at > now:
                conn.rollback()
                return False, "Le panneau est encore en renouvellement.", None, state

            if not state.jobs:
                conn.rollback()
                fresh = self.get_board(uid)
                return False, "Les annonces viennent d'être renouvelées. Actualise le panneau.", None, fresh

            if state.batch_id != str(batch_id):
                conn.rollback()
                fresh = self.get_board(uid)
                return False, "Ce panneau n'est plus à jour. Actualise les annonces.", None, fresh

            selected = next((job for job in state.jobs if job.job_id == str(job_id)), None)
            if selected is None:
                conn.rollback()
                return False, "Cette annonce n'est plus disponible.", None, state

            conn.execute("INSERT OR IGNORE INTO players(user_id) VALUES (?)", (uid,))
            conn.execute(
                "UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?",
                (int(selected.reward), uid),
            )
            next_at = now + REFRESH_COOLDOWN_SECONDS
            conn.execute(
                """
                UPDATE job_board_state
                SET batch_id='', jobs_json='[]', generated_at=?, next_board_at=?, accepted_total=accepted_total+1
                WHERE user_id=?
                """,
                (now, next_at, uid),
            )
            conn.commit()

        return True, "Petit boulot accepté.", selected, self.get_board(uid)
