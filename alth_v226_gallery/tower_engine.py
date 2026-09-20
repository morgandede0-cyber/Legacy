from __future__ import annotations

import io
import random
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import discord
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

from castle_engine import CastleStore
from gazette_engine import GazetteStore
import legacy_world_forge as WORLD_FORGE
from arena_engine import CLASSES, class_line

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "legacy.sqlite3"
ASSET_DIR = BASE / "assets" / "tower"
ENEMY_DIR = ASSET_DIR / "enemies"
RENDER_DIR = BASE / "renders" / "tower"
RENDER_DIR.mkdir(parents=True, exist_ok=True)
CASTLE = CastleStore(DB_PATH)
GAZETTE = GazetteStore(DB_PATH)


def _v2_view(title: str, description: str, legacy_view: discord.ui.View | None = None, *, image: str | None = None, accent: int = 0x6D4B37):
    """Construit une surface Components V2 sans Embed ni Select visible."""
    out = discord.ui.LayoutView(timeout=getattr(legacy_view, "timeout", 900) if legacy_view else 900)
    children = [discord.ui.TextDisplay(f"# {title}\n{description}" if description else f"# {title}")]
    if image:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=f"attachment://{image}", description=title)
        children += [discord.ui.Separator(spacing=discord.SeparatorSpacing.small), gallery]
    buttons=[]
    if legacy_view is not None:
        for item in list(getattr(legacy_view, "children", [])):
            if isinstance(item, discord.ui.Button):
                buttons.append(item)
    for i in range(0, len(buttons), 5):
        children.append(discord.ui.ActionRow(*buttons[i:i+5]))
    out.add_item(discord.ui.Container(*children, accent_colour=accent))
    return out

async def _edit_v2(interaction, *, title, description, legacy_view=None, file=None, filename=None, accent=0x6D4B37):
    view=_v2_view(title, description, legacy_view, image=filename if file else None, accent=accent)
    await interaction.response.edit_message(content=None, attachments=[file] if file else [], view=view)

async def _send_v2(interaction, *, title, description, legacy_view=None, file=None, filename=None, ephemeral=True, accent=0x6D4B37):
    view=_v2_view(title, description, legacy_view, image=filename if file else None, accent=accent)
    await interaction.response.send_message(view=view, file=file, ephemeral=ephemeral)

# Récompenses modestes : une seule fois par étage.
FLOORS = {
    1:  dict(name="Rat des Profondeurs", hp=650,  atk=70,  defense=35, speed=94,  gold=10,  pouciel=0),
    2:  dict(name="Gobelin Pillard", hp=740,  atk=76,  defense=39, speed=102, gold=15,  pouciel=0),
    3:  dict(name="Squelette Errant", hp=830,  atk=82,  defense=44, speed=96,  gold=20,  pouciel=0),
    4:  dict(name="Garde Déchu", hp=930,  atk=88,  defense=50, speed=98,  gold=25,  pouciel=0),
    5:  dict(name="Orc des Cavernes", hp=1040, atk=94,  defense=54, speed=96,  gold=30,  pouciel=1),
    6:  dict(name="Berserker Orc", hp=1160, atk=101, defense=58, speed=101, gold=40,  pouciel=0),
    7:  dict(name="Chevalier Corrompu", hp=1290, atk=108, defense=64, speed=103, gold=50, pouciel=0),
    8:  dict(name="Golem d'Obsidienne", hp=1460, atk=115, defense=76, speed=88, gold=65, pouciel=0),
    9:  dict(name="Exécuteur des Abysses", hp=1630, atk=124, defense=72, speed=108, gold=85, pouciel=0),
    10: dict(name="Varkhaz, Gardien d'Ashkar", hp=1900, atk=138, defense=82, speed=110, gold=120, pouciel=3, boss=True),
}


def _font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _hp_color(ratio: float):
    if ratio > .50:
        return (75, 190, 78)
    if ratio > .20:
        return (225, 175, 55)
    return (205, 62, 52)


def _draw_bar(draw, box, ratio, *, outline=(225, 225, 225), fill_bg=(30, 30, 34)):
    x1, y1, x2, y2 = box
    ratio = max(0.0, min(1.0, ratio))
    draw.rounded_rectangle(box, radius=8, fill=fill_bg, outline=outline, width=2)
    inner = (x1 + 4, y1 + 4, x1 + 4 + int((x2 - x1 - 8) * ratio), y2 - 4)
    if inner[2] > inner[0]:
        draw.rounded_rectangle(inner, radius=5, fill=_hp_color(ratio))


def _circle_portrait(source: Image.Image, size: int, border=(222, 190, 111, 255), border_width=7) -> Image.Image:
    src = ImageOps.fit(source.convert("RGBA"), (size, size), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out = Image.new("RGBA", (size + border_width * 2, size + border_width * 2), (0, 0, 0, 0))
    od = ImageDraw.Draw(out)
    od.ellipse((0, 0, out.width - 1, out.height - 1), fill=(12, 15, 20, 245), outline=border, width=border_width)
    out.paste(src, (border_width, border_width), mask)
    return out


class TowerStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _c(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._c() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS ashkar_progress(
                user_id INTEGER PRIMARY KEY,
                max_floor INTEGER NOT NULL DEFAULT 0
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS ashkar_daily(
                user_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                cleared INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id, day)
            )''')
            c.commit()

    def progress(self, uid: int):
        with self._c() as c:
            c.execute("INSERT OR IGNORE INTO ashkar_progress(user_id) VALUES(?)", (int(uid),))
            row = c.execute("SELECT max_floor FROM ashkar_progress WHERE user_id=?", (int(uid),)).fetchone()
            c.commit()
            return int(row["max_floor"])

    def daily(self, uid: int):
        day = date.today().isoformat()
        with self._c() as c:
            c.execute("INSERT OR IGNORE INTO ashkar_daily(user_id,day) VALUES(?,?)", (int(uid), day))
            row = c.execute("SELECT cleared FROM ashkar_daily WHERE user_id=? AND day=?", (int(uid), day)).fetchone()
            c.commit()
            return int(row["cleared"])

    def can_attempt(self, uid: int, floor: int):
        max_floor = self.progress(uid)
        daily = self.daily(uid)
        if floor != max_floor + 1:
            return False, "locked"
        if daily >= 3:
            return False, "daily"
        if floor > 10:
            return False, "end"
        return True, "ok"

    async def validate(self, uid: int, floor: int):
        day = date.today().isoformat()
        global_before = 0
        with self._c() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT OR IGNORE INTO ashkar_progress(user_id) VALUES(?)", (int(uid),))
            c.execute("INSERT OR IGNORE INTO ashkar_daily(user_id,day) VALUES(?,?)", (int(uid), day))
            row = c.execute("SELECT max_floor FROM ashkar_progress WHERE user_id=?", (int(uid),)).fetchone()
            d = c.execute("SELECT cleared FROM ashkar_daily WHERE user_id=? AND day=?", (int(uid), day)).fetchone()
            g = c.execute("SELECT COALESCE(MAX(max_floor),0) AS m FROM ashkar_progress").fetchone()
            global_before = int(g["m"] if g else 0)
            current = int(row["max_floor"])
            cleared = int(d["cleared"])
            if floor != current + 1 or cleared >= 3:
                c.rollback()
                return False
            c.execute("UPDATE ashkar_progress SET max_floor=? WHERE user_id=?", (floor, int(uid)))
            c.execute("UPDATE ashkar_daily SET cleared=cleared+1 WHERE user_id=? AND day=?", (int(uid), day))
            c.commit()
        reward = FLOORS[floor]
        await WORLD_FORGE.DB.add_currency(uid, gold=reward["gold"], pouciel=reward["pouciel"])
        # Quêtes quotidiennes + Gazette sont alimentées par la vraie validation de l'étage.
        CASTLE.record(uid, "tower_clear", 1)
        if floor == 10:
            GAZETTE.record_event("ashkar_boss", uid, 10)
        if floor > global_before and floor >= 5:
            GAZETTE.record_event("ashkar_record", uid, floor)
        return True


STORE = TowerStore(DB_PATH)


@dataclass
class BattleState:
    owner_id: int
    floor: int
    class_key: str
    player_name: str
    player_level: int
    player_hp: int
    player_max_hp: int
    player_atk: int
    player_def: int
    player_speed: int
    equipment_def_pct: float
    enemy_hp: int
    enemy_max_hp: int
    enemy_atk: int
    enemy_def: int
    enemy_speed: int
    ultimate_cd: int = 0
    guarding: bool = False
    guard_reduction: float = 0.0
    temp_evade: float = 0.0
    next_damage_bonus: float = 0.0
    ravager_light_stacks: int = 0
    enemy_bleed: int = 0
    enemy_shaken: bool = False
    evaded_last_attack: bool = False
    enemy_enraged: bool = False
    log: str = "Le combat commence !"

    @property
    def class_cfg(self):
        return CLASSES[self.class_key]


def make_state(user: discord.abc.User, floor: int, class_key: str) -> BattleState:
    level = CASTLE.current_level(user.id)
    with sqlite3.connect(DB_PATH, timeout=10) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT slot,branch,tier FROM legacy_equipment WHERE user_id=?", (int(user.id),)).fetchall()
    eq = {r["slot"]: {"branch": r["branch"], "tier": r["tier"]} for r in rows}
    gear = WORLD_FORGE.stats_from_equipment(eq)
    cfg = CLASSES[class_key]

    # Même identité de classe que l'Arène, adaptée à l'échelle de PV de la Tour.
    lvl_scale = max(0, level - 1)
    class_hp_mult = cfg["hp"] / 100.0
    class_speed_mult = cfg["speed"] / 100.0
    hp = round((1000 + 35 * lvl_scale) * class_hp_mult)
    atk = round(gear.atk * cfg["attack"] * (1 + 0.025 * lvl_scale))
    defense = round(gear.defense + 3 * lvl_scale)
    speed = round(gear.speed * class_speed_mult + 1.2 * lvl_scale)
    e = FLOORS[floor]
    return BattleState(
        user.id, floor, class_key, user.display_name, level,
        hp, hp, atk, defense, speed, gear.def_bonus_pct,
        e["hp"], e["hp"], e["atk"], e["defense"], e["speed"]
    )


def _enemy_damage(atk: int, defense: int, reduction: float = 0.0, *, power=1.0):
    mitigation = 100 / (100 + max(0, defense))
    raw = atk * mitigation * power * random.uniform(.90, 1.10)
    raw *= max(0.05, 1.0 - reduction)
    crit = random.random() < .06
    if crit:
        raw *= 1.5
    return max(1, round(raw)), crit


def _player_damage(state: BattleState, action: str):
    cfg = state.class_cfg
    skill = cfg["skills"][action]
    # Conversion des puissances de l'Arène vers l'échelle de la Tour.
    skill_mult = skill["power"] / 14.0
    mult = skill_mult
    if state.next_damage_bonus:
        mult *= 1 + state.next_damage_bonus
        state.next_damage_bonus = 0.0
    if state.class_key == "traqueur" and action == "heavy" and state.evaded_last_attack:
        mult *= 1.30
        state.evaded_last_attack = False
    mitigation = 100 / (100 + max(0, state.enemy_def))
    raw = state.player_atk * mitigation * mult * random.uniform(.94, 1.06)
    crit = action == "ultimate" and random.random() < .50
    if crit:
        raw *= 1.60
    return max(1, round(raw)), crit


def _enemy_dodges(state: BattleState, action: str):
    if action == "light":
        return False
    skill = state.class_cfg["skills"][action]
    if random.random() > skill.get("accuracy", 1.0):
        return True
    speed_gap = max(0, state.enemy_speed - state.player_speed)
    chance = min(.14, .02 + speed_gap * .0025)
    return random.random() < chance


def _player_dodges(state: BattleState):
    cfg = state.class_cfg
    speed_gap = max(0, state.player_speed - state.enemy_speed)
    equip_evade = min(.05, max(0.0, (state.player_speed - 100) / 2000.0))
    chance = min(.15, cfg["evade"] + state.temp_evade + equip_evade + speed_gap * .0015)
    dodged = random.random() < chance
    state.evaded_last_attack = dodged
    return dodged


async def render_battle(state: BattleState, avatar_bytes: bytes | None) -> Path:
    W, H = 1280, 720
    poster = ASSET_DIR / "tower_poster.png"
    if poster.exists():
        bg = Image.open(poster).convert("RGB")
        bg = ImageOps.fit(bg, (W, H), method=Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(8))
        shade = Image.new("RGBA", (W, H), (8, 12, 18, 145))
        bg = Image.alpha_composite(bg.convert("RGBA"), shade).convert("RGB")
    else:
        bg = Image.new("RGB", (W, H), (23, 28, 34))

    img = bg.convert("RGBA")
    draw = ImageDraw.Draw(img)
    f26 = _font(26, True)
    f22 = _font(22)
    f18 = _font(18)
    f16 = _font(16)

    # Plaque étage au centre haut.
    draw.rounded_rectangle((475, 22, 805, 96), 18, fill=(12, 15, 19, 235), outline=(184, 131, 55, 255), width=3)
    draw.text((505, 36), "TOUR D'ASHKAR", font=f26, fill=(239, 221, 185))
    boss = "  ☠ BOSS" if state.floor == 10 else ""
    draw.text((555, 68), f"ÉTAGE {state.floor} / 10{boss}", font=f16, fill=(224, 190, 120))

    # Bulle adversaire en haut à droite, symétrique au joueur.
    enemy_path = ENEMY_DIR / f"floor_{state.floor:02d}.png"
    if enemy_path.exists():
        enemy_src = Image.open(enemy_path).convert("RGBA")
        enemy_portrait = _circle_portrait(enemy_src, 205, border=(205, 88, 74, 255) if state.floor == 10 else (220, 190, 118, 255))
        img.alpha_composite(enemy_portrait, (975, 145))

    # Avatar Discord du joueur en bas à gauche.
    if avatar_bytes:
        try:
            av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            player_portrait = _circle_portrait(av, 205, border=(220, 190, 118, 255))
            img.alpha_composite(player_portrait, (70, 390))
        except Exception:
            pass

    # HUD ennemi — haut droite.
    e = FLOORS[state.floor]
    draw.rounded_rectangle((760, 105, 1235, 194), 18, fill=(11, 14, 18, 240), outline=(215, 215, 215, 230), width=3)
    draw.text((785, 116), e["name"], font=f26, fill=(245, 245, 245))
    draw.text((1135, 116), f"Niv. {state.floor}", font=f18, fill=(238, 204, 142))
    draw.text((785, 158), "PV", font=f18, fill=(230, 230, 230))
    _draw_bar(draw, (825, 160, 1085, 180), state.enemy_hp / state.enemy_max_hp)
    draw.text((1095, 158), f"{state.enemy_hp}/{state.enemy_max_hp}", font=f16, fill=(235, 235, 235))

    # HUD joueur — bas gauche. Même format compact que le HUD ennemi.
    cfg = state.class_cfg
    draw.rounded_rectangle((45, 510, 520, 599), 18, fill=(11, 14, 18, 240), outline=(215, 215, 215, 230), width=3)
    draw.text((70, 521), state.player_name, font=f26, fill=(245, 245, 245))
    draw.text((420, 521), f"Niv. {state.player_level}", font=f18, fill=(238, 204, 142))
    draw.text((70, 563), "PV", font=f18, fill=(230, 230, 230))
    _draw_bar(draw, (110, 565, 370, 585), state.player_hp / state.player_max_hp)
    draw.text((380, 563), f"{state.player_hp}/{state.player_max_hp}", font=f16, fill=(235, 235, 235))

    # Classe + statistiques restent visibles, mais hors de la barre pour garder le HUD compact.
    draw.text((70, 608), f"{cfg['emoji']} {cfg['name']}   •   ATK {state.player_atk}   DEF {state.player_def}   VIT {state.player_speed}", font=f16, fill=(224, 194, 137))

    # Journal du combat.
    draw.rounded_rectangle((670, 545, 1235, 690), 14, fill=(8, 10, 13, 238), outline=(168, 119, 54, 230), width=2)
    draw.text((695, 562), "JOURNAL DU COMBAT", font=f18, fill=(225, 194, 132))
    txt = state.log if len(state.log) < 130 else state.log[:127] + "..."
    # découpage simple en 2-3 lignes
    words = txt.split()
    lines, line = [], ""
    for w in words:
        candidate = (line + " " + w).strip()
        if draw.textlength(candidate, font=f16) > 505 and line:
            lines.append(line)
            line = w
        else:
            line = candidate
    if line:
        lines.append(line)
    for i, ln in enumerate(lines[:4]):
        draw.text((695, 595 + i * 22), ln, font=f16, fill=(242, 231, 208))

    out = RENDER_DIR / f"battle_{state.owner_id}_{state.floor}.png"
    img.convert("RGB").save(out, quality=92)
    return out


async def _avatar_bytes(user: discord.abc.User) -> Optional[bytes]:
    try:
        return await user.display_avatar.replace(size=256).read()
    except Exception:
        return None


class TowerClassView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=900)
        self.owner_id = int(owner_id)
        self.class_key: str | None = None
        for key, c in CLASSES.items():
            btn = discord.ui.Button(label=c["name"], emoji=c["emoji"], style=discord.ButtonStyle.primary, row=0)
            async def choose(interaction: discord.Interaction, class_key=key):
                self.class_key = class_key
                self.sync_buttons()
                floor = STORE.progress(interaction.user.id) + 1
                await interaction.response.edit_message(content=_tower_class_content(interaction.user.id, floor, self.class_key), view=self)
            btn.callback = choose
            self.add_item(btn)

        self.ready = discord.ui.Button(label="Entrer dans l'étage", emoji="⚔️", style=discord.ButtonStyle.danger, disabled=True, row=1)
        self.back = discord.ui.Button(label="Retour au monde", emoji="🌍", style=discord.ButtonStyle.secondary, row=1)
        self.ready.callback = self.ready_cb
        self.back.callback = self.back_cb
        self.add_item(self.ready)
        self.add_item(self.back)

    def sync_buttons(self):
        self.ready.disabled = self.class_key is None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Cette ascension appartient à un autre joueur.", ephemeral=True)
            return False
        return True

    async def ready_cb(self, interaction: discord.Interaction):
        if not self.class_key:
            await interaction.response.send_message("Choisis d'abord une classe.", ephemeral=True)
            return
        lvl = CASTLE.current_level(interaction.user.id)
        if lvl < 5:
            await interaction.response.send_message(f"🔒 La Tour d'Ashkar exige le **niveau 5**. Ton niveau : **{lvl}**.", ephemeral=True)
            return
        floor = STORE.progress(interaction.user.id) + 1
        ok, reason = STORE.can_attempt(interaction.user.id, floor)
        if not ok:
            msgs = {
                "daily": "⏳ Tu as déjà validé **3 nouveaux étages aujourd'hui**. Reviens demain.",
                "end": "🏆 Tu as terminé les 10 étages actuellement disponibles.",
                "locked": "🔒 Cet étage n'est pas encore accessible.",
            }
            await interaction.response.send_message(msgs.get(reason, "Impossible."), ephemeral=True)
            return
        state = make_state(interaction.user, floor, self.class_key)
        avatar = await _avatar_bytes(interaction.user)
        path = await render_battle(state, avatar)
        view = TowerBattleView(state, avatar)
        file = discord.File(path, filename="ashkar_battle.png")
        await _edit_v2(interaction, title=f"🗼 Tour d'Ashkar — Étage {floor}", description=f"{class_line(self.class_key)}\n\n**{FLOORS[floor]['name']}** se dresse devant toi.\nChoisis ton attaque.", legacy_view=view, file=file, filename="ashkar_battle.png", accent=0x6D4B37 if floor < 10 else 0x8B1E1E)

    async def back_cb(self, interaction: discord.Interaction):
        try:
            await interaction.response.edit_message(content="🌍 Retour au monde. Utilise les boutons de la carte principale.", embed=None, attachments=[], view=None)
        except discord.HTTPException:
            pass


def _tower_class_content(user_id: int, floor: int, class_key: str | None = None) -> str:
    max_floor = STORE.progress(user_id)
    today = STORE.daily(user_id)
    if floor > 10:
        opponent = "🏆 Les 10 étages sont terminés"
    else:
        opponent = f"Étage **{floor}** — **{FLOORS[floor]['name']}**"
    chosen = class_line(class_key) if class_key else "*Aucune classe sélectionnée*"
    return (
        "🗼 **La Tour d'Ashkar — Préparation**\n"
        f"Progression : **{max_floor}/10** • Aujourd'hui : **{today}/3**\n"
        f"Prochain combat : {opponent}\n\n"
        f"**Classe choisie :** {chosen}\n"
        "Tu peux changer de classe **entre chaque étage**. Les attaques et compétences sont identiques à celles de l'Arène."
    )


class TowerBattleView(discord.ui.View):
    def __init__(self, state: BattleState, avatar_bytes: bytes | None):
        super().__init__(timeout=900)
        self.state = state
        self.avatar_bytes = avatar_bytes
        self.finished = False
        cfg = state.class_cfg

        # Les boutons reprennent exactement les noms/emoji des compétences de l'Arène.
        for idx, action in enumerate(("light", "heavy", "ultimate", "defend")):
            sk = cfg["skills"][action]
            style = {
                "light": discord.ButtonStyle.primary,
                "heavy": discord.ButtonStyle.danger,
                "ultimate": discord.ButtonStyle.success,
                "defend": discord.ButtonStyle.secondary,
            }[action]
            b = discord.ui.Button(label=sk["name"], emoji=sk["emoji"], style=style, row=idx // 3, custom_id=f"ashkar_{action}")
            b.callback = self._make_action_callback(action)
            self.add_item(b)
        flee = discord.ui.Button(label="Abandonner", emoji="🏳️", style=discord.ButtonStyle.secondary, row=1)
        flee.callback = self.flee
        self.add_item(flee)

    def _make_action_callback(self, action: str):
        async def cb(interaction: discord.Interaction):
            await self.handle_action(interaction, action)
        return cb

    async def interaction_check(self, interaction):
        if interaction.user.id != self.state.owner_id:
            await interaction.response.send_message("❌ Ce combat n'est pas le tien.", ephemeral=True)
            return False
        return True

    def _sync_ultimate_button(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id == "ashkar_ultimate":
                if self.state.ultimate_cd > 0:
                    child.label = f"{self.state.class_cfg['skills']['ultimate']['name']} ({self.state.ultimate_cd})"
                    child.disabled = True
                else:
                    child.label = self.state.class_cfg["skills"]["ultimate"]["name"]
                    child.disabled = False

    async def refresh(self, interaction, extra=""):
        self._sync_ultimate_button()
        path = await render_battle(self.state, self.avatar_bytes)
        file = discord.File(path, filename="ashkar_battle.png")
        e = FLOORS[self.state.floor]
        desc = f"{class_line(self.state.class_key)}\n**{e['name']}** • Étage **{self.state.floor}/10**"
        if extra:
            desc += "\n" + extra
        await _edit_v2(interaction, title="⚔️ Combat — Tour d'Ashkar", description=desc, legacy_view=self, file=file, filename="ashkar_battle.png", accent=0x8B1E1E if self.state.floor == 10 else 0x6D4B37)

    async def enemy_turn(self):
        s = self.state
        if s.enemy_hp <= 0:
            return ""

        # Saignement infligé par Lacération.
        bleed_line = ""
        if s.enemy_bleed > 0:
            bleed = s.enemy_bleed
            s.enemy_bleed = 0
            s.enemy_hp = max(0, s.enemy_hp - bleed)
            bleed_line = f"🩸 {FLOORS[s.floor]['name']} subit **{bleed}** dégâts de saignement. "
            if s.enemy_hp <= 0:
                return bleed_line

        if _player_dodges(s):
            s.guarding = False
            s.guard_reduction = 0.0
            s.temp_evade = 0.0
            return bleed_line + f"💨 {s.player_name} esquive la riposte !"

        power = .90 if s.enemy_shaken else 1.0
        s.enemy_shaken = False
        if s.floor == 10 and s.enemy_hp <= s.enemy_max_hp // 2:
            if not s.enemy_enraged:
                s.enemy_enraged = True
            power *= 1.22

        class_reduction = s.class_cfg["passive_reduction"]
        equip_reduction = min(.10, s.equipment_def_pct / 100.0)
        total_reduction = 1 - (1 - class_reduction) * (1 - equip_reduction)
        if s.guarding:
            total_reduction = 1 - (1 - total_reduction) * (1 - s.guard_reduction)

        dmg, crit = _enemy_damage(s.enemy_atk, s.player_def, total_reduction, power=power)
        s.player_hp = max(0, s.player_hp - dmg)
        prefix = "💥 CRITIQUE ! " if crit else ""
        rage = " 🔥 Varkhaz entre en **Rage d'Obsidienne** !" if s.enemy_enraged and s.floor == 10 else ""
        s.guarding = False
        s.guard_reduction = 0.0
        s.temp_evade = 0.0
        return bleed_line + f"{prefix}{FLOORS[s.floor]['name']} inflige **{dmg}** dégâts.{rage}"

    async def handle_action(self, interaction: discord.Interaction, action: str):
        if self.finished:
            return
        s = self.state
        cfg = s.class_cfg
        skill = cfg["skills"][action]

        if action == "ultimate" and s.ultimate_cd > 0:
            await interaction.response.send_message(f"⏳ **{skill['name']}** recharge encore pendant **{s.ultimate_cd} tour(s)**.", ephemeral=True)
            return

        if action == "defend":
            s.guarding = True
            if s.class_key == "ravageur":
                s.guard_reduction = .45
                s.next_damage_bonus = max(s.next_damage_bonus, .10)
                player_line = f"🐯 **{skill['name']}** : garde renforcée et prochaine attaque +10%."
            elif s.class_key == "gardien":
                s.guard_reduction = .60
                player_line = f"🛡️ **{skill['name']}** : énorme réduction sur le prochain impact."
            else:
                s.guard_reduction = .30
                s.temp_evade = .35
                player_line = f"💨 **{skill['name']}** : garde légère et forte esquive temporaire."
        else:
            if _enemy_dodges(s, action):
                player_line = f"❌ **{skill['name']}** est esquivé ou rate sa cible."
            else:
                # Patte du Colosse ignore une partie de la défense ennemie.
                old_def = s.enemy_def
                if s.class_key == "gardien" and action == "light":
                    s.enemy_def = max(0, round(s.enemy_def * .75))
                dmg, crit = _player_damage(s, action)
                s.enemy_def = old_def
                s.enemy_hp = max(0, s.enemy_hp - dmg)
                crit_text = " 💥 **CRITIQUE !**" if crit else ""
                player_line = f"{skill['emoji']} **{skill['name']}** inflige **{dmg} dégâts**.{crit_text}"

                # Effets identiques dans l'esprit à l'Arène.
                if s.class_key == "ravageur":
                    if action == "light":
                        s.ravager_light_stacks = min(2, s.ravager_light_stacks + 1)
                        s.next_damage_bonus = max(s.next_damage_bonus, .05 * s.ravager_light_stacks)
                    elif action == "heavy":
                        s.enemy_bleed = max(s.enemy_bleed, 20)
                    elif action == "ultimate" and crit:
                        s.next_damage_bonus = max(s.next_damage_bonus, .10)
                elif s.class_key == "gardien":
                    if action == "heavy":
                        s.enemy_shaken = True
                    elif action == "ultimate":
                        s.guarding = True
                        s.guard_reduction = max(s.guard_reduction, .20)
                elif s.class_key == "traqueur":
                    if action == "light":
                        s.temp_evade = max(s.temp_evade, .10)

            if action == "ultimate":
                s.ultimate_cd = 2

        if s.enemy_hp <= 0:
            s.log = player_line
            await self.finish_win(interaction)
            return

        enemy_line = await self.enemy_turn()
        if s.enemy_hp <= 0:
            s.log = player_line + "  " + enemy_line
            await self.finish_win(interaction)
            return

        if action != "ultimate" and s.ultimate_cd > 0:
            s.ultimate_cd -= 1

        s.log = player_line + "  " + enemy_line
        if s.player_hp <= 0:
            await self.finish_loss(interaction)
            return
        await self.refresh(interaction)

    async def finish_win(self, interaction):
        self.finished = True
        ok = await STORE.validate(self.state.owner_id, self.state.floor)
        e = FLOORS[self.state.floor]
        if not ok:
            await interaction.response.send_message("⚠️ Cet étage a déjà été validé ou ta limite quotidienne est atteinte.", ephemeral=True)
            return
        reward = f"🪙 **+{e['gold']} Gold**" + (f"   🔷 **+{e['pouciel']} Pouciel**" if e["pouciel"] else "")
        self.state.log = f"🏆 VICTOIRE ! Étage {self.state.floor} validé. {reward}"
        path = await render_battle(self.state, self.avatar_bytes)
        file = discord.File(path, filename="ashkar_battle.png")
        await _edit_v2(interaction, title=f"🏆 Étage {self.state.floor} terminé !", description=f"**{e['name']}** est vaincu.\n\n{reward}\n\nL'étage reste **définitivement validé**.\nTu pourras choisir à nouveau ta classe avant le prochain étage.", legacy_view=PostBattleView(self.state.owner_id, self.state.class_key, self.state.floor, won=True), file=file, filename="ashkar_battle.png", accent=0xD6A84B)

    async def finish_loss(self, interaction):
        self.finished = True
        self.state.log = "💀 Défaite. Aucun étage perdu : tu pourras retenter ce combat."
        path = await render_battle(self.state, self.avatar_bytes)
        file = discord.File(path, filename="ashkar_battle.png")
        await _edit_v2(interaction, title="💀 Défaite", description=f"Tu n'as pas vaincu **{FLOORS[self.state.floor]['name']}**.\n\n✅ Tes étages déjà validés restent acquis.\n🔁 Tu peux retenter cet étage et même changer de classe avant le prochain essai.", legacy_view=PostBattleView(self.state.owner_id, self.state.class_key, self.state.floor, won=False), file=file, filename="ashkar_battle.png", accent=0x8B1E1E)

    async def flee(self, interaction: discord.Interaction):
        self.finished = True
        await _edit_v2(interaction, title="🏳️ Combat abandonné", description="Aucune progression n'est perdue et cet abandon ne valide pas l'étage. Tu peux changer de classe avant de retenter.", legacy_view=PostBattleView(self.state.owner_id, self.state.class_key, self.state.floor, won=False), accent=0x666666)


class PostBattleView(discord.ui.View):
    def __init__(self, owner_id: int, class_key: str, floor: int, *, won: bool):
        super().__init__(timeout=900)
        self.owner_id = int(owner_id)
        self.class_key = class_key
        self.floor = int(floor)
        self.won = bool(won)

        # Après une victoire, le joueur peut enchaîner directement avec la même classe.
        # Après une défaite/abandon, il peut retenter immédiatement sans refaire toute la préparation.
        if self.won and self.floor < 10:
            b = discord.ui.Button(label="Étage suivant", emoji="⬆️", style=discord.ButtonStyle.success, row=0)
            b.callback = self.continue_next
            self.add_item(b)
        elif not self.won:
            b = discord.ui.Button(label="Retenter", emoji="🔁", style=discord.ButtonStyle.danger, row=0)
            b.callback = self.retry_same
            self.add_item(b)

        c = discord.ui.Button(label="Changer de classe", emoji="🔄", style=discord.ButtonStyle.secondary, row=0)
        c.callback = self.change_class
        self.add_item(c)

        t = discord.ui.Button(label="Retour à la Tour", emoji="🗼", style=discord.ButtonStyle.primary, row=1)
        t.callback = self.tower
        self.add_item(t)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Ce menu n'est pas le tien.", ephemeral=True)
            return False
        return True

    async def _launch(self, interaction: discord.Interaction, floor: int):
        ok, reason = STORE.can_attempt(self.owner_id, floor)
        if not ok:
            msgs = {
                "daily": "⏳ Tu as déjà validé **3 nouveaux étages aujourd'hui**. Reviens demain.",
                "end": "🏆 Tu as terminé les 10 étages actuellement disponibles.",
                "locked": "🔒 Cet étage n'est pas encore accessible.",
            }
            await interaction.response.send_message(msgs.get(reason, "Impossible de lancer cet étage."), ephemeral=True)
            return

        state = make_state(interaction.user, floor, self.class_key)
        avatar = await _avatar_bytes(interaction.user)
        path = await render_battle(state, avatar)
        file = discord.File(path, filename="ashkar_battle.png")
        view = TowerBattleView(state, avatar)
        await _edit_v2(interaction, title=f"🗼 Tour d'Ashkar — Étage {floor}", description=f"{class_line(self.class_key)}\n\n**{FLOORS[floor]['name']}** se dresse devant toi.\nChoisis ton attaque.", legacy_view=view, file=file, filename="ashkar_battle.png", accent=0x6D4B37 if floor < 10 else 0x8B1E1E)

    async def continue_next(self, interaction: discord.Interaction):
        next_floor = self.floor + 1
        await self._launch(interaction, next_floor)

    async def retry_same(self, interaction: discord.Interaction):
        # Après une défaite, STORE.progress() n'a pas changé : on retente le même étage.
        await self._launch(interaction, self.floor)

    async def change_class(self, interaction: discord.Interaction):
        # Retour direct à la préparation du prochain étage / étage courant, sans repasser par la carte du monde.
        await show_lobby(interaction, edit=True)

    async def tower(self, interaction: discord.Interaction):
        await show_lobby(interaction, edit=True)


async def show_lobby(interaction: discord.Interaction, *, edit=False):
    lvl = CASTLE.current_level(interaction.user.id)
    max_floor = STORE.progress(interaction.user.id)
    next_floor = max_floor + 1

    if lvl < 5:
        embed = discord.Embed(
            title="🔒 La Tour d'Ashkar",
            description=f"La brume se dissipe, révélant une tour gigantesque… mais une force invisible te repousse.\n\n**Niveau 5 requis** • Ton niveau : **{lvl}**",
            color=0x3A3A46,
        )
        if edit:
            await interaction.response.edit_message(content=None, embed=embed, attachments=[], view=None)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if next_floor > 10:
        embed = discord.Embed(
            title="🏆 La Tour d'Ashkar",
            description="Tu as terminé les **10 étages actuellement disponibles**. D'autres étages seront révélés plus tard…",
            color=discord.Color.gold(),
        )
        poster = ASSET_DIR / "tower_poster.png"
        if poster.exists():
            file = discord.File(poster, filename="ashkar.png")
            embed.set_image(url="attachment://ashkar.png")
            if edit:
                await interaction.response.edit_message(content=None, embed=embed, attachments=[file], view=None)
            else:
                await interaction.response.send_message(embed=embed, file=file, ephemeral=True)
        else:
            if edit:
                await interaction.response.edit_message(content=None, embed=embed, attachments=[], view=None)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    view = TowerClassView(interaction.user.id)
    content = _tower_class_content(interaction.user.id, next_floor, None)
    poster = ASSET_DIR / "tower_poster.png"
    embed = discord.Embed(
        title="🗼 La Tour d'Ashkar",
        description="Avant chaque étage, choisis ta classe. Tu peux en changer librement **entre deux étages**.",
        color=0x5B475E,
    )
    if poster.exists():
        file = discord.File(poster, filename="ashkar.png")
        embed.set_image(url="attachment://ashkar.png")
        if edit:
            await interaction.response.edit_message(content=content, embed=embed, attachments=[file], view=view)
        else:
            await interaction.response.send_message(content=content, embed=embed, file=file, view=view, ephemeral=True)
    else:
        if edit:
            await interaction.response.edit_message(content=content, embed=embed, attachments=[], view=view)
        else:
            await interaction.response.send_message(content=content, embed=embed, view=view, ephemeral=True)
