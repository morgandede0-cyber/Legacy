"""Altherya Accueil — onboarding Discord séparé du RPG.

Chargé par main.py, mais toute la logique d'accueil reste isolée ici.
Parcours : Langue -> Pseudo -> Règlement -> Entrer.
"""
from __future__ import annotations

import os
import re
import io
import sqlite3
from pathlib import Path

from PIL import Image
import pytesseract

import discord
from discord import app_commands

ACCENT = 0xD6A84B
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DATA.mkdir(parents=True, exist_ok=True)
DB = sqlite3.connect(DATA / "onboarding.sqlite3")
DB.execute(
    """CREATE TABLE IF NOT EXISTS onboarding (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        language TEXT,
        nickname TEXT,
        rules INTEGER DEFAULT 0,
        completed INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    )"""
)
DB.commit()


def _env_id(name: str) -> int:
    try:
        return int(os.getenv(name, "0") or 0)
    except ValueError:
        return 0


def _state(guild_id: int, user_id: int) -> dict:
    row = DB.execute(
        "SELECT language,nickname,rules,completed FROM onboarding WHERE guild_id=? AND user_id=?",
        (guild_id, user_id),
    ).fetchone()
    return {
        "language": row[0] if row else None,
        "nickname": row[1] if row else None,
        "rules": bool(row[2]) if row else False,
        "completed": bool(row[3]) if row else False,
    }


def _save(guild_id: int, user_id: int, **changes) -> None:
    state = _state(guild_id, user_id)
    state.update(changes)
    DB.execute(
        """INSERT OR REPLACE INTO onboarding
        (guild_id,user_id,language,nickname,rules,completed) VALUES(?,?,?,?,?,?)""",
        (guild_id, user_id, state["language"], state["nickname"], int(state["rules"]), int(state["completed"])),
    )
    DB.commit()


def _container(*items):
    return discord.ui.Container(*items, accent_colour=ACCENT)


def _sep():
    return discord.ui.Separator(spacing=discord.SeparatorSpacing.large)


def _gid(interaction: discord.Interaction) -> int:
    return interaction.guild_id or 0


def _lang(guild_id: int, user_id: int) -> str:
    value = (_state(guild_id, user_id).get("language") or "Français").lower()
    return "en" if value in {"english", "en", "anglais"} else "fr"


def _set_lang(guild_id: int, user_id: int, code: str) -> None:
    _save(guild_id, user_id, language="English" if code == "en" else "Français")


class WelcomePublicView(discord.ui.LayoutView):
    """Panneau public. Le sélecteur ouvre une copie privée afin que la langue reste propre à chaque joueur."""
    def __init__(self):
        super().__init__(timeout=None)
        lang = discord.ui.Button(
            label="FR", emoji="🇫🇷", style=discord.ButtonStyle.secondary,
            custom_id="altherya_accueil:lang",
        )
        start = discord.ui.Button(
            label="COMMENCER", emoji="👑", style=discord.ButtonStyle.primary,
            custom_id="altherya_accueil:start",
        )
        lang.callback = self._language
        start.callback = self._start
        self.add_item(_container(
            discord.ui.Section("# 👑  A L T H É R Y A\n### BIENVENUE DANS LE ROYAUME", accessory=lang),
            _sep(),
            discord.ui.TextDisplay(
                "Une nouvelle aventure commence ici.\n\n"
                "Avant que les portes d’Althérya ne s’ouvrent, prépare ton arrivée en **3 étapes**."
            ),
            _sep(),
            discord.ui.TextDisplay(
                "🌍 **Langue**\nChoisis FR / EN avec le bouton en haut à droite.\n\n"
                "📸 **Identité**\nEnvoie ton screen Informations joueur : ton pseudo sera détecté automatiquement.\n\n"
                "📜 **Lois du Royaume**\nPrends connaissance du règlement."
            ),
            _sep(),
            discord.ui.ActionRow(start),
            discord.ui.TextDisplay("-# Althérya • Les portes du royaume attendent ton arrivée."),
        ))

    async def _language(self, interaction: discord.Interaction):
        current = _lang(_gid(interaction), interaction.user.id)
        target = "en" if current == "fr" else "fr"
        _set_lang(_gid(interaction), interaction.user.id, target)
        await interaction.response.send_message(
            view=WelcomePrivateView(_gid(interaction), interaction.user.id), ephemeral=True
        )

    async def _start(self, interaction: discord.Interaction):
        if _state(_gid(interaction), interaction.user.id)["completed"]:
            msg = "👑 Registration already completed. Welcome to Althérya!" if _lang(_gid(interaction), interaction.user.id) == "en" else "👑 Ton inscription est déjà terminée. Bienvenue à Althérya !"
            await interaction.response.send_message(msg, ephemeral=True)
            return
        if not _state(_gid(interaction), interaction.user.id)["language"]:
            _set_lang(_gid(interaction), interaction.user.id, "fr")
        await interaction.response.send_message(
            view=WelcomePrivateView(_gid(interaction), interaction.user.id), ephemeral=True
        )


class WelcomePrivateView(discord.ui.LayoutView):
    """Copie privée : ici le bouton FR/EN peut réellement changer visuellement pour le joueur."""
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=1800)
        lang = _lang(guild_id, user_id)
        toggle = discord.ui.Button(
            label="EN" if lang == "en" else "FR",
            emoji="🇬🇧" if lang == "en" else "🇫🇷",
            style=discord.ButtonStyle.secondary,
        )
        start = discord.ui.Button(
            label="START" if lang == "en" else "COMMENCER",
            emoji="👑", style=discord.ButtonStyle.primary,
        )
        async def toggle_cb(interaction: discord.Interaction):
            if interaction.user.id != user_id:
                await interaction.response.send_message("⛔ This panel is not yours." if lang == "en" else "⛔ Ce panneau ne t'appartient pas.", ephemeral=True)
                return
            _set_lang(guild_id, user_id, "fr" if lang == "en" else "en")
            await interaction.response.edit_message(view=WelcomePrivateView(guild_id, user_id))
        async def start_cb(interaction: discord.Interaction):
            await interaction.response.edit_message(view=IdentityView(guild_id, user_id))
        toggle.callback = toggle_cb
        start.callback = start_cb
        if lang == "en":
            header = "# 👑  A L T H É R Y A\n### WELCOME TO THE KINGDOM"
            intro = "A new adventure begins here.\n\nBefore the gates of Althérya open, prepare your arrival in **3 steps**."
            steps = "🌍 **Language**\nYour choice applies to the entire registration process.\n\n📸 **Identity**\nSend your Player Information screenshot: your nickname will be detected automatically.\n\n📜 **Laws of the Kingdom**\nRead and accept the server rules."
            foot = "-# Althérya • The gates of the kingdom await your arrival."
        else:
            header = "# 👑  A L T H É R Y A\n### BIENVENUE DANS LE ROYAUME"
            intro = "Une nouvelle aventure commence ici.\n\nAvant que les portes d’Althérya ne s’ouvrent, prépare ton arrivée en **3 étapes**."
            steps = "🌍 **Langue**\nTon choix s'applique à tout le processus d'accueil.\n\n📸 **Identité**\nEnvoie ton screen Informations joueur : ton pseudo sera détecté automatiquement.\n\n📜 **Lois du Royaume**\nPrends connaissance du règlement."
            foot = "-# Althérya • Les portes du royaume attendent ton arrivée."
        self.add_item(_container(
            discord.ui.Section(header, accessory=toggle), _sep(),
            discord.ui.TextDisplay(intro), _sep(), discord.ui.TextDisplay(steps), _sep(),
            discord.ui.ActionRow(start), discord.ui.TextDisplay(foot),
        ))


# Zone du pseudo relevée sur le screen de référence 744x429.
# Les coordonnées sont stockées en ratios pour rester compatibles avec les mêmes
# captures redimensionnées sans déformation.
NICK_CROP = (300 / 744, 109 / 429, 463 / 744, 144 / 429)
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


def _clean_ocr_name(raw: str) -> str:
    name = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ0-9 ._'\-]", "", raw or "")
    name = re.sub(r"\s+", " ", name).strip(" ._-")
    # Correction ciblée du préfixe de clan visible sur CET écran fixe : IV.
    # La police du jeu fusionne visuellement I+V et Tesseract peut le lire
    # comme Iv/IY mais aussi W, Ww ou Wv. On ne corrige que le PREMIER
    # token suivi d'un espace, jamais un W présent dans le pseudo lui-même.
    if re.match(r"^[Ii][VvYy]\s+", name):
        name = "IV " + re.sub(r"^[Ii][VvYy]\s+", "", name)
    elif re.match(r"^[Ww]{1,2}\s+", name):
        name = "IV " + re.sub(r"^[Ww]{1,2}\s+", "", name)
    elif re.match(r"^[Ww][Vv]\s+", name):
        name = "IV " + re.sub(r"^[Ww][Vv]\s+", "", name)
    return name[:32]


def _ocr_nickname(image_bytes: bytes) -> tuple[str, float]:
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("RGB")
    w, h = image.size
    if w < 500 or h < 280:
        raise ValueError("capture trop petite")
    x1, y1, x2, y2 = NICK_CROP
    crop = image.crop((int(w*x1), int(h*y1), int(w*x2), int(h*y2)))

    # Le pseudo du jeu est jaune/or sur fond sombre. On isole cette couleur afin
    # d'éviter que le cadre rouge, le portrait et les autres textes perturbent l'OCR.
    mask = Image.new("L", crop.size, 255)
    out = mask.load()
    for y in range(crop.height):
        for x in range(crop.width):
            r, g, b = crop.getpixel((x, y))
            if r > 150 and g > 95 and b < 145 and r > b * 1.35:
                out[x, y] = 0
    mask = mask.resize((mask.width * 8, mask.height * 8))
    data = pytesseract.image_to_data(mask, config="--psm 7", output_type=pytesseract.Output.DICT)
    words, confs = [], []
    for text, conf in zip(data.get("text", []), data.get("conf", [])):
        text = (text or "").strip()
        try:
            c = float(conf)
        except (TypeError, ValueError):
            c = -1
        if text:
            words.append(text)
            if c >= 0:
                confs.append(c)
    name = _clean_ocr_name(" ".join(words))
    confidence = sum(confs) / len(confs) if confs else 0.0
    return name, confidence


class AdminCorrectionModal(discord.ui.Modal, title="Corriger l'identité"):
    nickname = discord.ui.TextInput(label="Pseudo exact", min_length=2, max_length=32, required=True)

    def __init__(self, guild_id: int, user_id: int, detected: str = ""):
        super().__init__()
        self.guild_id = guild_id
        self.user_id = user_id
        self.nickname.default = detected[:32] if detected else None

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.permissions.administrator:
            await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
            return
        name = str(self.nickname).strip()
        member = interaction.guild.get_member(self.user_id) if interaction.guild else None
        if member is None and interaction.guild:
            try:
                member = await interaction.guild.fetch_member(self.user_id)
            except discord.HTTPException:
                member = None
        if member:
            try:
                await member.edit(nick=name, reason=f"Correction onboarding par {interaction.user}")
            except (discord.Forbidden, discord.HTTPException):
                await interaction.response.send_message("⚠️ Pseudo enregistré, mais Discord refuse le renommage.", ephemeral=True)
                _save(self.guild_id, self.user_id, nickname=name)
                return
        _save(self.guild_id, self.user_id, nickname=name)
        await interaction.response.send_message(f"✅ Identité corrigée et validée : **{discord.utils.escape_markdown(name)}**.", ephemeral=True)
        try:
            await interaction.message.edit(view=None)
        except discord.HTTPException:
            pass


class AdminReviewView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int, detected: str = ""):
        super().__init__(timeout=86400)
        self.guild_id = guild_id
        self.user_id = user_id
        self.detected = detected[:32]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.permissions.administrator:
            return True
        await interaction.response.send_message("⛔ Réservé aux administrateurs.", ephemeral=True)
        return False

    @discord.ui.button(label="Valider la détection", emoji="✅", style=discord.ButtonStyle.success)
    async def validate(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.detected:
            await interaction.response.send_message("⚠️ Aucun pseudo détecté à valider. Utilise Corriger.", ephemeral=True)
            return
        member = interaction.guild.get_member(self.user_id) if interaction.guild else None
        if member:
            try:
                await member.edit(nick=self.detected, reason=f"Validation onboarding par {interaction.user}")
            except (discord.Forbidden, discord.HTTPException):
                await interaction.response.send_message("⚠️ Discord refuse le renommage. Vérifie la hiérarchie des rôles.", ephemeral=True)
                return
        _save(self.guild_id, self.user_id, nickname=self.detected)
        await interaction.response.send_message(f"✅ **{discord.utils.escape_markdown(self.detected)}** validé.", ephemeral=True)
        await interaction.message.edit(view=None)

    @discord.ui.button(label="Corriger", emoji="✏️", style=discord.ButtonStyle.primary)
    async def correct(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminCorrectionModal(self.guild_id, self.user_id, self.detected))

    @discord.ui.button(label="Refuser", emoji="❌", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Identification refusée. Le joueur devra renvoyer un screen.", ephemeral=True)
        await interaction.message.edit(view=None)


async def _alert_admins(interaction: discord.Interaction, reason: str, image_bytes: bytes | None = None,
                        detected: str | None = None, confidence: float | None = None):
    channel_id = _env_id("ADMIN_ONBOARDING_CHANNEL_ID")
    if not channel_id or not interaction.guild:
        return
    channel = interaction.guild.get_channel(channel_id)
    if channel is None:
        try:
            channel = await interaction.guild.fetch_channel(channel_id)
        except (discord.HTTPException, discord.Forbidden):
            return
    details = (
        f"## 🚨 Échec d'identification Althérya\n"
        f"👤 Joueur : {interaction.user.mention} (`{interaction.user.id}`)\n"
        f"⚠️ Motif : **{reason}**\n"
        f"🔎 Détection : **{discord.utils.escape_markdown(detected or 'Aucune')}**\n"
        f"📊 Confiance OCR : **{confidence:.0f}%**" if confidence is not None else
        f"## 🚨 Échec d'identification Althérya\n👤 Joueur : {interaction.user.mention} (`{interaction.user.id}`)\n⚠️ Motif : **{reason}**\n🔎 Détection : **{discord.utils.escape_markdown(detected or 'Aucune')}**"
    )
    file = discord.File(io.BytesIO(image_bytes), filename="identification.png") if image_bytes else None
    await channel.send(details, file=file, view=AdminReviewView(interaction.guild.id, interaction.user.id, detected or ""))


class OCRConfirmView(discord.ui.LayoutView):
    def __init__(self, guild_id: int, user_id: int, nickname: str):
        super().__init__(timeout=900)
        self.nickname = nickname
        lang = _lang(guild_id, user_id)
        confirm = discord.ui.Button(label="CONFIRM" if lang == "en" else "CONFIRMER", emoji="✅", style=discord.ButtonStyle.success)
        retry = discord.ui.Button(label="SEND ANOTHER SCREEN" if lang == "en" else "RENVOYER UN SCREEN", emoji="📸", style=discord.ButtonStyle.secondary)
        async def confirm_cb(interaction: discord.Interaction):
            if interaction.user.id != user_id:
                await interaction.response.send_message("⛔ This identification is not yours." if lang == "en" else "⛔ Cette identification ne t'appartient pas.", ephemeral=True); return
            if isinstance(interaction.user, discord.Member):
                try: await interaction.user.edit(nick=self.nickname, reason="Identification OCR Althérya")
                except (discord.Forbidden, discord.HTTPException):
                    await _alert_admins(interaction, "Discord refuse le renommage du membre", detected=self.nickname)
                    reason = "Discord nickname update failed. An administrator has been notified." if lang == "en" else "Le renommage Discord a échoué. Un administrateur a été prévenu."
                    await interaction.response.edit_message(view=IdentityErrorView(guild_id, user_id, reason)); return
            _save(guild_id, user_id, nickname=self.nickname)
            await interaction.response.edit_message(view=RulesView(guild_id, user_id))
        async def retry_cb(interaction: discord.Interaction): await interaction.response.edit_message(view=IdentityView(guild_id, user_id))
        confirm.callback=confirm_cb; retry.callback=retry_cb
        title = "## 🔎 IDENTITY DETECTED\n**STEP 02 / 03**" if lang == "en" else "## 🔎 IDENTITÉ DÉTECTÉE\n**ÉTAPE 02 / 03**"
        body = (f"### Detected nickname\n# **{discord.utils.escape_markdown(nickname)}**\n\nConfirm only if this nickname exactly matches the one shown on your screenshot." if lang == "en" else f"### Pseudo détecté\n# **{discord.utils.escape_markdown(nickname)}**\n\nConfirme uniquement si ce pseudo correspond exactement à celui affiché sur ton screen.")
        progress = "**● ━ ● ━ ○**   Language • Identity • Rules" if lang == "en" else "**● ━ ● ━ ○**   Langue • Identité • Règlement"
        self.add_item(_container(discord.ui.TextDisplay(title), _sep(), discord.ui.TextDisplay(body), discord.ui.ActionRow(retry,confirm), _sep(), discord.ui.TextDisplay(progress)))


class IdentityErrorView(discord.ui.LayoutView):
    def __init__(self, guild_id: int, user_id: int, reason: str):
        super().__init__(timeout=1800)
        lang = _lang(guild_id, user_id)
        retry = discord.ui.Button(label="SEND A NEW SCREEN" if lang == "en" else "ENVOYER UN NOUVEAU SCREEN", emoji="📸", style=discord.ButtonStyle.primary)
        async def retry_cb(interaction: discord.Interaction): await interaction.response.edit_message(view=IdentityView(guild_id,user_id))
        retry.callback=retry_cb
        title = "## ⚠️ IDENTIFICATION FAILED\n**STEP 02 / 03**" if lang == "en" else "## ⚠️ IDENTIFICATION IMPOSSIBLE\n**ÉTAPE 02 / 03**"
        suffix = "\n\nThe administration team has been notified. You can send a new screenshot and try again." if lang == "en" else "\n\nL'équipe d'administration a été prévenue. Tu peux envoyer un nouveau screen puis réessayer."
        self.add_item(_container(discord.ui.TextDisplay(title), _sep(), discord.ui.TextDisplay(reason+suffix), discord.ui.ActionRow(retry)))


class ScreenUploadModal(discord.ui.Modal, title="Identification Althérya"):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.user_id = user_id
        lang = _lang(guild_id, user_id)
        self.upload = discord.ui.FileUpload(
            custom_id="altherya_identity_screen",
            required=True,
            min_values=1,
            max_values=1,
        )
        self.add_item(discord.ui.Label(
            text="Player Information screenshot" if lang == "en" else "Capture Informations joueur",
            description="Add a full screenshot of your profile (PNG/JPG/WEBP)." if lang == "en" else "Ajoute une capture complète de ton profil (PNG/JPG/WEBP).",
            component=self.upload,
        ))

    async def on_submit(self, interaction: discord.Interaction):
        # IMPORTANT: une modale contenant FileUpload est une interaction Components V2.
        # Discord refuse alors tout champ `content` dans la réponse (50035).
        # Toutes les réponses de cette modale sont donc rendues uniquement via LayoutView.
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                view=IdentityErrorView(self.guild_id, self.user_id, ("This identification is not yours." if _lang(self.guild_id, self.user_id) == "en" else "Cette identification ne t'appartient pas.")),
                ephemeral=True,
            )
            return
        attachments = self.upload.values
        if not attachments:
            await interaction.response.send_message(
                view=IdentityErrorView(self.guild_id, self.user_id, ("No screenshot was received." if _lang(self.guild_id, self.user_id) == "en" else "Aucun screen n'a été reçu.")),
                ephemeral=True,
            )
            return
        attachment = attachments[0]
        ctype = (attachment.content_type or "").lower()
        if ctype not in ALLOWED_IMAGE_TYPES and not attachment.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            await _alert_admins(interaction, "Fichier non image envoyé dans l'identification")
            await interaction.response.send_message(
                view=IdentityErrorView(self.guild_id, self.user_id, ("The file must be a PNG, JPG or WEBP image." if _lang(self.guild_id, self.user_id) == "en" else "Le fichier doit être une image PNG, JPG ou WEBP.")),
                ephemeral=True,
            )
            return
        try:
            image_bytes = await attachment.read()
            nickname, confidence = _ocr_nickname(image_bytes)
        except Exception as exc:
            await _alert_admins(interaction, f"Lecture du screen impossible ({type(exc).__name__})")
            await interaction.response.send_message(
                view=IdentityErrorView(self.guild_id, self.user_id, ("I could not read this screenshot." if _lang(self.guild_id, self.user_id) == "en" else "Je n'ai pas réussi à lire ce screen.")),
                ephemeral=True,
            )
            return
        if len(nickname) < 2 or confidence < 45:
            await _alert_admins(interaction, "OCR incertain", image_bytes, nickname, confidence)
            await interaction.response.send_message(
                view=IdentityErrorView(self.guild_id, self.user_id, ("The nickname could not be read with enough confidence." if _lang(self.guild_id, self.user_id) == "en" else "Le pseudo n'a pas pu être lu avec suffisamment de certitude.")),
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            view=OCRConfirmView(self.guild_id, self.user_id, nickname),
            ephemeral=True,
        )


class IdentityRetryView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=900)
        self.guild_id = guild_id
        self.user_id = user_id

    @discord.ui.button(label="ENVOYER UN NOUVEAU SCREEN", emoji="📸", style=discord.ButtonStyle.primary)
    async def retry(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("⛔ Cette identification ne t'appartient pas.", ephemeral=True)
            return
        await interaction.response.send_modal(ScreenUploadModal(self.guild_id, self.user_id))


class IdentityView(discord.ui.LayoutView):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=1800)
        lang = _lang(guild_id,user_id)
        back=discord.ui.Button(label="Back" if lang=="en" else "Retour",emoji="↩️",style=discord.ButtonStyle.secondary)
        upload=discord.ui.Button(label="UPLOAD MY SCREEN" if lang=="en" else "ENVOYER MON SCREEN",emoji="📷",style=discord.ButtonStyle.primary)
        async def back_cb(interaction): await interaction.response.edit_message(view=WelcomePrivateView(guild_id,user_id))
        async def upload_cb(interaction):
            if interaction.user.id != user_id:
                await interaction.response.send_message("⛔ This identification is not yours." if lang=="en" else "⛔ Cette identification ne t'appartient pas.",ephemeral=True); return
            await interaction.response.send_modal(ScreenUploadModal(guild_id,user_id))
        back.callback=back_cb; upload.callback=upload_cb
        title="## 📸 IDENTIFICATION\n**STEP 02 / 03**" if lang=="en" else "## 📸 IDENTIFICATION\n**ÉTAPE 02 / 03**"
        body=("### Send your **Player Information** screenshot.\nPress **UPLOAD MY SCREEN**: Discord will open a window where you can select your screenshot.\n\nAlthérya will automatically analyse **only the nickname area**.\n-# Manual nickname entry is not allowed." if lang=="en" else "### Envoie ton screen **Informations joueur**.\nAppuie sur **ENVOYER MON SCREEN** : Discord ouvrira une petite fenêtre où tu pourras sélectionner ta capture.\n\nAlthérya analysera automatiquement **uniquement la zone du pseudo**.\n-# Aucune saisie manuelle du pseudo n'est autorisée.")
        chosen="🌍 Selected language: **English**" if lang=="en" else "🌍 Langue choisie : **Français**"
        progress="**● ━ ● ━ ○**   Language • Identity • Rules" if lang=="en" else "**● ━ ● ━ ○**   Langue • Identité • Règlement"
        self.add_item(_container(discord.ui.TextDisplay(title),_sep(),discord.ui.TextDisplay(body),discord.ui.TextDisplay(chosen),_sep(),discord.ui.ActionRow(back,upload),_sep(),discord.ui.TextDisplay(progress)))


class RulesView(discord.ui.LayoutView):
    def __init__(self,guild_id:int,user_id:int):
        super().__init__(timeout=1800); lang=_lang(guild_id,user_id)
        back=discord.ui.Button(label="Back to identification" if lang=="en" else "Retour à l’identification",emoji="↩️",style=discord.ButtonStyle.secondary)
        accept=discord.ui.Button(label="I ACCEPT" if lang=="en" else "J'ACCEPTE",emoji="✅",style=discord.ButtonStyle.success)
        rules_channel_id=_env_id("RULES_CHANNEL_ID")
        async def back_cb(interaction): await interaction.response.edit_message(view=IdentityView(_gid(interaction),interaction.user.id))
        async def accept_cb(interaction): _save(_gid(interaction),interaction.user.id,rules=True); await interaction.response.edit_message(view=FinalView(_gid(interaction),interaction.user.id))
        back.callback=back_cb; accept.callback=accept_cb
        if lang=="en":
            title="## 📜 LAWS OF THE KINGDOM\n**STEP 03 / 03**"; body="Every community needs a few rules.\n\n🤝 **Respect other members**\n💬 **Use each channel appropriately**\n🛡️ **Harassment and discrimination are forbidden**\n⚖️ **Respect moderation decisions**"; confirm="By continuing, you confirm that you have read and accepted the full server rules."; progress="**● ━ ● ━ ●**   Language • Identity • Rules"; rulelabel="VIEW THE RULES"
        else:
            title="## 📜 LES LOIS DU ROYAUME\n**ÉTAPE 03 / 03**"; body="Toute communauté a besoin de quelques règles.\n\n🤝 **Respecte les autres membres**\n💬 **Utilise chaque salon à bon escient**\n🛡️ **Harcèlement et discrimination interdits**\n⚖️ **Respecte les décisions de la modération**"; confirm="En continuant, tu confirmes avoir lu et accepté le règlement complet du serveur."; progress="**● ━ ● ━ ●**   Langue • Identité • Règlement"; rulelabel="VOIR LE RÈGLEMENT"
        components=[discord.ui.TextDisplay(title),_sep(),discord.ui.TextDisplay(body),_sep(),discord.ui.TextDisplay(confirm)]
        if rules_channel_id and guild_id: components.append(discord.ui.ActionRow(discord.ui.Button(label=rulelabel,emoji="📖",style=discord.ButtonStyle.link,url=f"https://discord.com/channels/{guild_id}/{rules_channel_id}")))
        components.extend([discord.ui.ActionRow(back,accept),_sep(),discord.ui.TextDisplay(progress)])
        self.add_item(_container(*components))


class FinalView(discord.ui.LayoutView):
    def __init__(self,guild_id:int,user_id:int):
        super().__init__(timeout=1800); state=_state(guild_id,user_id); lang=_lang(guild_id,user_id); nickname=discord.utils.escape_markdown(state["nickname"] or ("Adventurer" if lang=="en" else "Aventurier"))
        enter=discord.ui.Button(label="ENTER THE KINGDOM" if lang=="en" else "ENTRER DANS LE ROYAUME",emoji="🏰",style=discord.ButtonStyle.success)
        async def enter_cb(interaction):
            current=_state(_gid(interaction),interaction.user.id)
            if not(current["language"] and current["nickname"] and current["rules"]): await interaction.response.send_message("⚠️ Your registration is incomplete." if lang=="en" else "⚠️ Ton inscription est incomplète.",ephemeral=True); return
            member_role_id=_env_id("MEMBER_ROLE_ID")
            if member_role_id:
                if not interaction.guild or not isinstance(interaction.user,discord.Member): await interaction.response.send_message("⚠️ This step must be completed on the server." if lang=="en" else "⚠️ Cette étape doit être terminée sur le serveur.",ephemeral=True); return
                role=interaction.guild.get_role(member_role_id)
                if role is None: await interaction.response.send_message("⚠️ The configured Member role cannot be found." if lang=="en" else "⚠️ Le rôle Membre configuré est introuvable. Vérifie `MEMBER_ROLE_ID`.",ephemeral=True); return
                try: await interaction.user.add_roles(role,reason="Onboarding Althérya terminé")
                except discord.Forbidden: await interaction.response.send_message("⚠️ I cannot assign the Member role. Place my role above it." if lang=="en" else "⚠️ Je ne peux pas attribuer le rôle Membre. Place mon rôle au-dessus du rôle Membre.",ephemeral=True); return
            _save(_gid(interaction),interaction.user.id,completed=True)
            done=discord.ui.LayoutView(timeout=300); txt=(f"# 👑 WELCOME, {discord.utils.escape_markdown(current['nickname'])}\n### The gates of the kingdom are open.\n\nYour adventure in **Althérya** can begin." if lang=="en" else f"# 👑 BIENVENUE, {discord.utils.escape_markdown(current['nickname'])}\n### Les portes du royaume sont ouvertes.\n\nTon aventure à **Althérya** peut commencer.")
            done.add_item(_container(discord.ui.TextDisplay(txt))); await interaction.response.edit_message(view=done)
        enter.callback=enter_cb
        if lang=="en": title=f"# 👑 WELCOME, {nickname}"; info=f"🌍 **English**\n✒️ **{nickname}**\n📜 **Rules accepted**"; body="### The gates are ready to open.\nYour adventure in Althérya can begin."
        else: title=f"# 👑 BIENVENUE, {nickname}"; info=f"🌍 **Français**\n✒️ **{nickname}**\n📜 **Règlement accepté**"; body="### Les portes sont prêtes à s’ouvrir.\nTon aventure à Althérya peut commencer."
        self.add_item(_container(discord.ui.TextDisplay(title),_sep(),discord.ui.TextDisplay(info),_sep(),discord.ui.TextDisplay(body),discord.ui.ActionRow(enter)))


class AdminUnregisterConfirmView(discord.ui.LayoutView):
    """Confirmation admin avant suppression complète de l'onboarding d'un membre."""
    def __init__(self, admin_id: int, member: discord.Member):
        super().__init__(timeout=180)
        self.admin_id = admin_id
        self.member = member

        cancel = discord.ui.Button(label="ANNULER", emoji="↩️", style=discord.ButtonStyle.secondary)
        confirm = discord.ui.Button(label="DÉSINSCRIRE", emoji="🗑️", style=discord.ButtonStyle.danger)

        async def cancel_cb(interaction: discord.Interaction):
            if interaction.user.id != self.admin_id:
                await interaction.response.send_message("⛔ Cette confirmation ne t'est pas destinée.", ephemeral=True)
                return
            closed = discord.ui.LayoutView(timeout=60)
            closed.add_item(_container(discord.ui.TextDisplay("### ↩️ Désinscription annulée.")))
            await interaction.response.edit_message(view=closed)

        async def confirm_cb(interaction: discord.Interaction):
            if interaction.user.id != self.admin_id:
                await interaction.response.send_message("⛔ Cette confirmation ne t'est pas destinée.", ephemeral=True)
                return
            if interaction.guild is None:
                await interaction.response.send_message("⚠️ Serveur introuvable.", ephemeral=True)
                return

            guild_id = interaction.guild.id
            user_id = self.member.id
            old = _state(guild_id, user_id)

            # Suppression totale de l'inscription : le prochain COMMENCER repart de zéro.
            DB.execute("DELETE FROM onboarding WHERE guild_id=? AND user_id=?", (guild_id, user_id))
            DB.commit()

            role_status = "Aucun rôle Membre configuré."
            member_role_id = _env_id("MEMBER_ROLE_ID")
            if member_role_id:
                role = interaction.guild.get_role(member_role_id)
                if role is None:
                    role_status = "⚠️ Rôle Membre configuré introuvable."
                elif role not in self.member.roles:
                    role_status = "Le rôle Membre n'était pas attribué."
                else:
                    try:
                        await self.member.remove_roles(role, reason=f"Désinscription Althérya par {interaction.user}")
                        role_status = "✅ Rôle Membre retiré."
                    except discord.Forbidden as exc:
                        role_status = "⚠️ Inscription supprimée, mais rôle Membre impossible à retirer (hiérarchie/permissions)."
                        print(f"[ACCUEIL ADMIN] remove role forbidden user={user_id}: {exc}")
                    except discord.HTTPException as exc:
                        role_status = "⚠️ Inscription supprimée, mais Discord a refusé le retrait du rôle."
                        print(f"[ACCUEIL ADMIN] remove role HTTP user={user_id}: {exc}")

            print(
                f"[ACCUEIL ADMIN] desinscription guild={guild_id} user={user_id} "
                f"admin={interaction.user.id} completed={old['completed']} nickname={old['nickname']!r}"
            )
            done = discord.ui.LayoutView(timeout=300)
            done.add_item(
                _container(
                    discord.ui.TextDisplay(
                        f"# 🗑️ JOUEUR DÉSINSCRIT\n"
                        f"**{discord.utils.escape_markdown(self.member.display_name)}** (`{self.member.id}`) a été supprimé de l'accueil Althérya.\n\n"
                        f"{role_status}\n\n"
                        "🌍 Langue : réinitialisée\n"
                        "📸 Identité OCR : réinitialisée\n"
                        "📜 Règlement : réinitialisé\n"
                        "🏰 Inscription : réinitialisée\n\n"
                        "Le joueur peut maintenant cliquer sur **COMMENCER** et refaire l'inscription depuis le début."
                    )
                )
            )
            await interaction.response.edit_message(view=done)

        cancel.callback = cancel_cb
        confirm.callback = confirm_cb
        self.add_item(
            _container(
                discord.ui.TextDisplay(
                    f"# ⚠️ DÉSINSCRIRE UN JOUEUR\n"
                    f"Tu vas réinitialiser complètement l'inscription de **{discord.utils.escape_markdown(member.display_name)}**.\n\n"
                    "Ses données d'accueil seront supprimées et son rôle Membre sera retiré s'il est configuré."
                ),
                _sep(),
                discord.ui.ActionRow(cancel, confirm),
            )
        )


def register(bot) -> None:
    """Ajoute /setup_accueil à l'arbre du bot principal avant sa synchronisation."""
    async def setup_accueil(interaction: discord.Interaction):
        # Vérification côté bot : compatible avec les versions discord.py où
        # app_commands.Command(...) n'accepte pas default_permissions=.
        if interaction.guild is None:
            await interaction.response.send_message(
                "⚠️ Cette commande doit être utilisée dans un serveur.", ephemeral=True
            )
            return
        if not interaction.permissions.administrator:
            await interaction.response.send_message(
                "⛔ Cette commande est réservée aux administrateurs.", ephemeral=True
            )
            return
        if not interaction.channel:
            await interaction.response.send_message("⚠️ Salon introuvable.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.send(view=WelcomePublicView())
        await interaction.followup.send("✅ Panneau d’accueil installé dans ce salon.", ephemeral=True)

    if bot.tree.get_command("setup_accueil") is None:
        command = app_commands.Command(
            name="setup_accueil",
            description="Installe le panneau d'accueil Althérya dans ce salon",
            callback=setup_accueil,
        )
        bot.tree.add_command(command)

    async def desinscrire(interaction: discord.Interaction, membre: discord.Member):
        if interaction.guild is None:
            await interaction.response.send_message("⚠️ Cette commande doit être utilisée dans un serveur.", ephemeral=True)
            return
        if not interaction.permissions.administrator:
            await interaction.response.send_message("⛔ Cette commande est réservée aux administrateurs.", ephemeral=True)
            return
        if membre.bot:
            await interaction.response.send_message("⚠️ Un bot ne possède pas d'inscription joueur Althérya.", ephemeral=True)
            return
        await interaction.response.send_message(
            view=AdminUnregisterConfirmView(interaction.user.id, membre),
            ephemeral=True,
        )

    if bot.tree.get_command("desinscrire") is None:
        command = app_commands.Command(
            name="desinscrire",
            description="Réinitialise complètement l'inscription Althérya d'un joueur",
            callback=desinscrire,
        )
        bot.tree.add_command(command)


def register_persistent_views(bot) -> None:
    """Rattache uniquement le panneau public persistant après un redémarrage."""
    bot.add_view(WelcomePublicView())
