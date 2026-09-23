"""Altherya Accueil — onboarding Discord séparé du RPG.

Chargé par main.py, mais toute la logique d'accueil reste isolée ici.
Parcours : Langue -> Pseudo -> Règlement -> Entrer.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

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
                    "✒️ **Identité**\nChoisis le nom sous lequel tu seras connu.\n\n"
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


class NickModal(discord.ui.Modal, title="✒️ Ton identité"):
    nickname = discord.ui.TextInput(
        label="Pseudo",
        placeholder="Le nom que tu porteras dans le royaume",
        min_length=2,
        max_length=32,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        name = str(self.nickname).strip()
        if isinstance(interaction.user, discord.Member):
            try:
                await interaction.user.edit(nick=name, reason="Onboarding Althérya")
            except discord.Forbidden:
                await interaction.response.send_message(
                    "⚠️ Je ne peux pas modifier ton pseudo. Donne-moi **Gérer les pseudos** et place mon rôle suffisamment haut.",
                    ephemeral=True,
                )
                return
            except discord.HTTPException:
                await interaction.response.send_message(
                    "⚠️ Discord a refusé ce pseudo. Essaie un autre nom.", ephemeral=True
                )
                return
        _save(_gid(interaction), interaction.user.id, nickname=name)
        await interaction.response.edit_message(view=RulesView(_gid(interaction), interaction.user.id))


class IdentityView(discord.ui.LayoutView):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=1800)
        state = _state(guild_id, user_id)
        back = discord.ui.Button(label="Retour", emoji="↩️", style=discord.ButtonStyle.secondary)
        choose = discord.ui.Button(label="CHOISIR MON PSEUDO", emoji="✒️", style=discord.ButtonStyle.primary)

        async def back_cb(interaction: discord.Interaction):
            await interaction.response.edit_message(view=LanguageView())

        async def choose_cb(interaction: discord.Interaction):
            await interaction.response.send_modal(NickModal())

        back.callback = back_cb
        choose.callback = choose_cb
        self.add_item(
            _container(
                discord.ui.TextDisplay("## ✒️ TON IDENTITÉ\n**ÉTAPE 02 / 03**"),
                _sep(),
                discord.ui.TextDisplay(
                    "### Chaque aventurier doit porter un nom.\nCe nom deviendra ton **pseudo sur le serveur**."
                ),
                discord.ui.TextDisplay(f"🌍 Langue choisie : **{state['language'] or '—'}**"),
                _sep(),
                discord.ui.ActionRow(back, choose),
                _sep(),
                discord.ui.TextDisplay("**● ━ ● ━ ○**   Langue • Identité • Règlement"),
            )
        )


class RulesView(discord.ui.LayoutView):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=1800)
        back = discord.ui.Button(label="Modifier mon pseudo", emoji="↩️", style=discord.ButtonStyle.secondary)
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
