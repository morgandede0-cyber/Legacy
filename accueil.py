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


class WelcomePublicView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        start = discord.ui.Button(
            label="COMMENCER",
            emoji="👑",
            style=discord.ButtonStyle.primary,
            custom_id="altherya_accueil:start",
        )
        start.callback = self._start
        self.add_item(
            _container(
                discord.ui.TextDisplay("# 👑  A L T H É R Y A\n### BIENVENUE DANS LE ROYAUME"),
                _sep(),
                discord.ui.TextDisplay(
                    "Une nouvelle aventure commence ici.\n\n"
                    "Avant que les portes d’Althérya ne s’ouvrent, prépare ton arrivée en **3 étapes**."
                ),
                _sep(),
                discord.ui.TextDisplay(
                    "🌍 **Langue**\nChoisis la langue que tu souhaites utiliser.\n\n"
                    "📸 **Identité**\nEnvoie ton screen Informations joueur : ton pseudo sera détecté automatiquement.\n\n"
                    "📜 **Lois du Royaume**\nPrends connaissance du règlement."
                ),
                _sep(),
                discord.ui.ActionRow(start),
                discord.ui.TextDisplay("-# Althérya • Les portes du royaume attendent ton arrivée."),
            )
        )

    async def _start(self, interaction: discord.Interaction):
        if _state(_gid(interaction), interaction.user.id)["completed"]:
            await interaction.response.send_message(
                "👑 Ton inscription est déjà terminée. Bienvenue à Althérya !", ephemeral=True
            )
            return
        await interaction.response.send_message(view=LanguageView(), ephemeral=True)


class LanguageView(discord.ui.LayoutView):
    LANGS = [
        ("Français", "🇫🇷", "fr"),
        ("English", "🇬🇧", "en"),
        ("Español", "🇪🇸", "es"),
        ("Deutsch", "🇩🇪", "de"),
        ("Português", "🇵🇹", "pt"),
    ]

    def __init__(self):
        super().__init__(timeout=1800)
        buttons = []
        for label, emoji, code in self.LANGS:
            button = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.secondary)

            async def choose(interaction: discord.Interaction, chosen=label):
                _save(_gid(interaction), interaction.user.id, language=chosen)
                await interaction.response.edit_message(view=IdentityView(_gid(interaction), interaction.user.id))

            button.callback = choose
            buttons.append(button)
        self.add_item(
            _container(
                discord.ui.TextDisplay("## 🌍 TON VOYAGE COMMENCE ICI\n**ÉTAPE 01 / 03**"),
                _sep(),
                discord.ui.TextDisplay("### Quelle langue parlera-t-on durant ton aventure ?"),
                discord.ui.ActionRow(*buttons[:4]),
                discord.ui.ActionRow(buttons[4]),
                _sep(),
                discord.ui.TextDisplay("**● ━ ○ ━ ○**   Langue • Identité • Règlement"),
            )
        )


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
        confirm = discord.ui.Button(label="CONFIRMER", emoji="✅", style=discord.ButtonStyle.success)
        retry = discord.ui.Button(label="RENVOYER UN SCREEN", emoji="📸", style=discord.ButtonStyle.secondary)

        async def confirm_cb(interaction: discord.Interaction):
            if interaction.user.id != user_id:
                await interaction.response.send_message("⛔ Cette identification ne t'appartient pas.", ephemeral=True)
                return
            if isinstance(interaction.user, discord.Member):
                try:
                    await interaction.user.edit(nick=self.nickname, reason="Identification OCR Althérya")
                except (discord.Forbidden, discord.HTTPException) as exc:
                    await _alert_admins(interaction, "Discord refuse le renommage du membre", detected=self.nickname)
                    await interaction.response.edit_message(view=IdentityErrorView(guild_id, user_id, "Le renommage Discord a échoué. Un administrateur a été prévenu."))
                    return
            _save(guild_id, user_id, nickname=self.nickname)
            await interaction.response.edit_message(view=RulesView(guild_id, user_id))

        async def retry_cb(interaction: discord.Interaction):
            await interaction.response.edit_message(view=IdentityView(guild_id, user_id))

        confirm.callback = confirm_cb
        retry.callback = retry_cb
        self.add_item(_container(
            discord.ui.TextDisplay("## 🔎 IDENTITÉ DÉTECTÉE\n**ÉTAPE 02 / 03**"), _sep(),
            discord.ui.TextDisplay(f"### Pseudo détecté\n# **{discord.utils.escape_markdown(nickname)}**\n\nConfirme uniquement si ce pseudo correspond exactement à celui affiché sur ton screen."),
            discord.ui.ActionRow(retry, confirm), _sep(),
            discord.ui.TextDisplay("**● ━ ● ━ ○**   Langue • Identité • Règlement"),
        ))


class IdentityErrorView(discord.ui.LayoutView):
    def __init__(self, guild_id: int, user_id: int, reason: str):
        super().__init__(timeout=1800)
        retry = discord.ui.Button(label="ENVOYER UN NOUVEAU SCREEN", emoji="📸", style=discord.ButtonStyle.primary)
        async def retry_cb(interaction: discord.Interaction):
            await interaction.response.edit_message(view=IdentityView(guild_id, user_id))
        retry.callback = retry_cb
        self.add_item(_container(
            discord.ui.TextDisplay("## ⚠️ IDENTIFICATION IMPOSSIBLE\n**ÉTAPE 02 / 03**"), _sep(),
            discord.ui.TextDisplay(f"{reason}\n\nL'équipe d'administration a été prévenue. Tu peux envoyer un nouveau screen puis réessayer."),
            discord.ui.ActionRow(retry),
        ))


class ScreenUploadModal(discord.ui.Modal, title="Identification Althérya"):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.user_id = user_id
        self.upload = discord.ui.FileUpload(
            custom_id="altherya_identity_screen",
            required=True,
            min_values=1,
            max_values=1,
        )
        self.add_item(discord.ui.Label(
            text="Capture Informations joueur",
            description="Ajoute une capture complète de ton profil (PNG/JPG/WEBP).",
            component=self.upload,
        ))

    async def on_submit(self, interaction: discord.Interaction):
        # IMPORTANT: une modale contenant FileUpload est une interaction Components V2.
        # Discord refuse alors tout champ `content` dans la réponse (50035).
        # Toutes les réponses de cette modale sont donc rendues uniquement via LayoutView.
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                view=IdentityErrorView(self.guild_id, self.user_id, "Cette identification ne t'appartient pas."),
                ephemeral=True,
            )
            return
        attachments = self.upload.values
        if not attachments:
            await interaction.response.send_message(
                view=IdentityErrorView(self.guild_id, self.user_id, "Aucun screen n'a été reçu."),
                ephemeral=True,
            )
            return
        attachment = attachments[0]
        ctype = (attachment.content_type or "").lower()
        if ctype not in ALLOWED_IMAGE_TYPES and not attachment.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            await _alert_admins(interaction, "Fichier non image envoyé dans l'identification")
            await interaction.response.send_message(
                view=IdentityErrorView(self.guild_id, self.user_id, "Le fichier doit être une image PNG, JPG ou WEBP."),
                ephemeral=True,
            )
            return
        try:
            image_bytes = await attachment.read()
            nickname, confidence = _ocr_nickname(image_bytes)
        except Exception as exc:
            await _alert_admins(interaction, f"Lecture du screen impossible ({type(exc).__name__})")
            await interaction.response.send_message(
                view=IdentityErrorView(self.guild_id, self.user_id, "Je n'ai pas réussi à lire ce screen."),
                ephemeral=True,
            )
            return
        if len(nickname) < 2 or confidence < 45:
            await _alert_admins(interaction, "OCR incertain", image_bytes, nickname, confidence)
            await interaction.response.send_message(
                view=IdentityErrorView(self.guild_id, self.user_id, "Le pseudo n'a pas pu être lu avec suffisamment de certitude."),
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
        state = _state(guild_id, user_id)
        back = discord.ui.Button(label="Retour", emoji="↩️", style=discord.ButtonStyle.secondary)
        upload = discord.ui.Button(label="ENVOYER MON SCREEN", emoji="📷", style=discord.ButtonStyle.primary)

        async def back_cb(interaction: discord.Interaction):
            await interaction.response.edit_message(view=LanguageView())

        async def upload_cb(interaction: discord.Interaction):
            if interaction.user.id != user_id:
                await interaction.response.send_message("⛔ Cette identification ne t'appartient pas.", ephemeral=True)
                return
            await interaction.response.send_modal(ScreenUploadModal(guild_id, user_id))

        back.callback = back_cb
        upload.callback = upload_cb
        self.add_item(_container(
            discord.ui.TextDisplay("## 📸 IDENTIFICATION\n**ÉTAPE 02 / 03**"), _sep(),
            discord.ui.TextDisplay(
                "### Envoie ton screen **Informations joueur**.\n"
                "Appuie sur **ENVOYER MON SCREEN** : Discord ouvrira une petite fenêtre où tu pourras sélectionner ta capture.\n\n"
                "Althérya analysera automatiquement **uniquement la zone du pseudo**.\n"
                "-# Aucune saisie manuelle du pseudo n'est autorisée."
            ),
            discord.ui.TextDisplay(f"🌍 Langue choisie : **{state['language'] or '—'}**"), _sep(),
            discord.ui.ActionRow(back, upload), _sep(),
            discord.ui.TextDisplay("**● ━ ● ━ ○**   Langue • Identité • Règlement"),
        ))


class RulesView(discord.ui.LayoutView):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=1800)
        back = discord.ui.Button(label="Retour à l’identification", emoji="↩️", style=discord.ButtonStyle.secondary)
        accept = discord.ui.Button(label="J'ACCEPTE", emoji="✅", style=discord.ButtonStyle.success)
        rules_channel_id = _env_id("RULES_CHANNEL_ID")

        async def back_cb(interaction: discord.Interaction):
            await interaction.response.edit_message(view=IdentityView(_gid(interaction), interaction.user.id))

        async def accept_cb(interaction: discord.Interaction):
            _save(_gid(interaction), interaction.user.id, rules=True)
            await interaction.response.edit_message(view=FinalView(_gid(interaction), interaction.user.id))

        back.callback = back_cb
        accept.callback = accept_cb
        components = [
            discord.ui.TextDisplay("## 📜 LES LOIS DU ROYAUME\n**ÉTAPE 03 / 03**"),
            _sep(),
            discord.ui.TextDisplay(
                "Toute communauté a besoin de quelques règles.\n\n"
                "🤝 **Respecte les autres membres**\n"
                "💬 **Utilise chaque salon à bon escient**\n"
                "🛡️ **Harcèlement et discrimination interdits**\n"
                "⚖️ **Respecte les décisions de la modération**"
            ),
            _sep(),
            discord.ui.TextDisplay(
                "En continuant, tu confirmes avoir lu et accepté le règlement complet du serveur."
            ),
        ]
        if rules_channel_id and guild_id:
            components.append(
                discord.ui.ActionRow(
                    discord.ui.Button(
                        label="VOIR LE RÈGLEMENT",
                        emoji="📖",
                        style=discord.ButtonStyle.link,
                        url=f"https://discord.com/channels/{guild_id}/{rules_channel_id}",
                    )
                )
            )
        components.extend(
            [
                discord.ui.ActionRow(back, accept),
                _sep(),
                discord.ui.TextDisplay("**● ━ ● ━ ●**   Langue • Identité • Règlement"),
            ]
        )
        self.add_item(_container(*components))


class FinalView(discord.ui.LayoutView):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=1800)
        state = _state(guild_id, user_id)
        nickname = discord.utils.escape_markdown(state["nickname"] or "Aventurier")
        enter = discord.ui.Button(
            label="ENTRER DANS LE ROYAUME", emoji="🏰", style=discord.ButtonStyle.success
        )

        async def enter_cb(interaction: discord.Interaction):
            current = _state(_gid(interaction), interaction.user.id)
            if not (current["language"] and current["nickname"] and current["rules"]):
                await interaction.response.send_message("⚠️ Ton inscription est incomplète.", ephemeral=True)
                return
            member_role_id = _env_id("MEMBER_ROLE_ID")
            if member_role_id:
                if not interaction.guild or not isinstance(interaction.user, discord.Member):
                    await interaction.response.send_message("⚠️ Cette étape doit être terminée sur le serveur.", ephemeral=True)
                    return
                role = interaction.guild.get_role(member_role_id)
                if role is None:
                    await interaction.response.send_message(
                        "⚠️ Le rôle Membre configuré est introuvable. Vérifie `MEMBER_ROLE_ID`.", ephemeral=True
                    )
                    return
                try:
                    await interaction.user.add_roles(role, reason="Onboarding Althérya terminé")
                except discord.Forbidden:
                    await interaction.response.send_message(
                        "⚠️ Je ne peux pas attribuer le rôle Membre. Place mon rôle au-dessus du rôle Membre.",
                        ephemeral=True,
                    )
                    return
            _save(_gid(interaction), interaction.user.id, completed=True)
            done = discord.ui.LayoutView(timeout=300)
            done.add_item(
                _container(
                    discord.ui.TextDisplay(
                        f"# 👑 BIENVENUE, {discord.utils.escape_markdown(current['nickname'])}\n"
                        "### Les portes du royaume sont ouvertes.\n\n"
                        "Ton aventure à **Althérya** peut commencer."
                    )
                )
            )
            await interaction.response.edit_message(view=done)

        enter.callback = enter_cb
        self.add_item(
            _container(
                discord.ui.TextDisplay(f"# 👑 BIENVENUE, {nickname}"),
                _sep(),
                discord.ui.TextDisplay(
                    f"🌍 **{state['language'] or '—'}**\n"
                    f"✒️ **{nickname}**\n"
                    "📜 **Règlement accepté**"
                ),
                _sep(),
                discord.ui.TextDisplay(
                    "### Les portes sont prêtes à s’ouvrir.\nTon aventure à Althérya peut commencer."
                ),
                discord.ui.ActionRow(enter),
            )
        )


def register(bot) -> None:
    """Ajoute /setup_accueil à l'arbre du bot principal avant sa synchronisation."""
    if bot.tree.get_command("setup_accueil") is not None:
        return

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

    command = app_commands.Command(
        name="setup_accueil",
        description="Installe le panneau d'accueil Althérya dans ce salon",
        callback=setup_accueil,
    )
    bot.tree.add_command(command)


def register_persistent_views(bot) -> None:
    """Rattache uniquement le panneau public persistant après un redémarrage."""
    bot.add_view(WelcomePublicView())
