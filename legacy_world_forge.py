from __future__ import annotations

import asyncio
import math
import os
import random
import re
import sqlite3
from shared_economy import connect_shared
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from urllib.parse import unquote

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageOps
from castle_engine import CastleStore
from gazette_engine import GazetteStore

# ============================================================
# CONFIG
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
ASSET_DIR = BASE_DIR / "assets"
WORLD_MAP = ASSET_DIR / "world" / "elyndor_map.png"
LEGACY_CITY = ASSET_DIR / "world" / "legacy_city.png"
KHAZ_GORAM = ASSET_DIR / "forge" / "khaz_goram.png"
THORGAR = ASSET_DIR / "forge" / "thorgar.png"
EQUIPMENT_DIR = ASSET_DIR / "equipment"
DB_PATH = BASE_DIR / "data" / "legacy.sqlite3"
CASTLE = CastleStore(DB_PATH)
GAZETTE = GazetteStore(DB_PATH)
RENDER_DIR = BASE_DIR / "renders"
RENDER_DIR.mkdir(exist_ok=True)

BASE_HP = 1000
BASE_ATK = 100
BASE_DEF = 60
BASE_SPEED = 100

BRANCH_LABELS = {
    "atk": "⚔️ Attaque",
    "def": "🛡️ Défense",
    "speed": "💨 Vitesse",
}

TIER_ORDER = ["commun", "rare", "epique", "mythique", "legendaire"]
TIER_LABELS = {
    "commun": "Commun",
    "rare": "Rare",
    "epique": "Épique",
    "mythique": "Mythique",
    "legendaire": "Légendaire",
}
TIER_INDEX = {name: i for i, name in enumerate(TIER_ORDER)}

SET_NAMES = {
    "atk": {
        "commun": "Barbarian",
        "rare": "Soldier",
        "epique": "Royal Guard",
        "mythique": "Almaty",
        "legendaire": "Spirit Fyra",
    },
    "def": {
        "commun": "Journeyman",
        "rare": "Adventurer",
        "epique": "Knight",
        "mythique": "Snake",
        "legendaire": "Spirit Vanna",
    },
    "speed": {
        "commun": "Bard",
        "rare": "Hunter",
        "epique": "Royal Archer",
        "mythique": "Owl",
        "legendaire": "Spirit Zephyr",
    },
}

# Le 3x3 officiel : les 6 premiers emplacements existent dès le Commun.
# Casque / Gantelets / Bottes apparaissent à partir du Mythique, comme dans les assets fournis.
SLOTS = [
    "weapon", "helmet", "ring",
    "shield", "belt", "amulet",
    "bracelet", "gauntlets", "boots",
]
SLOT_LABELS = {
    "weapon": "Arme",
    "helmet": "Casque",
    "ring": "Anneau",
    "shield": "Bouclier",
    "belt": "Ceinture",
    "amulet": "Amulette",
    "bracelet": "Bracelet",
    "gauntlets": "Gantelets",
    "boots": "Bottes",
}
BASE_SLOTS = ["weapon", "shield", "belt", "ring", "bracelet", "amulet"]
ADVANCED_SLOTS = ["helmet", "gauntlets", "boots"]

COMMON_GOLD_PRICES = {
    "weapon": 300,
    "shield": 300,
    "belt": 200,
    "bracelet": 200,
    "ring": 250,
    "amulet": 250,
}

POUCIEL_UPGRADE_COST = {
    "rare": 20,
    "epique": 45,
    "mythique": 90,
    "legendaire": 160,
}
NEW_MYTHIC_COST = 70

# Les équipements ne donnent plus de PV : les PV progressent désormais avec le niveau du joueur.
SPEC_PIECE = {
    "commun": {"base": 2/6, "advanced": 0.0},
    "rare": {"base": 4/6, "advanced": 0.0},
    "epique": {"base": 6/6, "advanced": 0.0},
    "mythique": {"base": 1.05, "advanced": (8 - 1.05*6)/3},
    "legendaire": {"base": 1.20, "advanced": (10 - 1.20*6)/3},
}

# Champion I -> X : difficulté fixe, pas de scaling caché sur le joueur.
# Champion X est calibré pour qu'un joueur Légendaire complet puisse réellement jouer à armes égales.
CHAMPIONS = {
    1:  {"name": "Champion I",  "hp": 960,  "atk": 90,  "def": 52, "speed": 96,  "reward": 150},
    2:  {"name": "Champion II", "hp": 1000, "atk": 94,  "def": 54, "speed": 98,  "reward": 225},
    3:  {"name": "Champion III","hp": 1040, "atk": 97,  "def": 56, "speed": 100, "reward": 325},
    4:  {"name": "Champion IV", "hp": 1080, "atk": 100, "def": 58, "speed": 102, "reward": 450},
    5:  {"name": "Champion V",  "hp": 1120, "atk": 103, "def": 60, "speed": 104, "reward": 600},
    6:  {"name": "Champion VI", "hp": 1150, "atk": 105, "def": 62, "speed": 105, "reward": 800},
    7:  {"name": "Champion VII","hp": 1180, "atk": 107, "def": 64, "speed": 106, "reward": 1050},
    8:  {"name": "Champion VIII","hp": 1210,"atk": 109, "def": 66, "speed": 108, "reward": 1350},
    9:  {"name": "Champion IX", "hp": 1240, "atk": 111, "def": 68, "speed": 109, "reward": 1750},
    10: {"name": "Champion X",  "hp": 1270, "atk": 113, "def": 70, "speed": 110, "reward": 2500},
}

# ============================================================
# DB
# ============================================================
class GameDB:
    def __init__(self, path: Path):
        self.path = Path(path)
        # La V1.61 est importée avant l'initialisation des autres modules.
        # Sur une installation neuve, le dossier data/ n'existe donc pas encore.
        # SQLite sait créer le fichier .sqlite3, mais pas son dossier parent.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = asyncio.Lock()
        self._init()

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = connect_shared(str(self.path), timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def _init(self):
        con = self._connect()
        cur = con.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS legacy_wallet (
                user_id INTEGER PRIMARY KEY,
                pouciel INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS legacy_equipment (
                user_id INTEGER NOT NULL,
                slot TEXT NOT NULL,
                branch TEXT NOT NULL,
                tier TEXT NOT NULL,
                PRIMARY KEY (user_id, slot)
            );
            CREATE TABLE IF NOT EXISTS legacy_arena_progress (
                user_id INTEGER PRIMARY KEY,
                max_champion_defeated INTEGER NOT NULL DEFAULT 0,
                champion_wins INTEGER NOT NULL DEFAULT 0,
                pvp_wins INTEGER NOT NULL DEFAULT 0,
                pvp_losses INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        con.commit()
        con.close()

    async def ensure_user(self, user_id: int):
        async with self.lock:
            con = self._connect()
            con.execute("INSERT OR IGNORE INTO legacy_wallet(user_id) VALUES(?)", (user_id,))
            con.execute("INSERT OR IGNORE INTO legacy_arena_progress(user_id) VALUES(?)", (user_id,))
            con.commit(); con.close()

    async def wallet(self, user_id: int) -> Tuple[int, int]:
        await self.ensure_user(user_id)
        con = self._connect()
        row = con.execute("SELECT pouciel FROM legacy_wallet WHERE user_id=?", (user_id,)).fetchone()
        prow = con.execute("SELECT wallet_gold FROM players WHERE user_id=?", (user_id,)).fetchone()
        con.close()
        return int(prow["wallet_gold"] if prow else 0), int(row["pouciel"])

    async def add_currency(self, user_id: int, gold: int = 0, pouciel: int = 0):
        await self.ensure_user(user_id)
        async with self.lock:
            con = self._connect()
            con.execute("INSERT OR IGNORE INTO players(user_id) VALUES(?)", (user_id,))
            con.execute("UPDATE players SET wallet_gold=MAX(0,wallet_gold+?) WHERE user_id=?", (gold, user_id))
            con.execute("UPDATE legacy_wallet SET pouciel=MAX(0,pouciel+?) WHERE user_id=?", (pouciel, user_id))
            con.commit(); con.close()

    async def spend(self, user_id: int, *, gold: int = 0, pouciel: int = 0) -> bool:
        await self.ensure_user(user_id)
        async with self.lock:
            con = self._connect()
            con.execute("INSERT OR IGNORE INTO players(user_id) VALUES(?)", (user_id,))
            row = con.execute("SELECT wallet_gold FROM players WHERE user_id=?", (user_id,)).fetchone()
            prow = con.execute("SELECT pouciel FROM legacy_wallet WHERE user_id=?", (user_id,)).fetchone()
            if row["wallet_gold"] < gold or prow["pouciel"] < pouciel:
                con.close(); return False
            con.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?", (gold, user_id))
            con.execute("UPDATE legacy_wallet SET pouciel=pouciel-? WHERE user_id=?", (pouciel, user_id))
            con.commit(); con.close(); return True

    async def get_equipment(self, user_id: int) -> Dict[str, dict]:
        await self.ensure_user(user_id)
        con = self._connect()
        rows = con.execute("SELECT slot,branch,tier FROM legacy_equipment WHERE user_id=?", (user_id,)).fetchall()
        con.close()
        return {r["slot"]: {"branch": r["branch"], "tier": r["tier"]} for r in rows}

    async def set_equipment(self, user_id: int, slot: str, branch: str, tier: str):
        await self.ensure_user(user_id)
        async with self.lock:
            con = self._connect()
            con.execute(
                "INSERT INTO legacy_equipment(user_id,slot,branch,tier) VALUES(?,?,?,?) "
                "ON CONFLICT(user_id,slot) DO UPDATE SET branch=excluded.branch,tier=excluded.tier",
                (user_id, slot, branch, tier),
            )
            con.commit(); con.close()

    async def purchase_common_piece(self, user_id: int, slot: str, branch: str, price: int):
        """Achat atomique : impossible de payer deux fois la même pièce."""
        await self.ensure_user(user_id)
        async with self.lock:
            con = self._connect()
            try:
                con.execute("INSERT OR IGNORE INTO players(user_id) VALUES(?)", (user_id,))
                owned = con.execute(
                    "SELECT 1 FROM legacy_equipment WHERE user_id=? AND slot=?",
                    (user_id, slot),
                ).fetchone()
                if owned:
                    return "owned"
                row = con.execute("SELECT wallet_gold FROM players WHERE user_id=?", (user_id,)).fetchone()
                if not row or int(row["wallet_gold"]) < price:
                    return "gold"
                con.execute("UPDATE players SET wallet_gold=wallet_gold-? WHERE user_id=?", (price, user_id))
                con.execute(
                    "INSERT INTO legacy_equipment(user_id,slot,branch,tier) VALUES(?,?,?,?)",
                    (user_id, slot, branch, "commun"),
                )
                con.commit()
                return "ok"
            finally:
                con.close()

    async def forge_upgrade_piece(self, user_id: int, slot: str, branch: str):
        """Amélioration atomique au Pouciel. Retourne (status, old_tier, new_tier, cost)."""
        await self.ensure_user(user_id)
        async with self.lock:
            con = self._connect()
            try:
                row = con.execute(
                    "SELECT branch,tier FROM legacy_equipment WHERE user_id=? AND slot=?",
                    (user_id, slot),
                ).fetchone()
                if row:
                    if row["branch"] != branch:
                        return ("wrong_set", row["tier"], None, 0)
                    old_tier = row["tier"]
                    if old_tier == "legendaire":
                        return ("max", old_tier, None, 0)
                    new_tier = TIER_ORDER[TIER_INDEX[old_tier] + 1]
                    cost = POUCIEL_UPGRADE_COST[new_tier]
                else:
                    if slot not in ADVANCED_SLOTS:
                        return ("missing", None, None, 0)
                    # Sécurité serveur : impossible de forger directement un emplacement avancé
                    # avant d'avoir obtenu au moins une pièce Mythique (ou Légendaire).
                    unlocked = con.execute(
                        "SELECT 1 FROM legacy_equipment WHERE user_id=? AND tier IN ('mythique','legendaire') LIMIT 1",
                        (user_id,),
                    ).fetchone()
                    if not unlocked:
                        return ("mythic_locked", None, "mythique", NEW_MYTHIC_COST)
                    old_tier = None
                    new_tier = "mythique"
                    cost = NEW_MYTHIC_COST

                if (branch, new_tier, slot) not in CATALOG:
                    return ("asset", old_tier, new_tier, cost)
                prow = con.execute("SELECT pouciel FROM legacy_wallet WHERE user_id=?", (user_id,)).fetchone()
                if not prow or int(prow["pouciel"]) < cost:
                    return ("pouciel", old_tier, new_tier, cost)

                con.execute("UPDATE legacy_wallet SET pouciel=pouciel-? WHERE user_id=?", (cost, user_id))
                con.execute(
                    "INSERT INTO legacy_equipment(user_id,slot,branch,tier) VALUES(?,?,?,?) "
                    "ON CONFLICT(user_id,slot) DO UPDATE SET branch=excluded.branch,tier=excluded.tier",
                    (user_id, slot, branch, new_tier),
                )
                con.commit()
                return ("ok", old_tier, new_tier, cost)
            finally:
                con.close()

    async def record_champion_win(self, user_id: int, level: int):
        await self.ensure_user(user_id)
        async with self.lock:
            con = self._connect()
            con.execute(
                "UPDATE legacy_arena_progress SET max_champion_defeated=MAX(max_champion_defeated,?), champion_wins=champion_wins+1 WHERE user_id=?",
                (level, user_id),
            )
            con.commit(); con.close()

    async def record_pvp(self, winner_id: int, loser_id: int):
        await self.ensure_user(winner_id); await self.ensure_user(loser_id)
        async with self.lock:
            con = self._connect()
            con.execute("UPDATE legacy_arena_progress SET pvp_wins=pvp_wins+1 WHERE user_id=?", (winner_id,))
            con.execute("UPDATE legacy_arena_progress SET pvp_losses=pvp_losses+1 WHERE user_id=?", (loser_id,))
            con.commit(); con.close()

DB = GameDB(DB_PATH)

# ============================================================
# EQUIPMENT ASSET CATALOG
# ============================================================
@dataclass(frozen=True)
class ItemAsset:
    branch: str
    tier: str
    slot: str
    path: Path
    display_name: str


def detect_slot(filename: str, branch: str, tier: str) -> Optional[str]:
    s = unquote(filename).lower()
    # descriptive names first
    if "amulet" in s or "amle" in s: return "amulet"
    if "bracelet" in s or "brle" in s: return "bracelet"
    if "ring" in s or "rile" in s: return "ring"
    if "shield" in s or "shle" in s: return "shield"
    if "belt" in s or "bele" in s: return "belt"
    if "helmet" in s or "hele" in s: return "helmet"
    if "gauntlet" in s or "gale" in s: return "gauntlets"
    if "boots" in s or "bole" in s: return "boots"
    if any(k in s for k in ["axe", "sword", "spear", "bow", "halberd", "wele", "weapon"]): return "weapon"
    # speed mythic cryptic bow
    if "bomy" in s: return "weapon"
    return None


def pretty_item_name(branch: str, tier: str, slot: str) -> str:
    set_name = SET_NAMES[branch][tier]
    return f"{SLOT_LABELS[slot]} — {set_name}"


def build_catalog() -> Dict[Tuple[str, str, str], ItemAsset]:
    cat = {}
    if not EQUIPMENT_DIR.exists():
        return cat
    for p in EQUIPMENT_DIR.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in {".png", ".webp", ".jpg", ".jpeg"}:
            continue
        folder = p.parent.name.lower()
        branch = "atk" if folder.startswith("atk ") else "def" if folder.startswith("def ") else "speed" if folder.startswith("speed ") else None
        if not branch: continue
        tier = next((t for t in TIER_ORDER if t in folder), None)
        if not tier: continue
        slot = detect_slot(p.name, branch, tier)
        if not slot: continue
        cat[(branch, tier, slot)] = ItemAsset(branch, tier, slot, p, pretty_item_name(branch, tier, slot))
    return cat

CATALOG = build_catalog()

# ============================================================
# STATS / BALANCE
# ============================================================
@dataclass
class FighterStats:
    hp: int
    atk: int
    defense: int
    speed: int
    atk_bonus_pct: float = 0.0
    def_bonus_pct: float = 0.0
    speed_bonus_pct: float = 0.0
    hp_bonus_pct: float = 0.0


def piece_contribution(slot: str, tier: str) -> Tuple[float, float]:
    kind = "advanced" if slot in ADVANCED_SLOTS else "base"
    return 0.0, SPEC_PIECE[tier][kind]


def stats_from_equipment(eq: Dict[str, dict]) -> FighterStats:
    hp_pct = atk_pct = def_pct = speed_pct = 0.0
    for slot, data in eq.items():
        tier, branch = data["tier"], data["branch"]
        hp_add, spec_add = piece_contribution(slot, tier)
        hp_pct += hp_add
        if branch == "atk": atk_pct += spec_add
        elif branch == "def": def_pct += spec_add
        else: speed_pct += spec_add
    hp = BASE_HP  # valeur neutre; les PV réels sont calculés depuis le niveau
    atk = round(BASE_ATK * (1 + atk_pct / 100))
    speed = round(BASE_SPEED * (1 + speed_pct / 100))
    return FighterStats(hp, atk, BASE_DEF, speed, atk_pct, def_pct, speed_pct, hp_pct)


def damage_roll(attacker: FighterStats, defender: FighterStats, *, power: float = 1.0, guard: bool = False) -> Tuple[int, bool, bool]:
    # dodge: vitesse utile mais plafonnée à 15% toutes sources confondues
    dodge = 0.02 + max(0, defender.speed - attacker.speed) * 0.003 + (defender.speed_bonus_pct / 100) * 0.50
    dodge = min(0.15, max(0.02, dodge))
    if random.random() < dodge:
        return 0, False, True

    mitigation = 100 / (100 + defender.defense)
    raw = attacker.atk * mitigation * power * random.uniform(0.92, 1.08)
    # spécialisation défense = réduction de dégâts, max 10% avec le légendaire complet
    raw *= (1 - min(0.10, defender.def_bonus_pct / 100))
    if guard:
        raw *= 0.50
    crit = random.random() < 0.05
    if crit:
        raw *= 1.5
    return max(1, round(raw)), crit, False

# ============================================================
# RENDER 3x3 EQUIPMENT MENU
# ============================================================
def get_font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def render_equipment_grid(user_id: int, display_name: str, eq: Dict[str, dict], stats: FighterStats) -> Path:
    W, H = 1200, 920
    img = Image.new("RGB", (W, H), (19, 15, 12))
    draw = ImageDraw.Draw(img)
    title_font = get_font(42, True); sub_font = get_font(24, True); text_font = get_font(20); tiny = get_font(16)

    # background panel
    draw.rounded_rectangle((20, 20, W-20, H-20), radius=22, fill=(29,23,18), outline=(180,120,35), width=4)
    draw.text((50, 38), f"Équipement — {display_name}", font=title_font, fill=(236,196,108))
    draw.text((50, 95), "3×3 • Équipement automatique • Une amélioration remplace la pièce précédente", font=text_font, fill=(210,205,195))

    cell_w, cell_h = 260, 220
    sx, sy, gap = 55, 150, 25
    branch_colors = {"atk": (173,69,44), "def": (54,108,160), "speed": (113,82,168)}

    for idx, slot in enumerate(SLOTS):
        row, col = divmod(idx, 3)
        x = sx + col*(cell_w+gap); y = sy + row*(cell_h+gap)
        data = eq.get(slot)
        outline = (130,95,52)
        if data:
            outline = branch_colors[data["branch"]]
        draw.rounded_rectangle((x,y,x+cell_w,y+cell_h), radius=18, fill=(10,10,11), outline=outline, width=4)
        draw.text((x+14,y+12), SLOT_LABELS[slot], font=sub_font, fill=(238,216,170))
        if not data:
            if slot in ADVANCED_SLOTS:
                draw.text((x+20,y+95), "Débloqué\nau Mythique", font=text_font, fill=(120,120,120))
            else:
                draw.text((x+20,y+95), "Aucune pièce", font=text_font, fill=(120,120,120))
            continue

        branch, tier = data["branch"], data["tier"]
        asset = CATALOG.get((branch, tier, slot))
        if asset and asset.path.exists():
            try:
                art = Image.open(asset.path).convert("RGBA")
                art.thumbnail((120,120), Image.Resampling.LANCZOS)
                art = ImageOps.contain(art, (120,120))
                img.paste(art, (x+12, y+62), art)
            except Exception:
                pass
        draw.text((x+140,y+72), TIER_LABELS[tier], font=text_font, fill=(235,235,235))
        draw.text((x+140,y+103), BRANCH_LABELS[branch].split(" ",1)[1], font=tiny, fill=(210,210,210))
        hp_add, spec_add = piece_contribution(slot,tier)
        draw.text((x+140,y+132), "PV : selon niveau", font=tiny, fill=(205,205,205))
        stat_txt = "ATK" if branch=="atk" else "DEF" if branch=="def" else "VIT"
        draw.text((x+140,y+158), f"{stat_txt} +{spec_add:.2f}%", font=tiny, fill=(205,205,205))

    # summary bottom
    y0 = 875
    summary = f"❤️ PV selon niveau   ⚔️ {stats.atk} ATK (+{stats.atk_bonus_pct:.1f}%)   🛡️ réduction +{stats.def_bonus_pct:.1f}%   💨 {stats.speed} VIT (+{stats.speed_bonus_pct:.1f}%)"
    draw.text((55, y0), summary, font=text_font, fill=(240,225,194))

    out = RENDER_DIR / f"equipment_{user_id}.png"
    img.save(out, quality=95)
    return out

# ============================================================
# HELPERS
# ============================================================
async def edit_with_image(interaction: discord.Interaction, image_path: Path, *, title: str, description: str, view: discord.ui.View):
    """Édite proprement le message du bouton, y compris lorsqu'il est éphémère.

    `interaction.message.edit()` utilise l'endpoint classique des messages et peut
    renvoyer `10008 Unknown Message` avec une réponse éphémère. Le callback répond
    donc directement à l'interaction via `edit_message`, qui est la méthode prévue
    par Discord pour modifier le message ayant déclenché le bouton.
    """
    file = discord.File(image_path, filename=image_path.name)
    embed = discord.Embed(title=title, description=description, color=0xB67A2A)
    embed.set_image(url=f"attachment://{image_path.name}")
    try:
        if not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, attachments=[file], view=view)
        else:
            await interaction.edit_original_response(embed=embed, attachments=[file], view=view)
    except discord.NotFound:
        # Le message d'origine a réellement été supprimé : recrée une interface privée
        # au lieu de faire planter toute la View.
        fresh = discord.File(image_path, filename=image_path.name)
        fresh_embed = discord.Embed(title=title, description=description, color=0xB67A2A)
        fresh_embed.set_image(url=f"attachment://{image_path.name}")
        await interaction.followup.send(embed=fresh_embed, file=fresh, view=view, ephemeral=True)

async def send_with_image(interaction: discord.Interaction, image_path: Path, *, title: str, description: str, view: discord.ui.View, ephemeral=False):
    file = discord.File(image_path, filename=image_path.name)
    embed = discord.Embed(title=title, description=description, color=0xB67A2A)
    embed.set_image(url=f"attachment://{image_path.name}")
    await interaction.response.send_message(embed=embed, file=file, view=view, ephemeral=ephemeral)

# ============================================================
# WORLD VIEWS
# ============================================================
class WorldView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Altherya", emoji="👑", style=discord.ButtonStyle.primary, custom_id="legacy_world:city")
    async def legacy(self, interaction: discord.Interaction, button: discord.ui.Button):
        await edit_with_image(
            interaction, LEGACY_CITY,
            title="🏰 Altherya",
            description="Bienvenue à Altherya. Choisis ensuite ton lieu dans le système actuel de la ville.\n\n*Branche ici ton ancienne vue de ville si elle possède déjà ses propres boutons.*",
            view=LegacyCityBridgeView(),
        )

    @discord.ui.button(label="La Forge de KHAZ'GORAM", emoji="⚒️", style=discord.ButtonStyle.secondary, custom_id="legacy_world:forge")
    async def forge(self, interaction: discord.Interaction, button: discord.ui.Button):
        await edit_with_image(
            interaction, KHAZ_GORAM,
            title="⚒️ La Forge de KHAZ'GORAM",
            description="Le métal façonne les légendes. Au cœur de la montagne, Thorgar attend ceux qui veulent dépasser leurs limites.",
            view=KhazGoramView(),
        )


class LegacyCityBridgeView(discord.ui.View):
    """Pont temporaire vers la ville Altherya existante.

    Remplace le callback entrer_ville() par ta vue Altherya actuelle si ton bot la possède déjà.
    Le bouton Monde est déjà prêt.
    """
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Entrer dans Altherya", emoji="🏰", style=discord.ButtonStyle.primary, custom_id="legacy_city:enter")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "🏰 **Altherya est ouverte.** Branche ici ta vue actuelle de la ville (Taverne, Marché, Château, Banque, Arène, Expéditions, Ruelle sombre).",
            ephemeral=True,
        )

    @discord.ui.button(label="Monde", emoji="🌍", style=discord.ButtonStyle.secondary, custom_id="legacy_city:world")
    async def world(self, interaction: discord.Interaction, button: discord.ui.Button):
        await edit_with_image(interaction, WORLD_MAP, title="🌍 Le Monde d'Elyndor", description="Trois régions sont actuellement révélées : Altherya, KHAZ'GORAM et la Tour d’Ashkar.", view=WorldView())


class KhazGoramView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Parler à Thorgar", emoji="🧔", style=discord.ButtonStyle.primary, custom_id="khaz:thorgar")
    async def thorgar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await edit_with_image(
            interaction, THORGAR,
            title="⚒️ Thorgar — Maître Forgeron",
            description="« Bienvenue à la Forge des Légendes, voyageur. Ici, nous façonnons bien plus que de simples armes. »",
            view=ThorgarView(interaction.user.id),
        )

    @discord.ui.button(label="Monde", emoji="🌍", style=discord.ButtonStyle.secondary, custom_id="khaz:world")
    async def world(self, interaction: discord.Interaction, button: discord.ui.Button):
        await edit_with_image(interaction, WORLD_MAP, title="🌍 Le Monde d'Elyndor", description="Trois régions sont actuellement révélées : Altherya, KHAZ'GORAM et la Tour d’Ashkar.", view=WorldView())

# ============================================================
# FORGE VIEWS
# ============================================================
class ThorgarView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Cette interaction appartient à un autre joueur.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Acheter", emoji="🪙", style=discord.ButtonStyle.success)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        gold, pouciel = await DB.wallet(self.owner_id)
        eq = await DB.get_equipment(self.owner_id)
        view = BuySetCarousel(self.owner_id, eq)
        path = render_set_carousel(view.branch, mode="buy", eq=eq)
        await send_with_image(
            interaction, path,
            title="🪙 Thorgar — Choisir un set",
            description=view.description() + f"\n\nSolde : **{gold:,} Gold**",
            view=view, ephemeral=True,
        )

    @discord.ui.button(label="Améliorer", emoji="⚒️", style=discord.ButtonStyle.primary)
    async def upgrade(self, interaction: discord.Interaction, button: discord.ui.Button):
        gold, pouciel = await DB.wallet(self.owner_id)
        eq = await DB.get_equipment(self.owner_id)
        view = UpgradeSetCarousel(self.owner_id, eq)
        path = render_set_carousel(view.branch, mode="upgrade", eq=eq)
        await send_with_image(
            interaction, path,
            title="⚒️ Thorgar — Choisir un set",
            description=view.description() + f"\n\nSolde : **{pouciel:,} Pouciel**",
            view=view, ephemeral=True,
        )

    @discord.ui.button(label="Équipement", emoji="🧰", style=discord.ButtonStyle.secondary)
    async def equipment(self, interaction: discord.Interaction, button: discord.ui.Button):
        eq = await DB.get_equipment(self.owner_id)
        stats = stats_from_equipment(eq)
        path = render_equipment_grid(self.owner_id, interaction.user.display_name, eq, stats)
        gold, pouciel = await DB.wallet(self.owner_id)
        file = discord.File(path, filename=path.name)
        embed = discord.Embed(title="🧰 Équipement 3×3", description=f"🪙 {gold:,} Gold   •   🔷 {pouciel:,} Pouciel", color=0xB67A2A)
        embed.set_image(url=f"attachment://{path.name}")
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    @discord.ui.button(label="Monde", emoji="🌍", style=discord.ButtonStyle.secondary)
    async def world(self, interaction: discord.Interaction, button: discord.ui.Button):
        await edit_with_image(interaction, WORLD_MAP, title="🌍 Le Monde d'Elyndor", description="Trois régions sont actuellement révélées : Altherya, KHAZ'GORAM et la Tour d’Ashkar.", view=WorldView())


# ============================================================
# DOUBLE CAROUSEL — ACHAT / AMÉLIORATION
# ============================================================
CAROUSEL_BRANCHES = ["atk", "def", "speed"]


def available_buy_slots(eq: Dict[str, dict], branch: str) -> List[str]:
    # Un emplacement déjà équipé ne peut jamais être racheté : il disparaît du shop.
    return [s for s in BASE_SLOTS if s not in eq and (branch, "commun", s) in CATALOG]


def has_mythic_unlock(eq: Dict[str, dict]) -> bool:
    """Débloque les 3 emplacements avancés après avoir atteint le Mythique au moins une fois.

    Une pièce Légendaire compte aussi : elle a forcément traversé le palier Mythique.
    """
    return any(TIER_INDEX.get(data.get("tier"), -1) >= TIER_INDEX["mythique"] for data in eq.values())


def available_upgrade_slots(eq: Dict[str, dict], branch: str) -> List[str]:
    result: List[str] = []
    advanced_unlocked = has_mythic_unlock(eq)
    for slot in SLOTS:
        data = eq.get(slot)
        if data:
            if data["branch"] != branch or data["tier"] == "legendaire":
                continue
            nxt = TIER_ORDER[TIER_INDEX[data["tier"]] + 1]
            if (branch, nxt, slot) in CATALOG:
                result.append(slot)
        elif advanced_unlocked and slot in ADVANCED_SLOTS and (branch, "mythique", slot) in CATALOG:
            # Casque / Gantelets / Bottes naissent directement au Mythique,
            # mais seulement après que le joueur a atteint au moins une pièce Mythique.
            result.append(slot)
    return result


def _preview_background(title: str, subtitle: str):
    w, h = 1050, 620
    img = Image.new("RGB", (w, h), (18, 14, 11))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((14, 14, w-14, h-14), radius=24, fill=(29, 22, 17), outline=(181, 123, 44), width=4)
    draw.text((42, 34), title, font=get_font(38, True), fill=(239, 201, 116))
    draw.text((42, 86), subtitle, font=get_font(20), fill=(210, 202, 186))
    return img, draw


def render_set_carousel(branch: str, *, mode: str, eq: Dict[str, dict]) -> Path:
    """Carte visuelle du premier carrousel : choix du set."""
    branch_name = BRANCH_LABELS[branch]
    if mode == "buy":
        tier = "commun"
        set_name = SET_NAMES[branch][tier]
        slots = available_buy_slots(eq, branch)
        subtitle = f"{set_name} • Commun • {len(slots)} pièce(s) encore disponible(s)"
        title = f"{branch_name} — {set_name}"
        shown = BASE_SLOTS
    else:
        slots = available_upgrade_slots(eq, branch)
        title = f"{branch_name} — Forge"
        subtitle = f"{len(slots)} amélioration(s) disponible(s) dans cette voie"
        shown = [s for s in SLOTS if s in eq and eq[s]["branch"] == branch]
        # Les 3 pièces avancées n'apparaissent qu'après le premier palier Mythique atteint.
        if has_mythic_unlock(eq):
            shown += [s for s in ADVANCED_SLOTS if s not in eq and (branch, "mythique", s) in CATALOG]

    img, draw = _preview_background(title, subtitle)
    card_w, card_h, gap = 145, 185, 15
    max_cols = 6
    shown = shown[:9]
    total_width = min(len(shown), max_cols) * card_w + max(0, min(len(shown), max_cols)-1) * gap
    sx = max(40, (1050-total_width)//2)
    sy = 155
    for i, slot in enumerate(shown):
        row, col = divmod(i, max_cols)
        x = sx + col*(card_w+gap)
        y = sy + row*(card_h+18)
        data = eq.get(slot)
        if mode == "buy":
            tier = "commun"
            asset = CATALOG.get((branch, tier, slot))
            enabled = slot in slots
            tier_text = "Commun"
        else:
            if data:
                tier = data["tier"]
                asset = CATALOG.get((branch, tier, slot))
                enabled = slot in slots
                tier_text = TIER_LABELS[tier]
            else:
                tier = "mythique"
                asset = CATALOG.get((branch, tier, slot))
                enabled = slot in slots
                tier_text = "→ Mythique"
        border = (181, 123, 44) if enabled else (75, 68, 62)
        draw.rounded_rectangle((x, y, x+card_w, y+card_h), radius=15, fill=(8,8,9), outline=border, width=3)
        if asset and asset.path.exists():
            try:
                art = Image.open(asset.path).convert("RGBA")
                art.thumbnail((112, 112), Image.Resampling.LANCZOS)
                px = x + (card_w-art.width)//2
                img.paste(art, (px, y+15), art)
            except Exception:
                pass
        label = SLOT_LABELS[slot]
        draw.text((x+10, y+132), label, font=get_font(17, True), fill=(232,220,194))
        draw.text((x+10, y+155), tier_text, font=get_font(15), fill=((225,191,112) if enabled else (120,115,108)))

    if mode == "upgrade" and not has_mythic_unlock(eq):
        footer = "🔒 Casque, Gantelets et Bottes : débloqués après votre première pièce Mythique"
    else:
        footer = "◀ / ▶ pour changer de set • Sélectionner pour continuer"
    draw.text((42, 575), footer, font=get_font(18), fill=(174,163,145))
    out = RENDER_DIR / f"forge_{mode}_set_{branch}.png"
    img.save(out, quality=95)
    return out


def render_piece_carousel(branch: str, slot: str, *, mode: str, eq: Dict[str, dict]) -> Path:
    """Carte visuelle du second carrousel : choix de la pièce."""
    if mode == "buy":
        tier = "commun"
        price = COMMON_GOLD_PRICES[slot]
        set_name = SET_NAMES[branch][tier]
        title = pretty_item_name(branch, tier, slot)
        subtitle = f"Set {set_name} • {price:,} Gold • Équipement automatique"
        asset = CATALOG.get((branch, tier, slot))
        hp_add, spec_add = piece_contribution(slot, tier)
        action = "ACHETER"
    else:
        data = eq.get(slot)
        if data:
            old_tier = data["tier"]
            tier = TIER_ORDER[TIER_INDEX[old_tier] + 1]
            cost = POUCIEL_UPGRADE_COST[tier]
            title = f"{SLOT_LABELS[slot]} — {TIER_LABELS[old_tier]} → {TIER_LABELS[tier]}"
            subtitle = f"{SET_NAMES[branch][tier]} • {cost:,} Pouciel • Remplace la pièce précédente"
        else:
            old_tier = None
            tier = "mythique"
            cost = NEW_MYTHIC_COST
            title = f"{SLOT_LABELS[slot]} — Forger Mythique"
            subtitle = f"{SET_NAMES[branch][tier]} • {cost:,} Pouciel • Nouvelle pièce"
        asset = CATALOG.get((branch, tier, slot))
        hp_add, spec_add = piece_contribution(slot, tier)
        action = "AMÉLIORER"

    img, draw = _preview_background(title, subtitle)
    # grande carte de l'objet
    draw.rounded_rectangle((85, 145, 500, 525), radius=22, fill=(8,8,9), outline=(181,123,44), width=4)
    if asset and asset.path.exists():
        try:
            art = Image.open(asset.path).convert("RGBA")
            art.thumbnail((320, 320), Image.Resampling.LANCZOS)
            img.paste(art, (292-art.width//2, 330-art.height//2), art)
        except Exception:
            pass

    stat_name = "ATK" if branch == "atk" else "DEF" if branch == "def" else "VITESSE"
    x = 560
    draw.text((x, 170), "BONUS DE LA PIÈCE", font=get_font(24, True), fill=(239,201,116))
    draw.text((x, 225), "❤️ PV : selon niveau", font=get_font(23), fill=(231,225,214))
    draw.text((x, 270), f"{BRANCH_LABELS[branch].split(' ',1)[0]} {stat_name} : +{spec_add:.2f}%", font=get_font(23), fill=(231,225,214))
    if mode == "upgrade" and eq.get(slot):
        old = eq[slot]["tier"]
        old_hp, old_spec = piece_contribution(slot, old)
        draw.text((x, 335), "GAIN DE L'AMÉLIORATION", font=get_font(22, True), fill=(239,201,116))
        draw.text((x, 378), "PV : progression par niveau", font=get_font(20), fill=(210,202,186))
        draw.text((x, 412), f"{stat_name} : +{max(0,spec_add-old_spec):.2f}%", font=get_font(20), fill=(210,202,186))
    draw.text((x, 478), f"{action}  •  ◀ / ▶ pour parcourir", font=get_font(18, True), fill=(181,123,44))

    out = RENDER_DIR / f"forge_{mode}_{branch}_{slot}.png"
    img.save(out, quality=95)
    return out


async def _edit_carousel(interaction: discord.Interaction, image_path: Path, *, title: str, description: str, view: discord.ui.View):
    file = discord.File(image_path, filename=image_path.name)
    embed = discord.Embed(title=title, description=description, color=0xB67A2A)
    embed.set_image(url=f"attachment://{image_path.name}")
    if not interaction.response.is_done():
        await interaction.response.edit_message(embed=embed, attachments=[file], view=view)
    else:
        await interaction.edit_original_response(embed=embed, attachments=[file], view=view)


class ForgeOwnerView(discord.ui.View):
    def __init__(self, owner_id: int, timeout=180):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Ce menu n'est pas le tien.", ephemeral=True)
            return False
        return True


class BuySetCarousel(ForgeOwnerView):
    def __init__(self, owner_id: int, eq: Dict[str, dict], index: int = 0):
        super().__init__(owner_id)
        self.eq = eq
        self.index = index % len(CAROUSEL_BRANCHES)

    @property
    def branch(self): return CAROUSEL_BRANCHES[self.index]

    def description(self):
        b = self.branch
        slots = available_buy_slots(self.eq, b)
        set_name = SET_NAMES[b]["commun"]
        if slots:
            total = sum(COMMON_GOLD_PRICES[s] for s in slots)
            return f"**Set {set_name} — {BRANCH_LABELS[b]}**\n{len(slots)} pièce(s) disponible(s) • coût restant : **{total:,} Gold**"
        return f"**Set {set_name} — {BRANCH_LABELS[b]}**\n✅ Toutes les pièces achetables de ce set sont déjà équipées ou leurs emplacements sont occupés."

    async def show(self, interaction):
        await _edit_carousel(interaction, render_set_carousel(self.branch, mode="buy", eq=self.eq), title="🪙 Thorgar — Choisir un set", description=self.description(), view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        self.index = (self.index - 1) % len(CAROUSEL_BRANCHES); await self.show(interaction)

    @discord.ui.button(label="Sélectionner ce set", emoji="✅", style=discord.ButtonStyle.primary)
    async def choose(self, interaction, button):
        slots = available_buy_slots(self.eq, self.branch)
        if not slots:
            return await interaction.response.send_message("Aucune pièce n'est disponible dans ce set.", ephemeral=True)
        view = BuyPieceCarousel(self.owner_id, self.branch, self.eq)
        await view.show(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):
        self.index = (self.index + 1) % len(CAROUSEL_BRANCHES); await self.show(interaction)

    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back_to_thorgar(self, interaction, button):
        await _edit_carousel(
            interaction, THORGAR,
            title="⚒️ Thorgar — Maître Forgeron",
            description="« Bienvenue à la Forge des Légendes, voyageur. Ici, nous façonnons bien plus que de simples armes. »",
            view=ThorgarView(self.owner_id),
        )


class BuyPieceCarousel(ForgeOwnerView):
    def __init__(self, owner_id: int, branch: str, eq: Dict[str, dict], index: int = 0):
        super().__init__(owner_id)
        self.branch = branch
        self.eq = eq
        self.slots = available_buy_slots(eq, branch)
        self.index = 0 if not self.slots else index % len(self.slots)

    @property
    def slot(self): return self.slots[self.index] if self.slots else None

    async def show(self, interaction, notice: str = ""):
        if not self.slots:
            parent = BuySetCarousel(self.owner_id, self.eq, CAROUSEL_BRANCHES.index(self.branch))
            desc = "✅ **Plus aucune pièce disponible dans ce set.**\nLa pièce achetée a été retirée du magasin." + (f"\n\n{notice}" if notice else "")
            return await _edit_carousel(interaction, render_set_carousel(self.branch, mode="buy", eq=self.eq), title="🪙 Set terminé", description=desc, view=parent)
        slot = self.slot
        price = COMMON_GOLD_PRICES[slot]
        gold, _ = await DB.wallet(self.owner_id)
        desc = f"**{pretty_item_name(self.branch,'commun',slot)}**\nPrix : **{price:,} Gold** • Solde : **{gold:,} Gold**\nUne fois achetée, la pièce disparaît immédiatement du shop."
        if notice: desc = notice + "\n\n" + desc
        await _edit_carousel(interaction, render_piece_carousel(self.branch, slot, mode="buy", eq=self.eq), title="🛒 Choisir une pièce", description=desc, view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        self.index = (self.index - 1) % len(self.slots); await self.show(interaction)

    @discord.ui.button(label="Acheter", emoji="🪙", style=discord.ButtonStyle.success)
    async def buy_piece(self, interaction, button):
        slot = self.slot
        if not slot:
            return await interaction.response.send_message("Aucune pièce disponible.", ephemeral=True)
        price = COMMON_GOLD_PRICES[slot]
        status = await DB.purchase_common_piece(self.owner_id, slot, self.branch, price)
        if status == "gold":
            return await interaction.response.send_message("❌ Pas assez de Gold.", ephemeral=True)
        if status == "owned":
            notice = "ℹ️ Cette pièce était déjà équipée : elle a été retirée du shop sans nouvel achat."
        else:
            notice = f"✅ **{pretty_item_name(self.branch,'commun',slot)}** acheté pour **{price:,} Gold** et équipé automatiquement."
        self.eq = await DB.get_equipment(self.owner_id)
        self.slots = available_buy_slots(self.eq, self.branch)
        if self.slots:
            self.index %= len(self.slots)
        else:
            self.index = 0
        await self.show(interaction, notice)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):
        self.index = (self.index + 1) % len(self.slots); await self.show(interaction)

    @discord.ui.button(label="Sets", emoji="↩️", style=discord.ButtonStyle.primary)
    async def back(self, interaction, button):
        self.eq = await DB.get_equipment(self.owner_id)
        view = BuySetCarousel(self.owner_id, self.eq, CAROUSEL_BRANCHES.index(self.branch))
        await view.show(interaction)


class UpgradeSetCarousel(ForgeOwnerView):
    def __init__(self, owner_id: int, eq: Dict[str, dict], index: int = 0):
        super().__init__(owner_id)
        self.eq = eq
        self.index = index % len(CAROUSEL_BRANCHES)

    @property
    def branch(self): return CAROUSEL_BRANCHES[self.index]

    def description(self):
        b = self.branch
        slots = available_upgrade_slots(self.eq, b)
        lock_hint = "" if has_mythic_unlock(self.eq) else "\n🔒 Casque, Gantelets et Bottes se débloquent après votre première pièce Mythique."
        if slots:
            return f"**{BRANCH_LABELS[b]}**\n{len(slots)} pièce(s) peuvent être forgées ou améliorées dans cette voie.{lock_hint}"
        return f"**{BRANCH_LABELS[b]}**\nAucune amélioration disponible pour le moment.{lock_hint}"

    async def show(self, interaction):
        await _edit_carousel(interaction, render_set_carousel(self.branch, mode="upgrade", eq=self.eq), title="⚒️ Thorgar — Choisir un set", description=self.description(), view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        self.index = (self.index - 1) % len(CAROUSEL_BRANCHES); await self.show(interaction)

    @discord.ui.button(label="Sélectionner ce set", emoji="✅", style=discord.ButtonStyle.primary)
    async def choose(self, interaction, button):
        slots = available_upgrade_slots(self.eq, self.branch)
        if not slots:
            return await interaction.response.send_message("Aucune pièce de ce set n'est améliorable.", ephemeral=True)
        view = UpgradePieceCarousel(self.owner_id, self.branch, self.eq)
        await view.show(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):
        self.index = (self.index + 1) % len(CAROUSEL_BRANCHES); await self.show(interaction)

    @discord.ui.button(label="Retour", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
    async def back_to_thorgar(self, interaction, button):
        await _edit_carousel(
            interaction, THORGAR,
            title="⚒️ Thorgar — Maître Forgeron",
            description="« Bienvenue à la Forge des Légendes, voyageur. Ici, nous façonnons bien plus que de simples armes. »",
            view=ThorgarView(self.owner_id),
        )


class UpgradePieceCarousel(ForgeOwnerView):
    def __init__(self, owner_id: int, branch: str, eq: Dict[str, dict], index: int = 0):
        super().__init__(owner_id)
        self.branch = branch
        self.eq = eq
        self.slots = available_upgrade_slots(eq, branch)
        self.index = 0 if not self.slots else index % len(self.slots)

    @property
    def slot(self): return self.slots[self.index] if self.slots else None

    def current_cost_and_tier(self):
        slot = self.slot
        data = self.eq.get(slot)
        if data:
            nxt = TIER_ORDER[TIER_INDEX[data["tier"]] + 1]
            return POUCIEL_UPGRADE_COST[nxt], nxt
        return NEW_MYTHIC_COST, "mythique"

    async def show(self, interaction, notice: str = ""):
        if not self.slots:
            parent = UpgradeSetCarousel(self.owner_id, self.eq, CAROUSEL_BRANCHES.index(self.branch))
            desc = "✅ **Aucune autre amélioration disponible dans ce set.**" + (f"\n\n{notice}" if notice else "")
            return await _edit_carousel(interaction, render_set_carousel(self.branch, mode="upgrade", eq=self.eq), title="⚒️ Forge", description=desc, view=parent)
        slot = self.slot
        cost, nxt = self.current_cost_and_tier()
        _, pouciel = await DB.wallet(self.owner_id)
        old = self.eq.get(slot)
        transition = f"{TIER_LABELS[old['tier']]} → {TIER_LABELS[nxt]}" if old else f"Nouvelle pièce → {TIER_LABELS[nxt]}"
        desc = f"**{SLOT_LABELS[slot]} • {transition}**\nCoût : **{cost:,} Pouciel** • Solde : **{pouciel:,} Pouciel**\nLa nouvelle version remplace automatiquement l'ancienne."
        if notice: desc = notice + "\n\n" + desc
        await _edit_carousel(interaction, render_piece_carousel(self.branch, slot, mode="upgrade", eq=self.eq), title="🔥 Choisir une amélioration", description=desc, view=self)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction, button):
        self.index = (self.index - 1) % len(self.slots); await self.show(interaction)

    @discord.ui.button(label="Améliorer", emoji="⚒️", style=discord.ButtonStyle.primary)
    async def forge_piece(self, interaction, button):
        slot = self.slot
        if not slot:
            return await interaction.response.send_message("Aucune amélioration disponible.", ephemeral=True)
        status, old_tier, new_tier, cost = await DB.forge_upgrade_piece(self.owner_id, slot, self.branch)
        if status == "pouciel":
            return await interaction.response.send_message(f"❌ Pas assez de Pouciel. Il faut **{cost:,}**.", ephemeral=True)
        if status in {"max", "wrong_set", "missing", "asset", "mythic_locked"}:
            messages = {
                "max": "Cette pièce est déjà Légendaire.",
                "wrong_set": "Cette pièce appartient désormais à un autre set.",
                "missing": "Cette pièce n'est pas encore disponible à la forge.",
                "asset": "L'asset de cette amélioration est introuvable.",
                "mythic_locked": "Casque, Gantelets et Bottes se débloquent seulement après avoir obtenu au moins une pièce Mythique.",
            }
            return await interaction.response.send_message(f"❌ {messages[status]}", ephemeral=True)
        item_name = pretty_item_name(self.branch,new_tier,slot)
        notice = f"🔥 **{item_name}** forgé pour **{cost:,} Pouciel** ! La nouvelle pièce a remplacé l'ancienne."
        CASTLE.record(self.owner_id, "forge_upgrade", 1)
        if new_tier == "legendaire":
            GAZETTE.record_event("legendary_forge", self.owner_id, 0, item_name)
        self.eq = await DB.get_equipment(self.owner_id)
        self.slots = available_upgrade_slots(self.eq, self.branch)
        if self.slots:
            self.index %= len(self.slots)
        else:
            self.index = 0
        await self.show(interaction, notice)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction, button):
        self.index = (self.index + 1) % len(self.slots); await self.show(interaction)

    @discord.ui.button(label="Sets", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction, button):
        self.eq = await DB.get_equipment(self.owner_id)
        view = UpgradeSetCarousel(self.owner_id, self.eq, CAROUSEL_BRANCHES.index(self.branch))
        await view.show(interaction)

# ============================================================
# COMBAT ENGINE + ARENA / PVP
# ============================================================
@dataclass
class Combatant:
    user_id: int
    name: str
    stats: FighterStats
    hp: int
    guard: bool = False
    power_cd: int = 0
    is_npc: bool = False


class FightView(discord.ui.View):
    def __init__(self, a: Combatant, b: Combatant, *, champion_level: Optional[int] = None):
        super().__init__(timeout=300)
        self.a = a; self.b = b
        self.turn_user_id = self._first_turn()
        self.champion_level = champion_level
        self.finished = False

    def _first_turn(self):
        # avantage vitesse sans rendre l'initiative automatique à 100%
        diff = self.a.stats.speed - self.b.stats.speed
        p_a = min(0.75, max(0.25, 0.50 + diff*0.02))
        return self.a.user_id if random.random() < p_a else self.b.user_id

    def _embed(self, log: str = "Le combat commence !"):
        e = discord.Embed(title="⚔️ Combat", description=log, color=0x9B2C20)
        e.add_field(name=self.a.name, value=f"❤️ **{max(0,self.a.hp)} / {self.a.stats.hp}**\n⚔️ {self.a.stats.atk}  🛡️ {self.a.stats.defense}  💨 {self.a.stats.speed}", inline=True)
        e.add_field(name=self.b.name, value=f"❤️ **{max(0,self.b.hp)} / {self.b.stats.hp}**\n⚔️ {self.b.stats.atk}  🛡️ {self.b.stats.defense}  💨 {self.b.stats.speed}", inline=True)
        if not self.finished:
            who = self.a.name if self.turn_user_id == self.a.user_id else self.b.name
            e.set_footer(text=f"Tour de {who}")
        return e

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.finished:
            await interaction.response.send_message("Le combat est terminé.", ephemeral=True); return False
        if interaction.user.id != self.turn_user_id:
            await interaction.response.send_message("Ce n'est pas ton tour.", ephemeral=True); return False
        return True

    def current_pair(self):
        return (self.a,self.b) if self.turn_user_id == self.a.user_id else (self.b,self.a)

    async def do_attack(self, interaction: discord.Interaction, power: float, label: str):
        attacker, defender = self.current_pair()
        if power > 1 and attacker.power_cd > 0:
            return await interaction.response.send_message(f"Coup puissant disponible dans {attacker.power_cd} tour(s).", ephemeral=True)
        if power > 1:
            attacker.power_cd = 3
            # 75% hit chance for power strike; dodge handled after hit check
            if random.random() > 0.75:
                log = f"💨 **{attacker.name}** tente un coup puissant… et manque sa cible !"
                await self.advance(interaction, attacker, defender, log)
                return
        dmg, crit, dodge = damage_roll(attacker.stats, defender.stats, power=power, guard=defender.guard)
        defender.guard = False
        if dodge:
            log = f"💨 **{defender.name} esquive** l'attaque de {attacker.name}."
        else:
            defender.hp -= dmg
            log = f"{label} **{attacker.name}** inflige **{dmg} dégâts** à {defender.name}."
            if crit: log += " 💥 **CRITIQUE !**"
        await self.advance(interaction, attacker, defender, log)

    async def advance(self, interaction, attacker, defender, log):
        if attacker.power_cd > 0: attacker.power_cd -= 1
        if defender.hp <= 0:
            self.finished = True
            for child in self.children: child.disabled = True
            winner, loser = attacker, defender
            log += f"\n\n🏆 **{winner.name} remporte le combat !**"
            if self.champion_level and not winner.is_npc:
                reward = CHAMPIONS[self.champion_level]["reward"]
                await DB.add_currency(winner.user_id, gold=reward)
                await DB.record_champion_win(winner.user_id, self.champion_level)
                log += f"\n🪙 Récompense : **{reward:,} Gold**"
            elif not winner.is_npc and not loser.is_npc:
                await DB.record_pvp(winner.user_id, loser.user_id)
            await interaction.response.edit_message(embed=self._embed(log), view=self)
            return

        self.turn_user_id = defender.user_id
        await interaction.response.edit_message(embed=self._embed(log), view=self)
        if defender.is_npc and not self.finished:
            await asyncio.sleep(1.0)
            await self.npc_turn(interaction.message)

    async def npc_turn(self, message: discord.Message):
        attacker, defender = self.current_pair()
        # Champion : petite IA, garde parfois, coup puissant rarement.
        if random.random() < 0.16:
            attacker.guard = True
            log = f"🛡️ **{attacker.name} se met en garde.**"
            self.turn_user_id = defender.user_id
            await message.edit(embed=self._embed(log), view=self)
            return
        power = 1.35 if random.random() < 0.20 and attacker.power_cd == 0 else 1.0
        if power > 1: attacker.power_cd = 3
        dmg, crit, dodge = damage_roll(attacker.stats, defender.stats, power=power, guard=defender.guard)
        defender.guard = False
        if dodge: log = f"💨 **{defender.name} esquive** l'attaque de {attacker.name}."
        else:
            defender.hp -= dmg
            log = f"⚔️ **{attacker.name}** inflige **{dmg} dégâts** à {defender.name}."
            if power > 1: log += " 🔥 Coup puissant !"
            if crit: log += " 💥 **CRITIQUE !**"
        if attacker.power_cd > 0: attacker.power_cd -= 1
        if defender.hp <= 0:
            self.finished = True
            for child in self.children: child.disabled = True
            log += f"\n\n🏆 **{attacker.name} remporte le combat !**"
            await message.edit(embed=self._embed(log), view=self); return
        self.turn_user_id = defender.user_id
        await message.edit(embed=self._embed(log), view=self)

    @discord.ui.button(label="Attaquer", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def attack(self, interaction, button):
        await self.do_attack(interaction, 1.0, "⚔️")

    @discord.ui.button(label="Coup puissant", emoji="🔥", style=discord.ButtonStyle.primary)
    async def power(self, interaction, button):
        await self.do_attack(interaction, 1.35, "🔥")

    @discord.ui.button(label="Garde", emoji="🛡️", style=discord.ButtonStyle.secondary)
    async def guard_btn(self, interaction, button):
        attacker, defender = self.current_pair()
        attacker.guard = True
        await self.advance(interaction, attacker, defender, f"🛡️ **{attacker.name} se met en garde** et réduira de moitié le prochain coup reçu.")

    @discord.ui.button(label="Abandonner", emoji="🏳️", style=discord.ButtonStyle.secondary)
    async def surrender(self, interaction, button):
        attacker, defender = self.current_pair()
        self.finished = True
        for child in self.children: child.disabled = True
        if not defender.is_npc and not attacker.is_npc:
            await DB.record_pvp(defender.user_id, attacker.user_id)
        await interaction.response.edit_message(embed=self._embed(f"🏳️ **{attacker.name} abandonne. {defender.name} remporte le combat.**"), view=self)


class ChampionSelect(discord.ui.Select):
    def __init__(self, owner_id: int):
        self.owner_id = owner_id
        options = []
        for i,c in CHAMPIONS.items():
            reco = ["Débutant","Commun","Commun","Commun complet","Rare","Rare/Épique","Épique","Mythique","Mythique/Légendaire","Légendaire"][i-1]
            options.append(discord.SelectOption(label=c["name"], value=str(i), description=f"Stuff conseillé : {reco}"))
        super().__init__(placeholder="Choisir Champion I → X", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("Ce menu n'est pas le tien.", ephemeral=True)
        level = int(self.values[0]); c = CHAMPIONS[level]
        eq = await DB.get_equipment(self.owner_id); ps = stats_from_equipment(eq)
        cs = FighterStats(c["hp"],c["atk"],c["def"],c["speed"])
        p = Combatant(self.owner_id, interaction.user.display_name, ps, ps.hp)
        npc = Combatant(-level, c["name"], cs, cs.hp, is_npc=True)
        view = FightView(p,npc,champion_level=level)
        await interaction.response.send_message(embed=view._embed(f"🏟️ **{c['name']}** entre dans l'arène."), view=view)
        if view.turn_user_id == npc.user_id:
            await asyncio.sleep(1.0)
            msg = await interaction.original_response()
            await view.npc_turn(msg)


class ArenaView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.add_item(ChampionSelect(owner_id))


class DuelInviteView(discord.ui.View):
    def __init__(self, challenger: discord.Member, target: discord.Member):
        super().__init__(timeout=120)
        self.challenger = challenger; self.target = target

    @discord.ui.button(label="Accepter", emoji="⚔️", style=discord.ButtonStyle.danger)
    async def accept(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.target.id:
            return await interaction.response.send_message("Seul le joueur défié peut accepter.", ephemeral=True)
        aeq = await DB.get_equipment(self.challenger.id); beq = await DB.get_equipment(self.target.id)
        ast = stats_from_equipment(aeq); bst = stats_from_equipment(beq)
        a = Combatant(self.challenger.id,self.challenger.display_name,ast,ast.hp)
        b = Combatant(self.target.id,self.target.display_name,bst,bst.hp)
        view = FightView(a,b)
        await interaction.response.edit_message(content=None, embed=view._embed("⚔️ **Le duel commence !**"), view=view)

    @discord.ui.button(label="Refuser", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.target.id:
            return await interaction.response.send_message("Seul le joueur défié peut refuser.", ephemeral=True)
        for c in self.children: c.disabled=True
        await interaction.response.edit_message(content="Défi refusé.", view=self)

# ============================================================
# COG / COMMANDS
# ============================================================
class LegacyWorldForge(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def legacy(self, interaction: discord.Interaction):
        await DB.ensure_user(interaction.user.id)
        await send_with_image(
            interaction, WORLD_MAP,
            title="🌍 Le Monde d'Elyndor",
            description="Le brouillard recouvre encore les terres inconnues. **Altherya**, **La Forge de KHAZ'GORAM** et **La Tour d’Ashkar** sont désormais révélées.",
            view=WorldView(),
        )

    @app_commands.command(name="equipement", description="Affiche ton équipement 3×3 et tes bonus")
    async def equipement(self, interaction: discord.Interaction):
        eq = await DB.get_equipment(interaction.user.id)
        stats = stats_from_equipment(eq)
        path = render_equipment_grid(interaction.user.id, interaction.user.display_name, eq, stats)
        gold,p = await DB.wallet(interaction.user.id)
        file = discord.File(path, filename=path.name)
        embed = discord.Embed(title="🧰 Ton équipement", description=f"🪙 {gold:,} Gold • 🔷 {p:,} Pouciel", color=0xB67A2A)
        embed.set_image(url=f"attachment://{path.name}")
        await interaction.response.send_message(embed=embed,file=file)

    async def arena(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "🏟️ **Arène — Champions I à X**\nLes Champions ont des statistiques fixes. Si tu bloques, améliore ton équipement à KHAZ'GORAM.",
            view=ArenaView(interaction.user.id), ephemeral=True,
        )

    async def duel(self, interaction: discord.Interaction, adversaire: discord.Member):
        if adversaire.bot or adversaire.id == interaction.user.id:
            return await interaction.response.send_message("Choisis un autre joueur humain.", ephemeral=True)
        await interaction.response.send_message(
            f"⚔️ {adversaire.mention}, **{interaction.user.display_name}** te défie en duel !",
            view=DuelInviteView(interaction.user, adversaire),
        )

    @app_commands.command(name="legacy_dev_wallet", description="[TEST] Ajoute Gold/Pouciel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def dev_wallet(self, interaction: discord.Interaction, membre: discord.Member, gold: int = 0, pouciel: int = 0):
        await DB.add_currency(membre.id,gold=gold,pouciel=pouciel)
        g,p = await DB.wallet(membre.id)
        await interaction.response.send_message(f"✅ {membre.mention} : {g:,} Gold / {p:,} Pouciel", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LegacyWorldForge(bot))
    # persistent world navigation after restart
    bot.add_view(WorldView())
    bot.add_view(LegacyCityBridgeView())
    bot.add_view(KhazGoramView())
