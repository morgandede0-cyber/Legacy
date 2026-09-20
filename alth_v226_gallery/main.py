import os
import asyncio
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Environment and shared economy MUST be initialized before importing game modules.
# Several modules create stores at import time; importing them first could sync a zero
# PostgreSQL wallet into the legacy SQLite file before its initial migration.
load_dotenv()
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
from shared_economy import (
    migrate_legacy_wallets, pending_events, mark_event_processed,
    enabled as shared_economy_enabled, diagnostics as shared_economy_diagnostics,
    recover_known_legacy_wallet,
)
MIGRATED_GOLD_PLAYERS = migrate_legacy_wallets(DATA / "legacy.sqlite3")
# Recovery unique du solde Altherya historique constaté avant le passage au wallet partagé.
RECOVERED_LEGACY_WALLET = recover_known_legacy_wallet(666805849011912705, 101000643)

import discord
from discord.ext import commands, tasks
from discord import app_commands
from economy import Economy
from arena_engine import ArenaStore, BattleState, Fighter, CLASSES, CHAMPION_PROFILES, class_line, choose_first, resolve_action, bot_choose_action
from expedition_engine import ExpeditionStore, EXPEDITIONS, LOCATION_META, TOOL_META, TOOL_LEVELS, BAG_LEVELS, UPGRADE_RECIPES, BAG_UPGRADE_RECIPES, STARTER_GEAR, RESOURCE_SELL_PRICES, EXPEDITION_OBJECTS, RARITY, RARITY_EMOJI, format_duration, loot_lines
from dark_alley import (DarkAlleyStore, HEIST_ATTEMPTS, HEIST_CODE_LENGTH, GUARD_ENTRY_FEE,
                        INVITATION_ITEM, ACTION_COOLDOWN, ALLEY_BAN_SECONDS, short_time)
from casino_engine import (CasinoStore, MAX_BET, VIP_MAX_BET, MIN_BET, SLOT_SYMBOLS, draw_slot, slot_multiplier, roulette_spin)
from casino_render import render_blackjack, render_roulette_strip, render_slot_machine, render_horse_race, EUROPEAN_WHEEL
from castle_engine import CastleStore, DAILY_REWARD, DAILY_XP, QUESTS, QUEST_GLOBAL_GOLD, QUEST_GLOBAL_XP, level_from_xp
import random
from progression import FORGE_LEVEL_REQUIREMENTS, FORGE_GOLD_COSTS, XP_REWARDS, EXPEDITION_XP
from achievements import AchievementStore, ACHIEVEMENTS, RARITIES
from admin_engine import AdminStore, EVENTS
from tavern_engine import TavernGameStore, MIN_TAVERN_BET, MAX_TAVERN_BET, TAVERN_ROUND_COST, roll_die, flip_coin, rps_bot, rps_result
from tavern_render import render_dice, render_coin, render_rps
from story_engine import StoryStore, SEASON_1_CHAPTERS, SEASON_1_TITLES, SEASON_1_TEXTS, STORY_REQUIREMENTS, ALL_STORY_ITEMS, STORY_ITEM_PRICES
from gazette_engine import GazetteStore
from expedition_render import render_expedition_live_card
from job_board_engine import JobBoardStore, RARITIES as JOB_RARITIES
import legacy_world_forge as WORLD_FORGE
import tower_engine as TOWER
from world_engine import current_event, destination_name, destination_description
from ui_v2 import container as v2_container, header as v2_header, separator as v2_separator, media_gallery as v2_media_gallery, action_row as v2_action_row
TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
GUILD_ID = os.getenv("GUILD_ID", "").strip()
PLACES = BASE / "assets" / "places"
TRANSITIONS = BASE / "assets" / "transitions"
EXPEDITION_LIVE_ASSETS = DATA / "expedition_live"
EXPEDITION_LIVE_ASSETS.mkdir(parents=True, exist_ok=True)
HUB_STATE_FILE = DATA / "hub_message.json"
if shared_economy_enabled():
    _eco_diag = shared_economy_diagnostics()
    print(f"[ECONOMIE COMMUNE] PostgreSQL actif • migration initiale: {MIGRATED_GOLD_PLAYERS} joueur(s) • récupération historique: {'oui' if RECOVERED_LEGACY_WALLET else 'non'} • db={_eco_diag['database']} • host={_eco_diag['host']}:{_eco_diag['port']} • wallets={_eco_diag['wallets']} • empreinte={_eco_diag['fingerprint']}")
else:
    print("[ECONOMIE COMMUNE] désactivée : ECONOMY_DATABASE_URL absente")
ECONOMY = Economy(DATA / "legacy.sqlite3")
ARENA_STORE = ArenaStore(DATA / "legacy.sqlite3")
EXPEDITION_STORE = ExpeditionStore(DATA / "legacy.sqlite3")
DARK_STORE = DarkAlleyStore(DATA / "legacy.sqlite3")
CASINO_STORE = CasinoStore(DATA / "legacy.sqlite3")
CASTLE_STORE = CastleStore(DATA / "legacy.sqlite3")
ACHIEVEMENT_STORE = AchievementStore(DATA / "legacy.sqlite3")
ADMIN_STORE = AdminStore(DATA / "legacy.sqlite3")
TAVERN_STORE = TavernGameStore(DATA / "legacy.sqlite3")
STORY_STORE = StoryStore(DATA / "legacy.sqlite3")
GAZETTE_STORE = GazetteStore(DATA / "legacy.sqlite3")
JOB_BOARD_STORE = JobBoardStore(DATA / "legacy.sqlite3")
RECOVERED_CASINO_GAMES = CASINO_STORE.recover_unfinished()
RECOVERED_ARENA_BATTLES = ARENA_STORE.recover_unfinished()
RECOVERED_TAVERN_GAMES = TAVERN_STORE.recover_unfinished()
ACTIVE_BATTLES: dict[str, BattleState] = {}
BATTLE_TIMEOUTS: dict[str, asyncio.Task] = {}
EXPEDITION_MONITORS: dict[str, asyncio.Task] = {}

DESTINATIONS = {
    "market":      {"label":"Marché",          "emoji":"🛒", "image":"market.png",      "transition":"to_market.gif"},
    "tavern":      {"label":"Taverne",         "emoji":"🍺", "image":"tavern.png",      "transition":"to_tavern.gif"},
    "bank":        {"label":"Banque",          "emoji":"🏦", "image":"bank.png",        "transition":"to_bank.gif"},
    "forge":       {"label":"Forge",           "emoji":"⚒️", "image":"forge.png",       "transition":"to_forge.gif"},
    "arena":       {"label":"Arène",           "emoji":"⚔️", "image":"arena.png",       "transition":"to_arena.gif"},
    "expeditions": {"label":"Petites annonces", "emoji":"📌", "image":"expeditions.png", "transition":"to_expeditions.gif"},
    "alley":       {"label":"Ruelle sombre",   "emoji":"🌑", "image":"alley.png",       "transition":"to_alley.gif"},
    "castle":      {"label":"Château",         "emoji":"🏰", "image":"castle.png",      "transition":"to_castle.gif"},
}

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

async def safe_defer(interaction: discord.Interaction):
    if not interaction.response.is_done():
        await interaction.response.defer()


def _level_up_embed(info: dict) -> discord.Embed:
    old_level=int(info['old_level']); new_level=int(info['new_level'])
    old_hp=int(info['old_hp']); new_hp=int(info['new_hp'])
    unlocks=[]
    if new_level == 3:
        unlocks.append('⚒️ **Forge de KHAZ’GORAM débloquée**')
    if new_level == 5:
        unlocks.append('🗼 **Tour d’Ashkar débloquée**')
    desc=(
        f'**Niveau {old_level} → {new_level}**\n\n'
        f'❤️ PV de base max : **{old_hp} → {new_hp}**\n'
        f'🩸 **+{new_hp-old_hp} PV permanents**'
    )
    if unlocks:
        desc += '\n\n🔓 **NOUVEAU CONTENU**\n' + '\n'.join(unlocks)
    e=discord.Embed(title='⭐ NIVEAU SUPÉRIEUR !', description=desc, color=discord.Color.gold())
    e.set_footer(text='Altherya • Ta progression devient plus puissante à chaque niveau')
    return e


async def show_pending_levelups(surface, user_id: int):
    """Affiche chaque montée de niveau en attente sans bloquer la récompense principale."""
    events=CASTLE_STORE.pending_levelups(user_id, consume=True)
    if not events:
        return
    try:
        for info in events:
            if int(info['new_level']) in {10,20,30,40,50}:
                GAZETTE_STORE.record_event('level_milestone', user_id, int(info['new_level']))
            embed=_level_up_embed(info)
            if isinstance(surface, discord.Interaction):
                if surface.response.is_done():
                    await surface.followup.send(embed=embed, ephemeral=True)
                else:
                    await surface.response.send_message(embed=embed, ephemeral=True)
            elif isinstance(surface, discord.Message):
                await surface.channel.send(content=f'<@{int(user_id)}>', embed=embed, delete_after=45)
    except Exception as exc:
        print(f'[LEVELUP] affichage impossible pour {user_id}: {exc}')


async def announce_player_log(guild: discord.Guild | None, user, action: str, *, category: str = "Action", details: str | None = None):
    """Journal admin complet configuré avec /logs. Rien n'est publié si aucun salon n'est défini."""
    if guild is None:
        return
    channel_id = ACHIEVEMENT_STORE.get_log_channel(guild.id)
    if not channel_id:
        return
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        member = user
        mention = getattr(member, "mention", f"<@{getattr(member, 'id', user)}>")
        embed = discord.Embed(
            title=f"📋 {category}",
            description=f"{mention}\n**{action}**" + (f"\n{details}" if details else ""),
            color=discord.Color.dark_grey(),
        )
        avatar = getattr(getattr(member, "display_avatar", None), "url", None)
        if avatar:
            embed.set_thumbnail(url=avatar)
        embed.set_footer(text="Altherya • Logs administrateur")
        await channel.send(embed=embed)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
        pass


async def announce_public_result(guild: discord.Guild | None, user, title: str, description: str, *, color=discord.Color.gold()):
    """Publie un résultat public compact dans le salon configuré avec /succes."""
    if guild is None:
        return
    channel_id = ACHIEVEMENT_STORE.get_channel(guild.id)
    if not channel_id:
        return
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        mention = getattr(user, "mention", f"<@{getattr(user, 'id', user)}>")
        embed = discord.Embed(
            title=title,
            description=f"{mention} {description}",
            color=color,
        )
        embed.set_footer(text="Altherya • Résultats publics")
        await channel.send(embed=embed)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
        pass


# V1.70 — Les expéditions sont privées dans leur zone, mais leur départ/retour
# est raconté publiquement dans le salon configuré avec /succes.
def _expedition_public_embed(run, *, finished: bool = False) -> discord.Embed:
    zone = EXPEDITIONS[run.expedition_key]
    location = LOCATION_META[zone["location_key"]]
    activity = {
        "axe": "couper du bois",
        "pickaxe": "extraire des minerais",
        "spear": "chasser",
    }.get(run.tool_key, _activity_label(run.tool_key).lower())
    activity_emoji = _activity_emoji(run.tool_key)
    if finished:
        total = sum((run.loot or {}).values())
        description = (
            f"<@{run.user_id}> est revenu de **{location['name']}**.\n"
            f"{activity_emoji} Activité : **{activity}**\n"
            f"📦 Récolte rapportée : **{total}/{run.capacity} objets**"
        )
        embed = discord.Embed(title="✅ EXPÉDITION TERMINÉE", description=description, color=discord.Color.green())
    else:
        description = (
            f"{activity_emoji} <@{run.user_id}> est parti **{activity}** dans **{location['name']}**.\n"
            f"🗺️ Destination : **{zone['name']}**\n"
            f"⏳ Durée : **{zone['duration_label']}**\n\n"
            "*Que les terres d’Elyndor lui soient favorables...*"
        )
        embed = discord.Embed(title="🧭 EXPÉDITION EN COURS", description=description, color=discord.Color.dark_gold())
    embed.set_footer(text="Altherya • Expéditions")
    return embed


async def announce_expedition_start(guild: discord.Guild | None, run):
    """Publie UNE annonce publique et mémorise son message pour le mettre à jour au retour."""
    if guild is None:
        return None
    channel_id = ACHIEVEMENT_STORE.get_channel(guild.id)
    if not channel_id:
        return None
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        message = await channel.send(embed=_expedition_public_embed(run, finished=False))
        EXPEDITION_STORE.bind_status_message(run.run_id, message.channel.id, message.id)
        return message
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError) as exc:
        print(f"[EXPEDITION V1.70] annonce publique impossible : {exc}")
        return None


async def finish_expedition_announcement(run):
    """Transforme l'annonce de départ en résultat, sans créer un second message public."""
    message = await _get_expedition_status_message(run)
    if message is None:
        return
    try:
        await message.edit(embed=_expedition_public_embed(run, finished=True), content=None, view=None)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


async def announce_gold_activity(guild: discord.Guild | None, user, delta: int, reason: str, *, counterpart=None, details: str | None = None, public: bool = True):
    """
    Journalise tous les mouvements de Gold dans /logs.
    Le salon public /succes ne montre QUE les gains/pertes liés aux jeux de la Taverne
    ou de la salle clandestine, afin de préserver la vie privée économique des joueurs.
    """
    if guild is None or int(delta) == 0:
        return

    amount = abs(int(delta))
    gain = int(delta) > 0
    mention = getattr(user, "mention", f"<@{getattr(user, 'id', user)}>")
    counterpart_line = None
    if counterpart is not None:
        counterpart_line = getattr(counterpart, "mention", f"<@{getattr(counterpart, 'id', counterpart)}>")

    # Journal privé /logs : tous les mouvements économiques.
    log_details = f"Variation : **{'+' if gain else '-'}{amount} Gold**"
    if counterpart_line:
        log_details += f"\nJoueur concerné : {counterpart_line}"
    if details:
        log_details += f"\n{details}"
    await announce_player_log(guild, user, reason, category="Mouvement de Gold", details=log_details)

    # Certaines actions (ex. vol entre deux joueurs) génèrent deux mouvements économiques
    # mais un seul message public combiné. Les deux mouvements restent détaillés dans /logs.
    if not public:
        return

    # Salon public succès : jeux de Taverne/Casino + résultats économiques de la Ruelle sombre.
    # Les achats, ventes, banque, forge, récompenses, etc. restent strictement privés.
    public_reason = reason.casefold()
    is_public_game = public_reason.startswith("casino —") or public_reason.startswith("taverne —")
    is_public_theft = (
        public_reason.startswith("vol réussi contre")
        or public_reason.startswith("victime d'un vol par")
        or public_reason.startswith("vol raté :")
        or public_reason.startswith("a surpris ")
    )
    is_public_heist = (
        public_reason.startswith("braquage réussi")
        or public_reason.startswith("amende après un braquage raté")
    )
    if not (is_public_game or is_public_theft or is_public_heist):
        return

    channel_id = ACHIEVEMENT_STORE.get_channel(guild.id)
    if not channel_id:
        return
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        color = discord.Color.green() if gain else discord.Color.red()
        if is_public_game:
            title = "🎲 GAIN DE JEU" if gain else "🎲 PERTE DE JEU"
            label = "Jeu"
        elif is_public_theft:
            title = "🐺 GAIN — VOL" if gain else "💥 PERTE — VOL"
            label = "Résultat"
        else:
            title = "🏦 BRAQUAGE RÉUSSI" if gain else "🚨 BRAQUAGE RATÉ"
            label = "Résultat"
        desc = f"{mention} **{'gagne' if gain else 'perd'} {amount} Gold**.\n**{label} :** {reason}"
        if counterpart_line:
            desc += f"\n**Joueur concerné :** {counterpart_line}"
        e = discord.Embed(title=title, description=desc, color=color)
        avatar = getattr(getattr(user, "display_avatar", None), "url", None)
        if avatar:
            e.set_thumbnail(url=avatar)
        e.set_footer(text="Altherya • Résultats publics")
        await channel.send(embed=e)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
        pass

class WorldHubView(discord.ui.View):
    """Carte du monde. Le premier clic public crée UNE session privée, puis elle s'auto-actualise."""
    def __init__(self, private_session: bool = False):
        super().__init__(timeout=None if not private_session else 1800)
        self.private_session = bool(private_session)
        legacy_btn = discord.ui.Button(label="Altherya", emoji="👑", style=discord.ButtonStyle.primary, custom_id="legacy:world:city", row=0)
        forge_btn = discord.ui.Button(label="La Forge de KHAZ'GORAM", emoji="⚒️", style=discord.ButtonStyle.secondary, custom_id="legacy:world:khaz", row=0)
        tower_btn = discord.ui.Button(label="La Tour d’Ashkar", emoji="🗼", style=discord.ButtonStyle.danger, custom_id="legacy:world:ashkar", row=0)
        forest_btn = discord.ui.Button(label="Forêt d'Elarwyn", emoji="🌲", style=discord.ButtonStyle.success, custom_id="altherya:world:elarwyn", row=1)
        mountain_btn = discord.ui.Button(label="Mont Vorak", emoji="🏔️", style=discord.ButtonStyle.secondary, custom_id="altherya:world:vorak", row=1)

        async def legacy_cb(interaction: discord.Interaction):
            file = discord.File(PLACES / "hub.png", filename="legacy.png")
            if self.private_session:
                await interaction.response.edit_message(
                    content="🏙️ **Altherya**\nBienvenue dans la cité. Choisis ta destination.",
                    attachments=[file], embeds=[], view=HubView(private_session=True)
                )
            else:
                await interaction.response.send_message(
                    content="🏙️ **Altherya**\nBienvenue dans la cité. Choisis ta destination.",
                    file=file, view=HubView(private_session=True), ephemeral=True
                )

        async def forge_cb(interaction: discord.Interaction):
            level = CASTLE_STORE.current_level(interaction.user.id)
            if level < 3:
                text = f"🔒 **La Forge de KHAZ'GORAM** se débloque au **niveau 3**.\nTon niveau actuel : **{level}**."
                if self.private_session:
                    await interaction.response.edit_message(content=text, attachments=[], embeds=[], view=WorldHubView(private_session=True))
                else:
                    await interaction.response.send_message(text, ephemeral=True)
                return
            file = discord.File(WORLD_FORGE.KHAZ_GORAM, filename="khaz_goram.png")
            embed = discord.Embed(
                title="⚒️ La Forge de KHAZ'GORAM",
                description="Une forge gigantesque, perdue loin de Altherya. **Thorgar** y façonne les équipements des légendes.",
                color=0xB67A2A,
            )
            embed.set_image(url="attachment://khaz_goram.png")
            if self.private_session:
                await interaction.response.edit_message(content=None, embed=embed, attachments=[file], view=WORLD_FORGE.KhazGoramView())
            else:
                await interaction.response.send_message(embed=embed, file=file, view=WORLD_FORGE.KhazGoramView(), ephemeral=True)

        async def tower_cb(interaction: discord.Interaction):
            await TOWER.show_lobby(interaction, edit=self.private_session)

        async def forest_cb(interaction: discord.Interaction):
            await open_exploration_location(interaction, "elarwyn", edit=self.private_session)

        async def mountain_cb(interaction: discord.Interaction):
            await open_exploration_location(interaction, "vorak", edit=self.private_session)

        legacy_btn.callback = legacy_cb
        forge_btn.callback = forge_cb
        tower_btn.callback = tower_cb
        forest_btn.callback = forest_cb
        mountain_btn.callback = mountain_cb
        self.add_item(legacy_btn); self.add_item(forge_btn); self.add_item(tower_btn)
        self.add_item(forest_btn); self.add_item(mountain_btn)

class HubView(discord.ui.View):
    def __init__(self, private_session: bool = False):
        super().__init__(timeout=None if not private_session else 1800)
        self.private_session = bool(private_session)
        for key, data in DESTINATIONS.items():
            button = discord.ui.Button(
                label=data["label"], emoji=data["emoji"],
                style=discord.ButtonStyle.secondary,
                custom_id=f"legacy:hub:{key}"
            )
            async def callback(interaction: discord.Interaction, destination=key):
                await travel(interaction, destination, edit=self.private_session)
            button.callback = callback
            self.add_item(button)

        board = discord.ui.Button(label="Panneau central", emoji="📋", style=discord.ButtonStyle.primary,
                                  custom_id="legacy:hub:central_board")
        async def board_cb(interaction: discord.Interaction):
            # Public -> crée la session privée. Privé -> réutilise exactement la même fenêtre.
            if self.private_session:
                await safe_defer(interaction)
                await show_central_board(interaction)
            else:
                await interaction.response.send_message("📋 **Tu consultes le panneau central...**", ephemeral=True)
                await show_central_board(interaction)
        board.callback = board_cb
        self.add_item(board)
        world = discord.ui.Button(label="Monde", emoji="🌍", style=discord.ButtonStyle.secondary, custom_id="legacy:hub:world")
        async def world_cb(interaction: discord.Interaction):
            file = discord.File(WORLD_FORGE.WORLD_MAP, filename="elyndor_map.png")
            embed = discord.Embed(title="🌍 Le Monde d\'Elyndor", description="Le brouillard recouvre les destinations encore inconnues. **Altherya** et **KHAZ\'GORAM** sont accessibles.", color=0xB67A2A)
            embed.set_image(url="attachment://elyndor_map.png")
            if self.private_session:
                await interaction.response.edit_message(content=None, embed=embed, attachments=[file], view=WorldHubView(private_session=True))
            else:
                await interaction.response.send_message(embed=embed, file=file, view=WorldHubView(private_session=True), ephemeral=True)
        world.callback = world_cb
        self.add_item(world)


# ============================================================
# V2.10 — HUBS COMPONENTS V2
# Les anciennes classes restent au-dessus pour compatibilité historique,
# mais les alias ci-dessous deviennent les interfaces actives.
# ============================================================
class WorldHubV2(discord.ui.LayoutView):
    """Carte d'Elyndor en Components V2 — aucune liste déroulante."""
    def __init__(self, private_session: bool = False):
        super().__init__(timeout=None if not private_session else 1800)
        self.private_session = bool(private_session)

        panel = v2_container(
            v2_header("🌍 ELYNDOR", "Choisis ta destination et écris ta propre légende."),
            v2_media_gallery("elyndor_map.png", "Carte du monde d'Elyndor"),
            v2_separator(True),
            colour=0xB67A2A,
        )

        specs = [
            ("city", "👑 ALTHERYA", "Capitale du royaume • commerce • taverne • arène", "Entrer", "👑", discord.ButtonStyle.primary),
            ("elarwyn", "🌲 FORÊT D'ELARWYN", "Terres sauvages • exploration • expéditions", "Explorer", "🌲", discord.ButtonStyle.success),
            ("vorak", "🏔️ MONT VORAK", "Pics hostiles • ressources • dangers", "Explorer", "🏔️", discord.ButtonStyle.secondary),
            ("khaz", "⚒️ KHAZ'GORAM", "Forge légendaire • amélioration d'équipement", "Voyager", "⚒️", discord.ButtonStyle.secondary),
            ("ashkar", "🗼 TOUR D'ASHKAR", "Épreuves • classes • progression", "Entrer", "🗼", discord.ButtonStyle.danger),
        ]
        for key, title, desc, label, emoji, style in specs:
            b = discord.ui.Button(label=label, emoji=emoji, style=style, custom_id=f"altherya:v210:world:{key}")
            async def cb(interaction: discord.Interaction, destination=key):
                if destination == "city":
                    file = discord.File(PLACES / "hub.png", filename="altherya_city.png")
                    view = CityHubV2(private_session=True)
                    if self.private_session:
                        await interaction.response.edit_message(content=None, embeds=[], attachments=[file], view=view)
                    else:
                        await interaction.response.send_message(file=file, view=view, ephemeral=True)
                    return
                if destination == "khaz":
                    level = CASTLE_STORE.current_level(interaction.user.id)
                    if level < 3:
                        await interaction.response.send_message(f"🔒 **KHAZ'GORAM** se débloque au niveau **3**. Ton niveau : **{level}**.", ephemeral=True)
                        return
                    file = discord.File(WORLD_FORGE.KHAZ_GORAM, filename="khaz_goram.png")
                    embed = discord.Embed(title="⚒️ La Forge de KHAZ'GORAM", description="Thorgar façonne ici les équipements des légendes.", color=0xB67A2A)
                    embed.set_image(url="attachment://khaz_goram.png")
                    if self.private_session:
                        await interaction.response.edit_message(content=None, embed=embed, attachments=[file], view=WORLD_FORGE.KhazGoramView())
                    else:
                        await interaction.response.send_message(embed=embed, file=file, view=WORLD_FORGE.KhazGoramView(), ephemeral=True)
                    return
                if destination == "ashkar":
                    await TOWER.show_lobby(interaction, edit=self.private_session)
                    return
                await open_exploration_location(interaction, destination, edit=self.private_session)
            b.callback = cb
            panel.add_item(discord.ui.Section(f"### {title}\n{desc}", accessory=b))
            if key != specs[-1][0]:
                panel.add_item(v2_separator())
        self.add_item(panel)


class CityHubV2(discord.ui.LayoutView):
    """Cité d'Altherya — destinations contextualisées et boutons locaux."""
    def __init__(self, private_session: bool = True):
        super().__init__(timeout=1800 if private_session else None)
        self.private_session = bool(private_session)
        panel = v2_container(
            v2_header("🏰 ALTHERYA", "La cité est ton point d'ancrage. Choisis un lieu."),
            v2_media_gallery("altherya_city.png", "Vue de la cité d'Altherya"),
            v2_separator(True),
            colour=0xB67A2A,
        )
        descriptions = {
            "market": "Achète, vends et équipe ton aventurier.",
            "tavern": "Bois, joue, défie tes amis et écoute le Troubadour.",
            "bank": "Protège tes Gold et consulte ton coffre.",
            "forge": "Améliore ton équipement et renforce tes outils.",
            "arena": "Affronte le Champion ou un autre joueur.",
            "expeditions": "Contrats, ressources et départs vers les terres sauvages.",
            "alley": "Marché clandestin, risques et affaires douteuses.",
            "castle": "Quêtes, progression et institutions du royaume.",
        }
        for key, data in DESTINATIONS.items():
            b = discord.ui.Button(label="Entrer", emoji=data["emoji"], style=discord.ButtonStyle.primary if key in {"tavern","arena","castle"} else discord.ButtonStyle.secondary, custom_id=f"altherya:v210:city:{key}")
            async def cb(interaction: discord.Interaction, destination=key):
                # IMPORTANT : un message passé en Components V2 conserve le flag V2.
                # Discord interdit ensuite d'y remettre content/embed + discord.ui.View classique.
                # Les lieux historiques s'ouvrent donc dans leur propre fenêtre privée.
                await travel(interaction, destination, edit=False)
            b.callback = cb
            panel.add_item(discord.ui.Section(f"### {data['emoji']} {data['label'].upper()}\n{descriptions.get(key, 'Explorer ce lieu.')}", accessory=b))
            panel.add_item(v2_separator())

        world = discord.ui.Button(label="Monde d'Elyndor", emoji="🌍", style=discord.ButtonStyle.secondary, custom_id="altherya:v210:city:world")
        board = discord.ui.Button(label="Panneau central", emoji="📋", style=discord.ButtonStyle.primary, custom_id="altherya:v210:city:board")
        async def world_cb(interaction: discord.Interaction):
            file = discord.File(WORLD_FORGE.WORLD_MAP, filename="elyndor_map.png")
            await interaction.response.edit_message(content=None, embeds=[], attachments=[file], view=WorldHubV2(private_session=True))
        async def board_cb(interaction: discord.Interaction):
            p = CASTLE_STORE.profile(interaction.user.id)
            lvl, cur, need = level_from_xp(p['xp'])
            txt = (
                '📋 **PANNEAU CENTRAL DE LEGACY**\n\n'
                'Toutes tes informations personnelles sont regroupées ici.\n'
                f'⭐ Niveau actuel : **{lvl}** • XP **{cur}/{need}**\n\n'
                '📋 **Quêtes quotidiennes** — Consulte tes 6 objectifs.\n'
                '📜 **Fiche joueur** — Consulte ta progression, tes réputations, ta fortune et tes statistiques.'
            )
            await interaction.response.send_message(content=txt, view=CentralBoardView(), ephemeral=True)
        world.callback = world_cb; board.callback = board_cb
        panel.add_item(v2_action_row(board, world))
        self.add_item(panel)


# Interfaces actives à partir de V2.10.
WorldHubView = WorldHubV2
HubView = CityHubV2

class TavernView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        bar = discord.ui.Button(label="Aller au bar", emoji="🍺", style=discord.ButtonStyle.primary,
                                custom_id="legacy:tavern:bar")
        games = discord.ui.Button(label="Aller à la table", emoji="🎲", style=discord.ButtonStyle.primary,
                                  custom_id="legacy:tavern:games")
        troubadour = discord.ui.Button(label="Voir le Troubadour", emoji="📖", style=discord.ButtonStyle.primary,
                                       custom_id="legacy:tavern:troubadour")
        leave = discord.ui.Button(label="Quitter la taverne", emoji="🚪", style=discord.ButtonStyle.secondary,
                                  custom_id="legacy:tavern:leave")

        async def bar_cb(interaction: discord.Interaction):
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES / "tavern_barman.png", "barman.png", TavernBarView(),
                                  "🍺 **Le comptoir de Altherya**\n" + tavern_reputation_content(interaction.user.id))

        async def games_cb(interaction: discord.Interaction):
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES / "tavern_games.png", "table_jeux.png", TavernGamesView(),
                                  "🎲 **La table de jeux de Altherya**")

        async def troubadour_cb(interaction: discord.Interaction):
            await safe_defer(interaction)
            await edit_with_asset(
                interaction, PLACES / "tavern_troubadour.png", "troubadour.png", TroubadourView(),
                "🦊 **Le Troubadour de Altherya**\nLe vieux renard relève les yeux de son luth et t'invite à approcher." + npc_alcohol_reaction(interaction.user.id, "troubadour")
            )

        async def leave_cb(interaction: discord.Interaction):
            await return_to_hub(interaction)

        bar.callback = bar_cb
        games.callback = games_cb
        troubadour.callback = troubadour_cb
        leave.callback = leave_cb
        self.add_item(bar)
        self.add_item(games)
        self.add_item(troubadour)
        self.add_item(leave)



class TroubadourView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        story = discord.ui.Button(label="Histoire", emoji="📖", style=discord.ButtonStyle.success,
                                  custom_id="legacy:tavern:troubadour:story")
        back = discord.ui.Button(label="Retour à la taverne", emoji="↩️", style=discord.ButtonStyle.secondary,
                                 custom_id="legacy:tavern:troubadour:back")

        async def story_cb(interaction: discord.Interaction):
            await safe_defer(interaction)
            # Le Troubadour ouvre toujours la Saison 1 sur le Chapitre 1.
            # Cela garantit que le premier chapitre reste toujours accessible ;
            # le joueur navigue ensuite avec précédent/suivant.
            await show_story_page(interaction, 1)

        async def back_cb(interaction: discord.Interaction):
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES / "tavern.png", "taverne.png", TavernView(),
                                  "🍺 **Taverne de Altherya**")

        story.callback = story_cb
        back.callback = back_cb
        self.add_item(story)
        self.add_item(back)


async def show_story_page(interaction: discord.Interaction, chapter: int, notice: str | None = None):
    """Affiche un carrousel Discord simple : une carte = un chapitre.

    Aucun livre/image n'est généré ici. Le contenu est affiché directement dans
    un Embed Discord afin de rester lisible sur ordinateur comme sur mobile.
    """
    chapter = max(1, min(SEASON_1_CHAPTERS, int(chapter)))
    state = STORY_STORE.chapter_state(interaction.user.id, 1, chapter)
    title = SEASON_1_TITLES.get(chapter, f"Chapitre {chapter}")
    unlocked = bool(state["unlocked"])

    # Une page verrouillée peut être consultée sans déplacer le marque-page.
    # Seul un chapitre effectivement débloqué et affiché devient le dernier lu.
    if unlocked:
        STORY_STORE.remember_read_chapter(interaction.user.id, 1, chapter)

    embed = discord.Embed(
        title=f"📖 Saison 1 — Chapitre {chapter}/{SEASON_1_CHAPTERS}",
        description=f"**{title}**",
        color=0xC89B3C if unlocked else 0x4B4B4B,
    )

    if unlocked:
        body = SEASON_1_TEXTS.get(chapter) or "*Le récit de ce chapitre sera ajouté prochainement.*"
        # Un champ d'Embed Discord est limité à 1024 caractères. Les chapitres
        # dépassent parfois cette taille (jusqu'à ~2400 caractères), donc le
        # récit complet est placé dans la description de l'Embed (limite 4096).
        # Cela évite l'erreur Discord 50035 « Must be 1024 or fewer ».
        max_body = 4096 - len(title) - 12
        if len(body) > max_body:
            body = body[: max_body - 1] + "…"
        embed.description = f"**{title}**\n\n{body}"
    else:
        if not state["previous_ok"]:
            embed.add_field(
                name="🔒 Chapitre verrouillé",
                value="Tu dois d'abord débloquer le chapitre précédent.",
                inline=False,
            )
        else:
            if chapter == 1:
                embed.add_field(
                    name="🎁 Premier chapitre gratuit",
                    value="Aucun objet n'est nécessaire. Utilise **🔓 Débloquer le chapitre** pour commencer l'histoire.",
                    inline=False,
                )
            else:
                req_lines = []
                for name in state["requirements"]:
                    have = int(state["inventory"].get(name, 0))
                    mark = "✅" if have >= 1 else "❌"
                    req_lines.append(f"{mark} {name} — **{min(have, 1)}/1**")
                embed.add_field(
                    name="🔒 Objets nécessaires",
                    value="\n".join(req_lines) if req_lines else "Aucun objet configuré.",
                    inline=False,
                )
                if state["can_unlock"]:
                    embed.add_field(
                        name="✨ Prêt à être débloqué",
                        value="Tous les objets sont réunis. Utilise **🔓 Débloquer le chapitre**.",
                        inline=False,
                    )

    if notice:
        embed.add_field(name="Information", value=notice[:1024], inline=False)

    embed.set_footer(text=f"Saison 1 • Chapitre {chapter} sur {SEASON_1_CHAPTERS}")

    # Components V2 : ne jamais tenter de réinjecter un Embed classique dans
    # le message V2 du Troubadour. On convertit la page et ses vrais boutons
    # vers le renderer commun, comme le reste d'Altherya.
    await edit_v2_surface(
        interaction,
        embed=embed,
        view=StoryCarouselView(interaction.user.id, chapter),
        title="📖 CHRONIQUES DU TROUBADOUR",
    )


class StoryCarouselView(discord.ui.View):
    def __init__(self, owner_id: int, chapter: int):
        super().__init__(timeout=300)
        self.owner_id = int(owner_id)
        self.chapter = max(1, min(SEASON_1_CHAPTERS, int(chapter)))
        state = STORY_STORE.chapter_state(self.owner_id, 1, self.chapter)

        prev = discord.ui.Button(label="Chapitre précédent", emoji="⬅️", style=discord.ButtonStyle.secondary, row=0,
                                 disabled=self.chapter <= 1)
        unlock = discord.ui.Button(label="Débloquer le chapitre", emoji="🔓", style=discord.ButtonStyle.success, row=0,
                                   disabled=state["unlocked"] or not state["can_unlock"])
        nxt = discord.ui.Button(label="Chapitre suivant", emoji="➡️", style=discord.ButtonStyle.secondary, row=0,
                                disabled=self.chapter >= SEASON_1_CHAPTERS)
        back = discord.ui.Button(label="Retour au Troubadour", emoji="↩️", style=discord.ButtonStyle.primary, row=1)

        async def guard(i: discord.Interaction) -> bool:
            if i.user.id != self.owner_id:
                await i.response.send_message("Ce menu appartient à un autre joueur.", ephemeral=True)
                return False
            return True

        async def prev_cb(i: discord.Interaction):
            if not await guard(i): return
            await safe_defer(i)
            await show_story_page(i, self.chapter - 1)

        async def next_cb(i: discord.Interaction):
            if not await guard(i): return
            await safe_defer(i)
            await show_story_page(i, self.chapter + 1)

        async def unlock_cb(i: discord.Interaction):
            if not await guard(i): return
            await safe_defer(i)
            ok, msg = STORY_STORE.unlock_chapter(self.owner_id, 1, self.chapter)
            if ok:
                details = (
                    "Premier chapitre débloqué gratuitement."
                    if self.chapter == 1
                    else "Objets requis remis au Troubadour et consommés."
                )
                await announce_player_log(i.guild, i.user, f"Chapitre {self.chapter} de la Saison 1 débloqué",
                                          category="Troubadour", details=details)

                # Succès du Troubadour : 1 / 5 / 10 / 20 / 30 chapitres.
                troubadour_milestones = {1: 1, 5: 2, 10: 3, 20: 4, 30: 5}
                tier = troubadour_milestones.get(self.chapter)
                if tier is not None:
                    await announce_achievement(i, f"troubadour:{tier}")
            await show_story_page(i, self.chapter, ("✅ " if ok else "❌ ") + msg)

        async def back_cb(i: discord.Interaction):
            if not await guard(i): return
            await safe_defer(i)
            await edit_with_asset(
                i, PLACES / "tavern_troubadour.png", "troubadour.png", TroubadourView(),
                "🦊 **Le Troubadour de Altherya**\n« Reviens lorsque tu voudras entendre la suite... »"
            )

        prev.callback = prev_cb
        unlock.callback = unlock_cb
        nxt.callback = next_cb
        back.callback = back_cb
        self.add_item(prev); self.add_item(unlock); self.add_item(nxt); self.add_item(back)


def npc_alcohol_reaction(user_id: int, npc: str) -> str:
    """Dialogue PNJ contextuel selon alcoolémie + réputation pertinente, sans bonus/malus de stats."""
    status = TAVERN_STORE.drink_status(user_id)
    drinks = int(status.get("drinks_today", 0))
    state = TAVERN_STORE.drunk_state(drinks)
    tav = TAVERN_STORE.tavern_reputation(user_id)
    tav_tier = int(tav.get("tier", 0))
    criminal = DARK_STORE.criminal_reputation(user_id) if 'DARK_STORE' in globals() else {"label":"Inconnu","successes":0}
    casino = CASINO_STORE.loyalty(user_id) if 'CASINO_STORE' in globals() else {"label":"Visiteur","wins":0,"vip":False}
    arena = ARENA_STORE.progress(user_id) if 'ARENA_STORE' in globals() else {"rank":"Bronze","champion_wins":0}

    if drinks <= 0:
        return ""

    # 4 intensités lisibles. Le rang de Taverne nuance la façon dont le PNJ juge l'état du joueur.
    severity = 1 if drinks <= 2 else 2 if drinks <= 4 else 3 if drinks <= 6 else 4
    known = tav_tier >= 2
    notorious = tav_tier >= 4

    lines = {
        "tavernier": [
            "« Je vois que le premier verre fait déjà son effet. »",
            "« Doucement. Je connais cette tête-là, et je sais comment ça finit. »" if known else "« Doucement. Essaie déjà de marcher droit. »",
            "« Toi, je te connais : tu vas encore devenir le sujet préféré du Troubadour demain matin. »" if notorious else "« Reste assis. C'est un conseil, pas une suggestion. »",
            "« ...Non. Ne me demande surtout pas ce que tu as fait. Je veux garder ce qu'il me reste de santé mentale. »",
        ],
        "troubadour": [
            "« Une chope déliera peut-être ta langue... ou la mienne. »",
            "« Ah, te voilà plus bavard. Les meilleures histoires commencent souvent par une mauvaise décision. »" if known else "« Tu écoutes encore, au moins ? Alors approche. »",
            "« Toi dans cet état ? Assieds-toi. J'ai peut-être une histoire que je ne raconte pas aux gens sobres. »" if notorious else "« Si tu t'endors, je transforme ça en chanson. »",
            "« Magnifique. Tu ne te souviendras probablement de rien... c'est précisément ce qui rend cette histoire intéressante. »",
        ],
        "marchand": [
            "« Tant que tu sais encore compter tes Gold, on peut faire affaire. »",
            "« Je te connais du comptoir... garde tes mains où je peux les voir et lis bien les prix. »" if known else "« Pas de marchandage dans cet état. Les prix sont écrits juste devant toi. »",
            "« Encore toi ? Le Tavernier devrait te donner une laisse. Je ne rembourse pas les achats que tu oublies demain. »" if notorious else "« Tu touches, tu achètes. Et évite de tomber sur l'étal. »",
            "« Non. Même mes objets ont l'air plus sobres que toi. Je vais compter tes pièces deux fois. »",
        ],
        "forgeron": [
            "« Une chope, ça va. Mais ne mets pas les doigts près de l'enclume. »",
            "« Je t'ai déjà vu sortir de la Taverne comme ça. Reste de ce côté du comptoir. »" if known else "« Tu sens l'alcool jusqu'à la cheminée. Pas un pas de plus vers le feu. »",
            "« Ah, le célèbre pilier de comptoir... si tu tombes dans ma forge, je te transforme en décoration. »" if notorious else "« Recule. Marteau, feu et ivrogne : très mauvaise combinaison. »",
            "« DEHORS de l'atelier. Je peux améliorer ta hache, pas ton jugement. »",
        ],
        "voleur": [
            "« Un verre de courage ? Ça peut servir ici. »",
            f"« {criminal['label']} et déjà éméché... soit tu es audacieux, soit tu es idiot. J'aime les deux. »",
            f"« On connaît ton nom dans la Ruelle, {criminal['label']}. Mais là, même tes poches ont l'air de tituber. »" if criminal.get('successes',0) >= 60 else "« Dans cet état, évite de voler quelqu'un qui court plus vite que toi. »",
            "« Parfait. Tu n'as plus peur de rien parce que tu ne comprends plus rien. C'est presque une compétence criminelle. »",
        ],
        "braqueur": [
            "« Tu as bu ? Tant que tu sais encore compter jusqu'à quatre, ça ira. »",
            f"« {criminal['label']}... et tu veux toucher à un coffre dans cet état ? Amusant. »",
            "« Si tu confonds le code du coffre avec ta commande de boissons, je nie t'avoir rencontré. »",
            "« Tu veux braquer une banque alors que tu négocies déjà avec le mur ? J'admire l'ambition. »",
        ],
        "vigile": [
            "« Je sens la Taverne d'ici. Tiens-toi correctement. »",
            "« Je te reconnais. Ne me donne pas une raison de changer d'avis sur ton entrée. »" if casino.get('vip') else "« Pas de scandale devant la salle de jeux. Compris ? »",
            "« VIP ou pas, si tu t'écroules sur ma porte, je te déplace moi-même. »" if casino.get('vip') else "« Un faux pas et tu repars dans l'autre sens. »",
            "« Même le Casino a des limites. Toi, visiblement, non. »",
        ],
        "champion": [
            "« Un verre avant l'Arène ? J'espère que ton courage n'est pas seulement liquide. »",
            f"« {arena.get('rank','Bronze')} et déjà de travers ? Montre-moi que ton rang n'est pas une erreur. »",
            "« Je connais tes victoires. Mais aujourd'hui, j'ai surtout l'impression que le sol est ton véritable adversaire. »" if int(arena.get('champion_wins',0)) > 0 else "« Je refuse de perdre contre quelqu'un qui voit probablement deux Champions. »",
            "« Excellent. Tu me vois en double : ça te fera deux fois plus de raisons d'avoir peur. »",
        ],
    }
    arr = lines.get(npc)
    if not arr:
        return ""
    return f"\n🥴 **Réaction à ton état — {state} :** {arr[severity-1]}"


def tavern_reputation_content(user_id: int) -> str:
    rep = TAVERN_STORE.tavern_reputation(user_id)
    status = TAVERN_STORE.drink_status(user_id)
    reactions = {
        "Sobre": "« Bienvenue. Qu'est-ce que je te sers ? »",
        "Client discret": "« Je commence à connaître ta tête... »",
        "Habitué du comptoir": "« Comme d'habitude ? Tu connais le comptoir. »",
        "Pilier de taverne": "« Ah... notre pilier est de retour. Essaie de rester debout cette fois. »",
        "Ivrogne notoire": "« Encore toi ? Je prépare déjà le seau. »",
        "Alcoolique du coin": "« Regardez qui voilà... l'alcoolique officiel de Altherya ! »",
    }
    limit = int(status.get("limit", 3))
    text = (
        f"🗣️ **Tavernier :** {reactions.get(rep['label'], reactions['Sobre'])}\n"
        f"🍻 Réputation : **{rep['label']}** • Verres bus : **{rep['drinks']}**\n"
        f"🍺 Aujourd'hui : **{status['drinks_today']}/{limit} verres**"
    )
    if rep.get('next_at'):
        text += f" • Prochain palier : **{rep['next_at']} verres**"
    state = TAVERN_STORE.drunk_state(status['drinks_today'])
    drunk_reactions = {
        "Éméché": "« Doucement... je commence à reconnaître ce regard. »",
        "Ivre": "« Essaie au moins de rester sur ton tabouret. »",
        "Bien bourré": "« Si tu casses encore quelque chose, tu paies. »",
        "Complètement bourré": "« Je sens que cette soirée va encore finir dans les histoires du Troubadour... »",
        "Catastrophique": "« Je ne veux même pas savoir ce que tu prépares. »",
        "Mais qu'est-ce que j'ai foutu hier soir ?": "« ...Non. Cette fois, tu ne me demandes pas ce qui s'est passé. »",
    }
    text += f"\n🥴 État actuel : **{state}**"
    if status["drinks_today"] > 0:
        text += npc_alcohol_reaction(user_id, "tavernier")
    if state in drunk_reactions:
        text += f"\n🍺 **Tavernier :** {drunk_reactions[state]}"
    if rep['label'] == "Alcoolique du coin":
        text += "\n💀 Le Tavernier a abandonné l'idée de compter : ton rang permet jusqu'à **8 verres par jour**. Le cooldown reste de **1 h**."
    if status['daily_limit']:
        text += "\n🥴 **Le tavernier refuse de te resservir : tu es saoul. Reviens demain.**"
    elif status['cooldown_seconds'] > 0:
        text += f"\n⏳ Prochain verre dans **{short_time(status['cooldown_seconds'])}**."
    return text


TAVERN_DRINKS = [
    ("beer", "Bière", "🍺", 0),
    ("cider", "Cidre", "🍎", 1),
    ("mead", "Hydromel", "🍯", 2),
    ("red_wine", "Vin rouge", "🍷", 3),
    ("spiced_rum", "Rhum épicé", "🥃", 4),
    ("whisky", "Whisky des Trois Terres", "🥃", 5),
]

class TavernBarView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        drink = discord.ui.Button(label="Boire un coup", emoji="🍺", style=discord.ButtonStyle.success,
                                  custom_id="legacy:tavern:bar:drink")
        round_btn = discord.ui.Button(label=f"Tournée générale ({TAVERN_ROUND_COST} Gold)", emoji="🍻", style=discord.ButtonStyle.primary,
                                  custom_id="legacy:tavern:bar:round")
        back = discord.ui.Button(label="Retour à la taverne", emoji="↩️", style=discord.ButtonStyle.secondary,
                                 custom_id="legacy:tavern:bar:back")

        async def drink_cb(interaction: discord.Interaction):
            status = TAVERN_STORE.drink_status(interaction.user.id)
            if status["daily_limit"]:
                await interaction.response.send_message(
                    "🥴 **Le tavernier secoue la tête.**\n« Ça suffit pour aujourd'hui. Tu es saoul, je ne te sers plus. »\n\n"
                    f"🍺 Limite : **{status.get('limit',3)}/{status.get('limit',3)} verres aujourd'hui**. Reviens demain.",
                    ephemeral=True,
                )
                return
            if status["cooldown_seconds"] > 0:
                await interaction.response.send_message(
                    f"⏳ **Le tavernier refuse de te resservir tout de suite.**\n"
                    f"Attends encore **{short_time(status['cooldown_seconds'])}** avant ton prochain verre.",
                    ephemeral=True,
                )
                return
            await safe_defer(interaction)
            await edit_with_asset(
                interaction,
                PLACES / "tavern_barman.png",
                "barman.png",
                TavernDrinksView(interaction.user.id),
                "🍺 **Le barman te présente ses boissons.**\n" + tavern_reputation_content(interaction.user.id) + "\n\nChoisis ce que tu veux boire."
            )

        async def round_cb(interaction: discord.Interaction):
            result = TAVERN_STORE.buy_round(interaction.user.id)
            if not result.get("ok"):
                await interaction.response.send_message(result.get("message", "Tournée impossible."), ephemeral=True); return
            rounds = int(result["rounds"])
            for threshold, tier in ((1,1),(5,2),(20,3)):
                if rounds >= threshold:
                    await announce_achievement(interaction, f"tavern_rounds:{tier}")
            await announce_gold_activity(interaction.guild, interaction.user, -int(result["cost"]), "Tournée générale à la Taverne", public=False)
            await announce_public_result(interaction.guild, interaction.user, "🍻 Tournée générale !",
                                         f"offre une tournée à tous les habitués présents à la Taverne ! (**{TAVERN_ROUND_COST} Gold**)", color=discord.Color.gold())
            await interaction.response.send_message(
                f"🍻 **Tournée générale !** Le Tavernier remplit les chopes du comptoir.\n"
                f"Tu as offert **{rounds} tournée(s)** au total. Cette tournée ne compte pas dans la réputation alcool.", ephemeral=True)

        async def back_cb(interaction: discord.Interaction):
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES / "tavern.png", "taverne.png", TavernView(),
                                  "🍺 **Taverne de Altherya**")
        drink.callback = drink_cb
        round_btn.callback = round_cb
        back.callback = back_cb
        self.add_item(drink)
        self.add_item(round_btn)
        self.add_item(back)

class TavernDrinkSelect(discord.ui.Select):
    def __init__(self, user_id: int | None = None):
        tier = TAVERN_STORE.tavern_reputation(user_id)["tier"] if user_id else 5
        options = [
            discord.SelectOption(label=label, value=key, emoji=emoji, description=("Disponible" if tier >= required else f"Débloqué au palier {required}"), default=False)
            for key, label, emoji, required in TAVERN_DRINKS if tier >= required
        ]
        super().__init__(placeholder="Choisir une boisson...", min_values=1, max_values=1, options=options, custom_id="legacy:tavern:bar:drink:select")

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        drink = next(item for item in TAVERN_DRINKS if item[0] == selected)
        _, label, emoji, required = drink
        current_tier = TAVERN_STORE.tavern_reputation(interaction.user.id)["tier"]
        if current_tier < required:
            await interaction.response.send_message("🔒 Cette boisson n'est pas encore disponible pour toi.", ephemeral=True); return
        rep = TAVERN_STORE.drink(interaction.user.id, selected)
        if not rep.get("ok"):
            limit = int(rep.get("limit", TAVERN_STORE.daily_drink_limit(interaction.user.id)))
            if rep.get("reason") == "daily_limit":
                await interaction.response.send_message(
                    f"🥴 **Le tavernier retire ton verre.**\n« Non. Tu es déjà saoul. Ça suffit pour aujourd'hui. »\n\n🍺 Limite : **{limit}/{limit} verres aujourd'hui**. Reviens demain.", ephemeral=True); return
            remaining = int(rep.get("cooldown_seconds", 0))
            await interaction.response.send_message(f"⏳ **Pas si vite.** Attends encore **{short_time(remaining)}** avant de boire.", ephemeral=True); return
        if rep["tier"] > 0:
            await announce_achievement(interaction, f"tavern_reputation:{rep['tier']}")
        limit = int(rep.get("limit", TAVERN_STORE.daily_drink_limit(interaction.user.id)))
        extra = ("\n\n🥴 **Le tavernier refuse de te servir davantage aujourd'hui.**" if rep["remaining_today"] <= 0
                 else f"\n🍺 Verres aujourd'hui : **{rep['drinks_today']}/{limit}** • Prochain verre dans **1 h**.")
        event = rep.get("event")
        event_text = ""
        if event:
            event_text = f"\n\n### {event['title']}\n{event['text']}"
            if event.get("gold_actual"):
                delta = int(event["gold_actual"])
                event_text += f"\n{'🪙 +' if delta > 0 else '💸 '}{delta if delta < 0 else delta} Gold"
                await announce_gold_activity(interaction.guild, interaction.user, delta, f"Événement d'ivresse : {event['title']}", public=False)
            if event.get("item"):
                event_text += f"\n🎒 **Objet mystérieux obtenu : {event['item']}**"
            if event.get("achievement"):
                await announce_achievement(interaction, str(event["achievement"]))
            if event.get("legendary"):
                await announce_public_result(interaction.guild, interaction.user, "🍺 Une soirée dont Altherya se souviendra...",
                                             f"vient de provoquer un événement d'ivresse **extrêmement rare** à la Taverne. Les détails restent entre lui et le Tavernier.", color=discord.Color.dark_gold())
        drink_line = f"{emoji} Tu bois un verre de **{label}**.\n🍻 Réputation : **{rep['label']}** • **{rep['drinks']} verre(s)**\n🥴 État : **{rep.get('drunk_state','Sobre')}**" + extra
        if event and event.get("id") == "horse_judges":
            await show_horse_wakeup(interaction, drink_line)
            return
        await interaction.response.send_message(drink_line + event_text, ephemeral=True)

class TavernDrinksView(discord.ui.View):
    def __init__(self, user_id: int | None = None):
        super().__init__(timeout=None)
        self.add_item(TavernDrinkSelect(user_id))

        back = discord.ui.Button(
            label="Retour au comptoir",
            emoji="↩️",
            style=discord.ButtonStyle.secondary,
            custom_id="legacy:tavern:bar:drink:back"
        )

        async def back_cb(interaction: discord.Interaction):
            await safe_defer(interaction)
            await edit_with_asset(
                interaction,
                PLACES / "tavern_barman.png",
                "barman.png",
                TavernBarView(),
                "🍺 **Le comptoir de Altherya**\n" + tavern_reputation_content(interaction.user.id)
            )

        back.callback = back_cb
        self.add_item(back)

class TavernGamesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        specs = [
            ("dice", "Lancer de dé", "🎲"),
            ("coin", "Pile ou face", "🪙"),
            ("rps", "Pierre feuille ciseaux", "✊"),
        ]
        for game_key, label, emoji in specs:
            button = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.success,
                                       custom_id=f"legacy:tavern:games:{game_key}")
            async def game_cb(interaction: discord.Interaction, game=game_key):
                await interaction.response.send_modal(TavernBetModal(game))
            button.callback = game_cb
            self.add_item(button)
        friend_specs = [
            ("dice", "Dés contre un ami", "🎲"),
            ("coin", "Pile/Face contre un ami", "🪙"),
            ("rps", "PFC contre un ami", "🤝"),
        ]
        for game_key, label, emoji in friend_specs:
            button = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary,
                                       custom_id=f"legacy:tavern:friends:{game_key}")
            async def friend_cb(interaction: discord.Interaction, game=game_key):
                await interaction.response.send_message(
                    f"🤝 **Duel amical — {TAVERN_GAME_LABELS[game]}**\nChoisis l'ami que tu veux défier.",
                    view=TavernFriendSelectView(interaction.user.id, game), ephemeral=True
                )
            button.callback = friend_cb
            self.add_item(button)
        back = discord.ui.Button(label="Retour à la taverne", emoji="↩️", style=discord.ButtonStyle.secondary,
                                 custom_id="legacy:tavern:games:back")
        async def back_cb(interaction: discord.Interaction):
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES / "tavern.png", "taverne.png", TavernView(),
                                  "🍺 **Taverne de Altherya**")
        back.callback = back_cb
        self.add_item(back)


class TavernFriendSelect(discord.ui.UserSelect):
    def __init__(self, owner_id: int, game_type: str):
        super().__init__(placeholder="Choisir un ami à défier...", min_values=1, max_values=1)
        self.owner_id = int(owner_id)
        self.game_type = game_type

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Ce menu appartient à un autre joueur.", ephemeral=True)
            return
        target = self.values[0]
        if target.id == interaction.user.id:
            await interaction.response.send_message("❌ Tu ne peux pas te défier toi-même.", ephemeral=True)
            return
        if getattr(target, "bot", False):
            await interaction.response.send_message("❌ Choisis un vrai joueur, pas un bot.", ephemeral=True)
            return
        await interaction.response.send_modal(TavernFriendBetModal(self.game_type, target.id))


class TavernFriendSelectView(discord.ui.View):
    def __init__(self, owner_id: int, game_type: str):
        super().__init__(timeout=90)
        self.add_item(TavernFriendSelect(owner_id, game_type))


class TavernFriendBetModal(discord.ui.Modal):
    def __init__(self, game_type: str, opponent_id: int):
        super().__init__(title=f"Défi — {TAVERN_GAME_LABELS[game_type]}")
        self.game_type = game_type
        self.opponent_id = int(opponent_id)
        self.bet = discord.ui.TextInput(
            label=f"Mise chacun ({MIN_TAVERN_BET}-{MAX_TAVERN_BET} Gold)",
            placeholder="Exemple : 100",
            min_length=1, max_length=4, required=True,
        )
        self.add_item(self.bet)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            wager = int(str(self.bet.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Entre une mise entière en Gold.", ephemeral=True)
            return
        target = interaction.guild.get_member(self.opponent_id) if interaction.guild else None
        if target is None:
            await interaction.response.send_message("❌ Ce joueur n'est plus disponible sur le serveur.", ephemeral=True)
            return
        result = TAVERN_STORE.pvp_create(interaction.user.id, target.id, self.game_type, wager)
        if not result.get("ok"):
            await interaction.response.send_message(result.get("message", "Défi impossible."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        view = TavernFriendChallengeView(result["session_id"], interaction.user.id, target.id, self.game_type, wager)
        try:
            msg = await interaction.channel.send(
                f"🤝 **DÉFI À LA TAVERNE**\n"
                f"{interaction.user.mention} défie {target.mention} à **{TAVERN_GAME_LABELS[self.game_type]}** !\n"
                f"💰 Mise : **{wager} Gold chacun** • Pot : **{wager*2} Gold**\n"
                f"{target.mention}, acceptes-tu le défi ?",
                view=view,
            )
            view.message = msg
            await interaction.followup.send("✅ Défi envoyé. Ta mise est réservée jusqu'à la réponse de ton ami.", ephemeral=True)
            await announce_player_log(interaction.guild, interaction.user, "Défi amical créé", category="Taverne",
                                      details=f"Jeu : {TAVERN_GAME_LABELS[self.game_type]}\nAdversaire : {target.mention}\nMise : {wager} Gold")
        except Exception:
            TAVERN_STORE.pvp_refund(result["session_id"])
            await interaction.followup.send("❌ Impossible de publier le défi. Ta mise a été remboursée.", ephemeral=True)


class TavernFriendChallengeView(discord.ui.View):
    def __init__(self, session_id: str, challenger_id: int, opponent_id: int, game_type: str, wager: int):
        super().__init__(timeout=120)
        self.session_id = session_id
        self.challenger_id = int(challenger_id)
        self.opponent_id = int(opponent_id)
        self.game_type = game_type
        self.wager = int(wager)
        self.message = None
        self.completed = False

    @discord.ui.button(label="Accepter le défi", emoji="✅", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message("Ce défi n'est pas pour toi.", ephemeral=True)
            return
        result = TAVERN_STORE.pvp_accept(self.session_id, interaction.user.id)
        if not result.get("ok"):
            await interaction.response.send_message(result.get("message", "Impossible d'accepter ce défi."), ephemeral=True)
            return
        self.completed = True
        await interaction.response.defer()
        challenger = interaction.guild.get_member(self.challenger_id)
        opponent = interaction.guild.get_member(self.opponent_id)
        if self.game_type == "dice":
            await play_tavern_dice_pvp(interaction.guild, interaction.message, self.session_id, self.wager, challenger, opponent)
        elif self.game_type == "coin":
            await interaction.message.edit(
                content=(f"🪙 **PILE OU FACE — DUEL AMICAL**\n{challenger.mention}, choisis **Pile** ou **Face**. "
                         f"{opponent.mention} recevra automatiquement l'autre côté.\n💰 Pot : **{self.wager*2} Gold**"),
                attachments=[], embeds=[],
                view=CoinPVPChoiceView(self.session_id, self.challenger_id, self.opponent_id, self.wager)
            )
        else:
            await interaction.message.edit(
                content=(f"✊ **PIERRE • FEUILLE • CISEAUX — DUEL AMICAL**\n"
                         f"{challenger.mention} et {opponent.mention}, choisissez chacun votre coup. "
                         f"Les choix restent secrets jusqu'à la révélation.\n💰 Pot : **{self.wager*2} Gold**"),
                attachments=[], embeds=[],
                view=RPSPVPChoiceView(self.session_id, self.challenger_id, self.opponent_id, self.wager)
            )

    @discord.ui.button(label="Refuser / Annuler", emoji="✖️", style=discord.ButtonStyle.danger)
    async def refuse(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in (self.challenger_id, self.opponent_id):
            await interaction.response.send_message("Tu ne participes pas à ce défi.", ephemeral=True)
            return
        self.completed = True
        TAVERN_STORE.pvp_refund(self.session_id)
        await interaction.response.edit_message(content="❌ **Défi annulé.** La mise réservée a été remboursée.", attachments=[], embeds=[], view=None)

    async def on_timeout(self):
        if self.completed:
            return
        self.completed = True
        TAVERN_STORE.pvp_refund(self.session_id)
        if self.message:
            try:
                await self.message.edit(content="⌛ **Défi expiré.** La mise réservée a été remboursée.", attachments=[], embeds=[], view=None)
            except Exception:
                pass


def _member_label(member, fallback: str) -> str:
    if member is None:
        return fallback
    return getattr(member, "display_name", fallback)


async def _edit_public_game(message: discord.Message, path: Path, filename: str, content: str, view=None):
    file = discord.File(path, filename=filename)
    await message.edit(content=content, attachments=[], files=[file], embeds=[], view=view)


async def settle_tavern_pvp(guild: discord.Guild, session_id: str, winner_id: int | None, game_label: str):
    result = TAVERN_STORE.pvp_settle(session_id, winner_id)
    if not result.get("ok"):
        return result
    c0, o0 = int(result["challenger_id"]), int(result["opponent_id"])
    CASTLE_STORE.record(c0, "tavern_game", 1)
    CASTLE_STORE.record(o0, "tavern_game", 1)
    if winner_id is not None:
        c, o, wager = result["challenger_id"], result["opponent_id"], result["wager"]
        loser_id = o if int(winner_id) == c else c
        winner = guild.get_member(int(winner_id)) or discord.Object(id=int(winner_id))
        loser = guild.get_member(int(loser_id)) or discord.Object(id=int(loser_id))
        await announce_gold_activity(guild, winner, wager, f"Taverne — Duel amical — {game_label}", counterpart=loser)
        await announce_gold_activity(guild, loser, -wager, f"Taverne — Duel amical — {game_label}", counterpart=winner)
    return result


async def play_tavern_dice_pvp(guild: discord.Guild, message: discord.Message, session_id: str, wager: int, challenger, opponent):
    path = tavern_render_path(session_id, "dice_pvp")
    left = _member_label(challenger, "Joueur 1")
    right = _member_label(opponent, "Joueur 2")
    for step in range(5):
        a = (roll_die(), roll_die()); b = (roll_die(), roll_die())
        spin = 20 + step * 31
        render_dice(path, wager, a, b, "Les 4 dés roulent...",
                    angles=((spin, -spin*.8), (-spin*.65, spin*.9)), left_label=left, right_label=right)
        await _edit_public_game(message, path, "des_duel.png",
                                f"🎲 **DUEL DE DÉS — {wager} Gold chacun**\nLes 4 dés roulent...", None)
        await asyncio.sleep(.22 + step*.11)
    a = (roll_die(), roll_die()); b = (roll_die(), roll_die())
    while sum(a) == sum(b):
        render_dice(path, wager, a, b, "Égalité ! Les 4 dés sont relancés.", left_label=left, right_label=right)
        await _edit_public_game(message, path, "des_duel.png", "🎲 **ÉGALITÉ !** Les quatre dés sont relancés...", None)
        await asyncio.sleep(.7)
        a = (roll_die(), roll_die()); b = (roll_die(), roll_die())
    winner = challenger if sum(a) > sum(b) else opponent
    loser = opponent if winner.id == challenger.id else challenger
    result = await settle_tavern_pvp(guild, session_id, winner.id, "Lancer de dés")
    status = f"🏆 {winner.display_name} remporte le pot de {wager*2} Gold !"
    render_dice(path, wager, a, b, status, left_label=left, right_label=right)
    await _edit_public_game(message, path, "des_duel.png",
                            f"🎲 **DUEL DE DÉS TERMINÉ**\n{challenger.mention} : **{a[0]} + {a[1]} = {sum(a)}** • "
                            f"{opponent.mention} : **{b[0]} + {b[1]} = {sum(b)}**\n\n🏆 {winner.mention} gagne **{wager} Gold net**.", None)


class CoinPVPChoiceView(discord.ui.View):
    def __init__(self, session_id: str, challenger_id: int, opponent_id: int, wager: int):
        super().__init__(timeout=90)
        self.session_id, self.challenger_id, self.opponent_id, self.wager = session_id, int(challenger_id), int(opponent_id), int(wager)
        self.done = False
        for label, emoji, key in [("Pile", "🪙", "pile"), ("Face", "👑", "face")]:
            b = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary)
            async def cb(interaction: discord.Interaction, choice=key):
                if interaction.user.id != self.challenger_id:
                    await interaction.response.send_message("Seul le joueur qui a lancé le défi choisit le côté. Tu obtiens automatiquement l'autre.", ephemeral=True)
                    return
                if self.done:
                    await interaction.response.send_message("La pièce a déjà été lancée.", ephemeral=True); return
                self.done = True
                await interaction.response.defer()
                await play_tavern_coin_pvp(interaction.guild, interaction.message, self.session_id, self.wager,
                                           self.challenger_id, self.opponent_id, choice)
            b.callback = cb; self.add_item(b)

    async def on_timeout(self):
        if not self.done:
            self.done = True
            TAVERN_STORE.pvp_refund(self.session_id)


async def play_tavern_coin_pvp(guild: discord.Guild, message: discord.Message, session_id: str, wager: int,
                               challenger_id: int, opponent_id: int, choice: str):
    challenger = guild.get_member(challenger_id); opponent = guild.get_member(opponent_id)
    other = "face" if choice == "pile" else "pile"
    path = tavern_render_path(session_id, "coin_pvp")
    for step in range(4):
        render_coin(path, wager, choice, "pile" if step % 2 == 0 else "face", "La pièce tourne...")
        await _edit_public_game(message, path, "pile_face_duel.png",
                                f"🪙 **PILE OU FACE — DUEL**\n{challenger.mention}: **{choice.title()}** • {opponent.mention}: **{other.title()}**\nLa pièce tourne...", None)
        await asyncio.sleep(.32 + step*.13)
    result_face = flip_coin()
    winner = challenger if result_face == choice else opponent
    await settle_tavern_pvp(guild, session_id, winner.id, "Pile ou face")
    render_coin(path, wager, choice, result_face, f"{result_face.title()} ! {winner.display_name} gagne le pot.")
    await _edit_public_game(message, path, "pile_face_duel.png",
                            f"🪙 **RÉSULTAT : {result_face.upper()}**\n{challenger.mention}: **{choice.title()}** • {opponent.mention}: **{other.title()}**\n\n🏆 {winner.mention} gagne **{wager} Gold net**.", None)


class RPSPVPChoiceView(discord.ui.View):
    def __init__(self, session_id: str, challenger_id: int, opponent_id: int, wager: int):
        super().__init__(timeout=120)
        self.session_id, self.challenger_id, self.opponent_id, self.wager = session_id, int(challenger_id), int(opponent_id), int(wager)
        self.choices = {}
        self.done = False
        self.message = None
        for label, emoji, key in [("Pierre", "✊", "pierre"), ("Feuille", "✋", "feuille"), ("Ciseaux", "✌️", "ciseaux")]:
            b = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary)
            async def cb(interaction: discord.Interaction, choice=key):
                uid = interaction.user.id
                if uid not in (self.challenger_id, self.opponent_id):
                    await interaction.response.send_message("Tu ne participes pas à ce duel.", ephemeral=True); return
                if self.done:
                    await interaction.response.send_message("Ce duel est déjà terminé.", ephemeral=True); return
                if uid in self.choices:
                    await interaction.response.send_message("Ton choix est déjà verrouillé.", ephemeral=True); return
                self.choices[uid] = choice
                await interaction.response.send_message(f"✅ Choix enregistré : **{choice.title()}**. Il reste secret jusqu'à la révélation.", ephemeral=True)
                c_ok = "✅" if self.challenger_id in self.choices else "⏳"
                o_ok = "✅" if self.opponent_id in self.choices else "⏳"
                c = interaction.guild.get_member(self.challenger_id); o = interaction.guild.get_member(self.opponent_id)
                if len(self.choices) < 2:
                    await interaction.message.edit(content=f"✊ **PFC — DUEL AMICAL**\n{c.mention} {c_ok} • {o.mention} {o_ok}\nLes choix restent secrets.", view=self)
                    return
                self.done = True
                await play_tavern_rps_pvp(interaction.guild, interaction.message, self.session_id, self.wager,
                                          c, o, self.choices[self.challenger_id], self.choices[self.opponent_id])
            b.callback = cb; self.add_item(b)

    async def on_timeout(self):
        if not self.done:
            self.done = True
            TAVERN_STORE.pvp_refund(self.session_id)


async def play_tavern_rps_pvp(guild: discord.Guild, message: discord.Message, session_id: str, wager: int,
                              challenger, opponent, c_choice: str, o_choice: str):
    path = tavern_render_path(session_id, "rps_pvp")
    render_rps(path, wager, c_choice, None, "Les deux choix sont verrouillés...", left_label=challenger.display_name, right_label=opponent.display_name)
    await _edit_public_game(message, path, "pfc_duel.png", "✊ **PIERRE... FEUILLE... CISEAUX...**\nRévélation des deux choix...", None)
    await asyncio.sleep(1.0)
    outcome = rps_result(c_choice, o_choice)
    if outcome == 0:
        await settle_tavern_pvp(guild, session_id, None, "Pierre feuille ciseaux")
        status = "🤝 Égalité — les deux mises sont rendues."
        result_line = status
    else:
        winner = challenger if outcome > 0 else opponent
        await settle_tavern_pvp(guild, session_id, winner.id, "Pierre feuille ciseaux")
        status = f"🏆 {winner.display_name} remporte le pot de {wager*2} Gold !"
        result_line = f"🏆 {winner.mention} gagne **{wager} Gold net**."
    render_rps(path, wager, c_choice, o_choice, status, left_label=challenger.display_name, right_label=opponent.display_name)
    await _edit_public_game(message, path, "pfc_duel.png",
                            f"✊ **PFC — RÉSULTAT**\n{challenger.mention}: **{c_choice.title()}** • {opponent.mention}: **{o_choice.title()}**\n\n{result_line}", None)


TAVERN_GAME_LABELS = {
    "dice": "Lancer de dé",
    "coin": "Pile ou face",
    "rps": "Pierre feuille ciseaux",
}


def tavern_render_path(session_id: str, game: str) -> Path:
    return DATA / "renders" / f"tavern_{game}_{session_id}.png"


async def show_tavern_games(interaction: discord.Interaction):
    await safe_defer(interaction)
    await edit_with_asset(interaction, PLACES / "tavern_games.png", "table_jeux.png", TavernGamesView(),
                          f"🎲 **La table de jeux de Altherya**\n💰 Ton Gold : **{TAVERN_STORE.wallet(interaction.user.id)}**")


class TavernBetModal(discord.ui.Modal):
    def __init__(self, game_type: str):
        super().__init__(title=f"Mise — {TAVERN_GAME_LABELS[game_type]}")
        self.game_type = game_type
        self.bet = discord.ui.TextInput(
            label=f"Mise en Gold ({MIN_TAVERN_BET}-{MAX_TAVERN_BET})",
            placeholder="Exemple : 100",
            min_length=1,
            max_length=3,
            required=True,
        )
        self.add_item(self.bet)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            wager = int(str(self.bet.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Entre une mise entière en Gold.", ephemeral=True)
            return
        result = TAVERN_STORE.start(interaction.user.id, self.game_type, wager)
        if not result.get("ok"):
            await interaction.response.send_message(result.get("message", "Mise impossible."), ephemeral=True)
            return
        await safe_defer(interaction)
        if self.game_type == "dice":
            await play_tavern_dice(interaction, result["session_id"], wager)
        elif self.game_type == "coin":
            await show_coin_choice(interaction, result["session_id"], wager)
        else:
            await show_rps_choice(interaction, result["session_id"], wager)


class TavernResultView(discord.ui.View):
    def __init__(self, owner_id: int, game_type: str):
        super().__init__(timeout=180)
        self.owner_id = int(owner_id)
        replay = discord.ui.Button(label="Rejouer", emoji="🔁", style=discord.ButtonStyle.success)
        menu = discord.ui.Button(label="Table de jeux", emoji="🎲", style=discord.ButtonStyle.primary)

        async def replay_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Cette partie appartient à un autre joueur.", ephemeral=True)
                return
            await interaction.response.send_modal(TavernBetModal(game_type))

        async def menu_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Cette partie appartient à un autre joueur.", ephemeral=True)
                return
            await show_tavern_games(interaction)

        replay.callback = replay_cb
        menu.callback = menu_cb
        self.add_item(replay)
        self.add_item(menu)


async def settle_tavern_game(interaction: discord.Interaction, session_id: str, wager: int, payout: int, reason: str):
    settled = TAVERN_STORE.settle(session_id, payout)
    actual = int(settled.get("payout", payout))
    wallet = int(settled.get("wallet", TAVERN_STORE.wallet(interaction.user.id)))
    net = actual - int(wager)
    CASTLE_STORE.record(interaction.user.id, "tavern_game", 1)
    if net:
        await announce_gold_activity(interaction.guild, interaction.user, net, f"Taverne — {reason}")
    if actual > payout:
        bonus = f" • 🎉 Gold x2 : **{actual} Gold crédités**"
    else:
        bonus = ""
    return actual, wallet, net, bonus


async def play_tavern_dice(interaction: discord.Interaction, session_id: str, wager: int):
    path = tavern_render_path(session_id, "dice")

    # Deux dés par joueur. Les images intermédiaires changent de valeurs ET d'angle
    # pour donner un vrai effet de dés qui roulent sur la table.
    for step in range(5):
        p_frame = (roll_die(), roll_die())
        b_frame = (roll_die(), roll_die())
        spin = 20 + step * 31
        angles = ((spin, -spin * .8), (-spin * .65, spin * .9))
        render_dice(path, wager, p_frame, b_frame, "Les 4 dés roulent...", angles=angles)
        await edit_with_asset(
            interaction, path, "des.png", discord.ui.View(),
            f"🎲 **LANCER DE DÉS — mise {wager} Gold**\nDeux dés chacun. Les dés roulent sur la table..."
        )
        await asyncio.sleep(0.22 + step * 0.11)

    # Résultat réel : somme des deux dés de chaque joueur.
    player = (roll_die(), roll_die())
    bot_roll = (roll_die(), roll_die())
    p_total, b_total = sum(player), sum(bot_roll)

    # En cas d'égalité, les deux joueurs relancent leurs deux dés.
    while p_total == b_total:
        for step in range(2):
            p_frame = (roll_die(), roll_die())
            b_frame = (roll_die(), roll_die())
            render_dice(path, wager, p_frame, b_frame, "Égalité ! On relance les 4 dés...",
                        angles=((35 + step*55, -25-step*45),(-40-step*35,30+step*60)))
            await edit_with_asset(interaction, path, "des.png", discord.ui.View(),
                                  "🎲 **ÉGALITÉ !**\nLes deux joueurs relancent leurs deux dés...")
            await asyncio.sleep(0.3 + step*.12)
        player = (roll_die(), roll_die())
        bot_roll = (roll_die(), roll_die())
        p_total, b_total = sum(player), sum(bot_roll)

    payout = wager * 2 if p_total > b_total else 0
    actual, wallet, net, bonus = await settle_tavern_game(interaction, session_id, wager, payout, "Lancer de dés")
    if p_total > b_total:
        status = f"🏆 Tu gagnes ! +{net} Gold{bonus} • Solde : {wallet}"
    else:
        status = f"💀 Le tavernier gagne. -{wager} Gold • Solde : {wallet}"

    render_dice(path, wager, player, bot_roll, status)
    await edit_with_asset(
        interaction, path, "des.png", TavernResultView(interaction.user.id, "dice"),
        f"🎲 **LANCER DE DÉS**\n"
        f"Toi : **{player[0]} + {player[1]} = {p_total}** • "
        f"Tavernier : **{bot_roll[0]} + {bot_roll[1]} = {b_total}**\n\n{status}"
    )


class CoinChoiceView(discord.ui.View):
    def __init__(self, owner_id: int, session_id: str, wager: int):
        super().__init__(timeout=120)
        self.owner_id, self.session_id, self.wager = int(owner_id), session_id, int(wager)
        for label, emoji, key in [("Pile", "🪙", "pile"), ("Face", "👑", "face")]:
            b = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary)
            async def cb(interaction: discord.Interaction, choice=key):
                if interaction.user.id != self.owner_id:
                    await interaction.response.send_message("Ce n'est pas ta mise.", ephemeral=True); return
                await safe_defer(interaction)
                await play_tavern_coin(interaction, self.session_id, self.wager, choice)
            b.callback = cb
            self.add_item(b)
        cancel = discord.ui.Button(label="Annuler la mise", emoji="↩️", style=discord.ButtonStyle.secondary)
        async def cancel_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Ce n'est pas ta mise.", ephemeral=True); return
            TAVERN_STORE.refund(self.session_id)
            await show_tavern_games(interaction)
        cancel.callback = cancel_cb
        self.add_item(cancel)

    async def on_timeout(self):
        TAVERN_STORE.refund(self.session_id)


async def show_coin_choice(interaction: discord.Interaction, session_id: str, wager: int):
    path = tavern_render_path(session_id, "coin")
    render_coin(path, wager, "?", None, "Choisis Pile ou Face.")
    await edit_with_asset(interaction, path, "pile_face.png", CoinChoiceView(interaction.user.id, session_id, wager),
                          f"🪙 **PILE OU FACE — mise {wager} Gold**\nChoisis ton côté.")


async def play_tavern_coin(interaction: discord.Interaction, session_id: str, wager: int, choice: str):
    path = tavern_render_path(session_id, "coin")
    for step in range(4):
        render_coin(path, wager, choice, "pile" if step % 2 == 0 else "face", "La pièce tourne...")
        await edit_with_asset(interaction, path, "pile_face.png", discord.ui.View(), "🪙 **PILE OU FACE**\nLa pièce tourne...")
        await asyncio.sleep(0.35 + step * 0.15)
    result = flip_coin()
    payout = wager * 2 if result == choice else 0
    actual, wallet, net, bonus = await settle_tavern_game(interaction, session_id, wager, payout, "Pile ou face")
    if result == choice:
        status = f"🏆 {result.title()} ! Tu gagnes +{net} Gold{bonus} • Solde : {wallet}"
    else:
        status = f"💀 {result.title()} ! Tu perds {wager} Gold • Solde : {wallet}"
    render_coin(path, wager, choice, result, status)
    await edit_with_asset(interaction, path, "pile_face.png", TavernResultView(interaction.user.id, "coin"),
                          f"🪙 **PILE OU FACE**\nTon choix : **{choice.title()}** • Résultat : **{result.title()}**\n\n{status}")


class RPSChoiceView(discord.ui.View):
    def __init__(self, owner_id: int, session_id: str, wager: int):
        super().__init__(timeout=120)
        self.owner_id, self.session_id, self.wager = int(owner_id), session_id, int(wager)
        choices = [("Pierre", "✊", "pierre"), ("Feuille", "✋", "feuille"), ("Ciseaux", "✌️", "ciseaux")]
        for label, emoji, key in choices:
            b = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary)
            async def cb(interaction: discord.Interaction, choice=key):
                if interaction.user.id != self.owner_id:
                    await interaction.response.send_message("Ce n'est pas ta mise.", ephemeral=True); return
                await safe_defer(interaction)
                await play_tavern_rps(interaction, self.session_id, self.wager, choice)
            b.callback = cb
            self.add_item(b)
        cancel = discord.ui.Button(label="Annuler la mise", emoji="↩️", style=discord.ButtonStyle.secondary)
        async def cancel_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Ce n'est pas ta mise.", ephemeral=True); return
            TAVERN_STORE.refund(self.session_id)
            await show_tavern_games(interaction)
        cancel.callback = cancel_cb
        self.add_item(cancel)

    async def on_timeout(self):
        TAVERN_STORE.refund(self.session_id)


async def show_rps_choice(interaction: discord.Interaction, session_id: str, wager: int):
    path = tavern_render_path(session_id, "rps")
    render_rps(path, wager, "pierre", None, "Choisis ton coup.")
    await edit_with_asset(interaction, path, "pfc.png", RPSChoiceView(interaction.user.id, session_id, wager),
                          f"✊ **PIERRE • FEUILLE • CISEAUX — mise {wager} Gold**\nChoisis ton coup.")


async def play_tavern_rps(interaction: discord.Interaction, session_id: str, wager: int, choice: str):
    path = tavern_render_path(session_id, "rps")
    # Suspense avant de révéler le choix du tavernier.
    render_rps(path, wager, choice, None, "Pierre... feuille... ciseaux...")
    await edit_with_asset(interaction, path, "pfc.png", discord.ui.View(), "✊ **PIERRE • FEUILLE • CISEAUX**\nLe tavernier prépare son coup...")
    await asyncio.sleep(1.1)
    bot_choice = rps_bot()
    outcome = rps_result(choice, bot_choice)
    payout = wager * 2 if outcome > 0 else wager if outcome == 0 else 0
    actual, wallet, net, bonus = await settle_tavern_game(interaction, session_id, wager, payout, "Pierre feuille ciseaux")
    if outcome > 0:
        status = f"🏆 Victoire ! +{net} Gold{bonus} • Solde : {wallet}"
    elif outcome == 0:
        status = f"🤝 Égalité. Mise rendue • Solde : {wallet}"
    else:
        status = f"💀 Défaite. -{wager} Gold • Solde : {wallet}"
    render_rps(path, wager, choice, bot_choice, status)
    await edit_with_asset(interaction, path, "pfc.png", TavernResultView(interaction.user.id, "rps"),
                          f"✊ **PIERRE • FEUILLE • CISEAUX**\nToi : **{choice.title()}** • Tavernier : **{bot_choice.title()}**\n\n{status}")


MARKET_ITEMS = [
    {
        "key":"pickaxe", "name":"Pioche en bois", "emoji":"⛏️", "price":100,
        "type":"Outil de récolte • Niveau 1",
        "desc":"Une pioche simple mais indispensable pour commencer.",
        "use":"Permet de récolter des minerais pendant les expéditions.",
    },
    {
        "key":"axe", "name":"Hache en bois", "emoji":"🪓", "price":100,
        "type":"Outil de récolte • Niveau 1",
        "desc":"Une hache légère adaptée aux premières expéditions.",
        "use":"Permet de récolter du bois pendant les expéditions.",
    },
    {
        "key":"spear", "name":"Lance en bois", "emoji":"🗡️", "price":100,
        "type":"Outil de chasse • Niveau 1",
        "desc":"Une lance rudimentaire conçue pour les premières chasses.",
        "use":"Permet de chasser et de récupérer des peaux en expédition.",
    },
    {
        "key":"bag", "name":"Sac de fortune", "emoji":"🎒", "price":100,
        "type":"Sac d'expédition • Niveau 1",
        "desc":"Un petit sac robuste pour transporter les premiers butins.",
        "use":"Capacité : 8 ressources par expédition.",
    },
]


async def announce_achievement(interaction: discord.Interaction, achievement_key: str):
    """Débloque puis publie un succès dans le salon configuré par /succes."""
    ach = ACHIEVEMENTS.get(achievement_key)
    if ach is None or not ACHIEVEMENT_STORE.unlock(interaction.user.id, achievement_key):
        return
    if interaction.guild is None:
        return
    channel_id = ACHIEVEMENT_STORE.get_channel(interaction.guild.id)
    if not channel_id:
        return
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        progress = ACHIEVEMENT_STORE.branch_progress(interaction.user.id, ach.branch)
        branch_total = sum(1 for a in ACHIEVEMENTS.values() if a.branch == ach.branch)
        is_secret = ach.branch == "tavern_secrets"
        embed = discord.Embed(
            title=("🏆 SUCCÈS SECRET DÉCOUVERT !" if is_secret else "🏆 SUCCÈS DÉBLOQUÉ !"),
            description=(
                f"{interaction.user.mention} vient de débloquer un nouveau succès !\n\n"
                f"### {ach.branch_emoji} {ach.title}\n"
                f"{ach.description}"
            ),
            color=ach.color,
        )
        embed.add_field(name="Branche", value=f"{ach.branch_emoji} **{ach.branch_label}**", inline=True)
        embed.add_field(name="Rareté", value=f"{ach.rarity_emoji} **{ach.rarity}**", inline=True)
        embed.add_field(name="Progression", value=f"**{progress}/{branch_total}**", inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Altherya • Système de succès")
        await channel.send(embed=embed)
        await announce_player_log(interaction.guild, interaction.user, f"Succès débloqué : {ach.title}", category="Succès", details=f"Branche : {ach.branch_label} • Rareté : {ach.rarity}")
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
        pass


def achievements_setup_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🏆 Succès & Résultats des jeux de Altherya",
        description=(
            "Ce salon est désormais le **salon officiel des succès et des résultats de jeux**.\n"
            "Seuls les gains et pertes des jeux de la **Taverne** et de la **salle clandestine** sont publics ici.\n"
            "Les achats, ventes, améliorations et autres actions économiques restent privés.\n\n"
            "Les branches actuellement disponibles sont : **Pioche, Hache, Lance et Sac**."
        ),
        color=discord.Color.gold(),
    )
    lines=[]
    for tier in range(1,6):
        rarity, emoji, _ = RARITIES[tier]
        lines.append(f"{emoji} **Niveau {tier} — {rarity}**")
    embed.add_field(name="Niveaux de difficulté", value="\n".join(lines), inline=False)
    embed.set_footer(text="Altherya • 5 succès par branche")
    return embed


def available_starter_items(user_id:int):
    owned=EXPEDITION_STORE.owned_equipment(user_id)
    return [i for i in MARKET_ITEMS if not owned.get(i["key"],False)]


def market_buy_embed(user_id:int,index:int,notice:str|None=None)->discord.Embed:
    """Carte graphique du carrousel du marchand, sans image d'objet supplémentaire."""
    items=available_starter_items(user_id)
    balance=ECONOMY.get_balance(user_id)

    if not items:
        embed=discord.Embed(
            title="🛍️ Boutique de Altherya",
            description=(
                "✅ **Tout l'équipement de départ est déjà en ta possession.**\n\n"
                "Les objets achetés disparaissent automatiquement de la boutique afin d'empêcher les doublons."
            ),
            color=discord.Color.gold(),
        )
        embed.add_field(name="🪙 Bourse",value=f"**{balance.wallet} Gold**",inline=False)
        if notice:
            embed.add_field(name="Résultat",value=notice,inline=False)
        embed.set_footer(text="Marché de Altherya • Équipement de départ complet")
        return embed

    index%=len(items)
    item=items[index]
    can_buy=balance.wallet>=item["price"]

    embed=discord.Embed(
        title=f"{item['emoji']}  {item['name']}",
        description=f"*{item['type']}*\n\n{item['desc']}",
        color=discord.Color.from_rgb(45, 87, 145),
    )
    embed.add_field(name="📜 Utilité",value=item["use"],inline=False)
    embed.add_field(name="🪙 Prix",value=f"**{item['price']} Gold**",inline=True)
    embed.add_field(name="💰 Ta bourse",value=f"**{balance.wallet} Gold**",inline=True)
    embed.add_field(
        name="État",
        value="🟢 **Achat disponible**" if can_buy else f"🔴 **Il te manque {item['price']-balance.wallet} Gold**",
        inline=False,
    )
    if notice:
        embed.add_field(name="Résultat",value=notice,inline=False)
    embed.set_footer(text=f"Objet {index+1}/{len(items)} • ◀️ / ▶️ pour parcourir la boutique")
    return embed



def _story_item_group(item_name: str) -> int:
    for group, items in STORY_REQUIREMENTS.items():
        if item_name in items:
            return int(group)
    return 0


def _current_story_market_items(user_id: int) -> list[str]:
    return STORY_STORE.current_market_items(user_id)


def story_market_embed(user_id: int, index: int, notice: str | None = None) -> discord.Embed:
    items = _current_story_market_items(user_id)
    balance = ECONOMY.get_balance(user_id)
    group = STORY_STORE.current_market_group(user_id)

    if not items or group is None:
        embed = discord.Embed(
            title="📖 Objets d'Histoire — Saison 1",
            description=(
                "Tu as déjà acheté toutes les collections d'objets nécessaires "
                "aux chapitres de la Saison 1.\n\n"
                "Retourne voir le **Troubadour** pour poursuivre les déblocages."
            ),
            color=discord.Color.dark_gold(),
        )
        embed.add_field(name="💰 Bourse", value=f"**{balance.wallet} Gold**", inline=True)
        if notice:
            embed.add_field(name="Résultat", value=notice, inline=False)
        embed.set_footer(text="Toutes les collections de la Saison 1 ont été achetées")
        return embed

    index %= len(items)
    item = items[index]
    price = STORY_ITEM_PRICES[item]
    chapter = group + 1
    inv = STORY_STORE.inventory(user_id)
    owned = inv.get(item, 0)
    purchased = STORY_STORE.has_purchased_story_item(user_id, item)
    purchased_count = sum(1 for name in items if STORY_STORE.has_purchased_story_item(user_id, name))

    embed = discord.Embed(
        title=f"📖 Chapitre {chapter} — {item}",
        description=(
            f"Collection **[{group:02d}]** — objets nécessaires pour débloquer le "
            f"**Chapitre {chapter} de la Saison 1**.\n\n"
            "Le Marchand ne montre que les objets du chapitre actuellement en cours."
        ),
        color=discord.Color.dark_gold(),
    )
    embed.add_field(name="🪙 Prix", value=f"**{price} Gold**", inline=True)
    embed.add_field(name="🎒 Possédé", value=f"**{owned}**", inline=True)
    embed.add_field(name="💰 Bourse", value=f"**{balance.wallet} Gold**", inline=True)
    embed.add_field(
        name="État",
        value=(
            "✅ **Déjà acheté**" if purchased
            else ("🟢 **Achat disponible**" if balance.wallet >= price
                  else f"🔴 **Il te manque {price-balance.wallet} Gold**")
        ),
        inline=False,
    )
    embed.add_field(
        name="📚 Progression de la collection",
        value=f"**{purchased_count}/{len(items)} objets achetés**",
        inline=False,
    )
    if notice:
        embed.add_field(name="Résultat", value=notice, inline=False)
    embed.set_footer(text=f"Objet {index+1}/{len(items)} • Collection [{group:02d}] • Chapitre {chapter}")
    return embed


class StoryMarketView(discord.ui.View):
    def __init__(self, owner_id: int, index: int = 0):
        super().__init__(timeout=300)
        self.owner_id = int(owner_id)
        items = _current_story_market_items(self.owner_id)
        self.index = int(index) % len(items) if items else 0

        prev = discord.ui.Button(emoji="⬅️", style=discord.ButtonStyle.secondary)
        buy = discord.ui.Button(label="Acheter", emoji="🛒", style=discord.ButtonStyle.success)
        nxt = discord.ui.Button(emoji="➡️", style=discord.ButtonStyle.secondary)
        back = discord.ui.Button(label="Retour au marché", emoji="↩️", style=discord.ButtonStyle.primary, row=1)

        if not items:
            prev.disabled = True
            buy.disabled = True
            nxt.disabled = True
        else:
            current_item = items[self.index]
            if STORY_STORE.has_purchased_story_item(self.owner_id, current_item):
                buy.disabled = True
                buy.label = "Déjà acheté"

        async def guard(i):
            if i.user.id != self.owner_id:
                await i.response.send_message("Ce marché appartient à un autre joueur.", ephemeral=True)
                return False
            return True

        async def prev_cb(i):
            if not await guard(i): return
            items_now = _current_story_market_items(self.owner_id)
            if not items_now:
                await i.response.edit_message(content=None, embed=story_market_embed(self.owner_id, 0), view=StoryMarketView(self.owner_id, 0))
                return
            self.index = (self.index - 1) % len(items_now)
            await i.response.edit_message(
                content=None,
                embed=story_market_embed(self.owner_id, self.index),
                view=StoryMarketView(self.owner_id, self.index),
            )

        async def next_cb(i):
            if not await guard(i): return
            items_now = _current_story_market_items(self.owner_id)
            if not items_now:
                await i.response.edit_message(content=None, embed=story_market_embed(self.owner_id, 0), view=StoryMarketView(self.owner_id, 0))
                return
            self.index = (self.index + 1) % len(items_now)
            await i.response.edit_message(
                content=None,
                embed=story_market_embed(self.owner_id, self.index),
                view=StoryMarketView(self.owner_id, self.index),
            )

        async def buy_cb(i):
            if not await guard(i): return
            items_before = _current_story_market_items(self.owner_id)
            if not items_before:
                await i.response.edit_message(content=None, embed=story_market_embed(self.owner_id, 0), view=StoryMarketView(self.owner_id, 0))
                return
            self.index %= len(items_before)
            item = items_before[self.index]
            group_before = STORY_STORE.current_market_group(self.owner_id)
            await safe_defer(i)
            before = ECONOMY.get_balance(self.owner_id).wallet
            ok, msg, price = STORY_STORE.buy_story_item(self.owner_id, item)
            after = ECONOMY.get_balance(self.owner_id).wallet
            if ok:
                await announce_gold_activity(i.guild, i.user, after-before, f"Achat au Marché — Histoire : {item}")

            group_after = STORY_STORE.current_market_group(self.owner_id)
            items_after = _current_story_market_items(self.owner_id)
            next_index = 0 if group_after != group_before else min(self.index, max(0, len(items_after)-1))
            notice = ("✅ " if ok else "❌ ") + msg
            if ok and group_after is not None and group_after != group_before:
                notice += f"\n📖 Collection [{group_before:02d}] complète : les objets du Chapitre {group_after + 1} sont maintenant disponibles."
            elif ok and group_after is None:
                notice += "\n🏆 Toutes les collections d'objets de la Saison 1 ont été achetées."

            await i.edit_original_response(
                content=None,
                embed=story_market_embed(self.owner_id, next_index, notice),
                view=StoryMarketView(self.owner_id, next_index),
            )

        async def back_cb(i):
            if not await guard(i): return
            await safe_defer(i)
            await edit_with_asset(i, PLACES/"market.png", "marche.png", MarketView(), "🛒 **Marché de Altherya**\nQue veux-tu faire ?" + npc_alcohol_reaction(i.user.id, "marchand"))

        prev.callback = prev_cb
        buy.callback = buy_cb
        nxt.callback = next_cb
        back.callback = back_cb
        self.add_item(prev)
        self.add_item(buy)
        self.add_item(nxt)
        self.add_item(back)


async def show_story_market_item(interaction: discord.Interaction, index: int):
    await edit_v2_surface(interaction, path=PLACES/"market.png", filename="marche.png", embed=story_market_embed(interaction.user.id,index), view=StoryMarketView(interaction.user.id,index), title="📖 HISTOIRE DU MARCHÉ")


class MarketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        buy=discord.ui.Button(label="Acheter",emoji="🛍️",style=discord.ButtonStyle.success,custom_id="legacy:market:buy")
        sell=discord.ui.Button(label="Vendre",emoji="💰",style=discord.ButtonStyle.primary,custom_id="legacy:market:sell")
        history=discord.ui.Button(label="Histoire",emoji="📖",style=discord.ButtonStyle.primary,custom_id="legacy:market:history")
        back=discord.ui.Button(label="Revenir en ville",emoji="🏙️",style=discord.ButtonStyle.secondary,custom_id="legacy:market:back")
        async def buy_cb(interaction):
            await safe_defer(interaction); await show_market_item(interaction,0)
        async def sell_cb(interaction):
            await safe_defer(interaction); await show_market_sell(interaction)
        async def history_cb(interaction):
            await safe_defer(interaction); await show_story_market_item(interaction,0)
        async def back_cb(interaction): await return_to_hub(interaction)
        buy.callback=buy_cb; sell.callback=sell_cb; history.callback=history_cb; back.callback=back_cb
        self.add_item(buy); self.add_item(sell); self.add_item(history); self.add_item(back)


class MarketBuyView(discord.ui.View):
    def __init__(self,owner_id:int,index:int=0):
        super().__init__(timeout=300)
        self.owner_id=int(owner_id)
        self.index=int(index)
        items=available_starter_items(self.owner_id)

        if items:
            self.index%=len(items)
            prev=discord.ui.Button(label="",emoji="⬅️",style=discord.ButtonStyle.secondary,row=0)
            buy=discord.ui.Button(label="Acheter",emoji="🛒",style=discord.ButtonStyle.success,row=0)
            nxt=discord.ui.Button(label="",emoji="➡️",style=discord.ButtonStyle.secondary,row=0)

            async def prev_cb(i):
                if i.user.id!=self.owner_id:
                    return await i.response.send_message("Ce marché appartient à un autre joueur.",ephemeral=True)
                items2=available_starter_items(self.owner_id)
                if not items2:
                    await safe_defer(i); return await edit_v2_surface(i,path=PLACES/"market.png",filename="marche.png",embed=market_buy_embed(self.owner_id,0),view=MarketBuyView(self.owner_id,0),title="🛒 MARCHÉ D’ALTHERYA")
                self.index=(self.index-1)%len(items2)
                await safe_defer(i); await edit_v2_surface(i,path=PLACES/"market.png",filename="marche.png",embed=market_buy_embed(self.owner_id,self.index),view=self,title="🛒 MARCHÉ D’ALTHERYA")

            async def next_cb(i):
                if i.user.id!=self.owner_id:
                    return await i.response.send_message("Ce marché appartient à un autre joueur.",ephemeral=True)
                items2=available_starter_items(self.owner_id)
                if not items2:
                    await safe_defer(i); return await edit_v2_surface(i,path=PLACES/"market.png",filename="marche.png",embed=market_buy_embed(self.owner_id,0),view=MarketBuyView(self.owner_id,0),title="🛒 MARCHÉ D’ALTHERYA")
                self.index=(self.index+1)%len(items2)
                await safe_defer(i); await edit_v2_surface(i,path=PLACES/"market.png",filename="marche.png",embed=market_buy_embed(self.owner_id,self.index),view=self,title="🛒 MARCHÉ D’ALTHERYA")

            async def buy_cb(i):
                if i.user.id!=self.owner_id:
                    return await i.response.send_message("Ce marché appartient à un autre joueur.",ephemeral=True)
                items2=available_starter_items(self.owner_id)
                if not items2:
                    await safe_defer(i); return await edit_v2_surface(i,path=PLACES/"market.png",filename="marche.png",embed=market_buy_embed(self.owner_id,0),view=MarketBuyView(self.owner_id,0),title="🛒 MARCHÉ D’ALTHERYA")

                item=items2[self.index%len(items2)]
                await safe_defer(i)
                before_gold=ECONOMY.get_balance(self.owner_id).wallet
                ok,msg=EXPEDITION_STORE.buy_starter(self.owner_id,item["key"])
                if ok:
                    after_gold=ECONOMY.get_balance(self.owner_id).wallet
                    await announce_achievement(i, f"gear:{item['key']}:1")
                    await announce_gold_activity(i.guild, i.user, after_gold-before_gold, f"Achat au Marché : {item['name']}")

                # Après achat, l'objet disparaît du carrousel. On reste au même index
                # lorsque possible pour faire apparaître naturellement l'objet suivant.
                remaining=available_starter_items(self.owner_id)
                new_index=0 if not remaining else min(self.index,len(remaining)-1)
                notice=("✅ **"+msg+"**") if ok else ("❌ **"+msg+"**")
                await edit_v2_surface(i,path=PLACES/"market.png",filename="marche.png",embed=market_buy_embed(self.owner_id,new_index,notice),view=MarketBuyView(self.owner_id,new_index),title="🛒 MARCHÉ D’ALTHERYA")

            prev.callback=prev_cb; buy.callback=buy_cb; nxt.callback=next_cb
            self.add_item(prev); self.add_item(buy); self.add_item(nxt)

        back=discord.ui.Button(label="Retour au marché",emoji="↩️",style=discord.ButtonStyle.primary,row=1)
        async def back_cb(i):
            await safe_defer(i)
            await edit_with_asset(i,PLACES/"market.png","marche.png",MarketView(),"🛒 **Marché de Altherya**\nQue veux-tu faire ?" + npc_alcohol_reaction(i.user.id, "marchand"))
        back.callback=back_cb
        self.add_item(back)


async def show_market_item(interaction,index:int):
    # On conserve exactement la photo actuelle du marchand.
    # Seule la zone de sélection passe en carrousel graphique Discord (Embed + boutons).
    await edit_v2_surface(interaction, path=PLACES/"market.png", filename="marche.png", embed=market_buy_embed(interaction.user.id,index), view=MarketBuyView(interaction.user.id,index), title="🛒 MARCHÉ D’ALTHERYA")


class ResourceSellModal(discord.ui.Modal,title="Vendre une ressource"):
    quantity=discord.ui.TextInput(label="Quantité à vendre",placeholder="Exemple : 3",min_length=1,max_length=6,required=True)
    def __init__(self,owner_id:int,resource_name:str):
        super().__init__(); self.owner_id=int(owner_id); self.resource_name=resource_name
    async def on_submit(self,interaction):
        if interaction.user.id!=self.owner_id: return await interaction.response.send_message("Cette vente ne t'appartient pas.",ephemeral=True)
        try: qty=int(str(self.quantity.value))
        except: return await interaction.response.send_message("Quantité invalide.",ephemeral=True)
        ok,msg,total=EXPEDITION_STORE.sell_resource(self.owner_id,self.resource_name,qty)
        if ok and total:
            CASTLE_STORE.record(self.owner_id,"gold_earned",total)
            await announce_gold_activity(interaction.guild, interaction.user, total, f"Vente au Marché : {qty}× {self.resource_name}")
        await interaction.response.send_message(("✅ " if ok else "❌ ")+msg,ephemeral=True)


class MarketSellSelect(discord.ui.Select):
    def __init__(self,owner_id:int):
        self.owner_id=int(owner_id); inv=EXPEDITION_STORE.get_resources(owner_id)
        opts=[]
        for name,qty in sorted(inv.items()):
            price=RESOURCE_SELL_PRICES.get(name,0)
            if price>0: opts.append(discord.SelectOption(label=name,value=name,description=f"Stock {qty} • {price} Gold/unité"))
        if not opts: opts=[discord.SelectOption(label="Aucune ressource vendable",value="__none__")]
        super().__init__(placeholder="Choisir une ressource",options=opts[:25],min_values=1,max_values=1)
    async def callback(self,interaction):
        if interaction.user.id!=self.owner_id: return await interaction.response.send_message("Ce marché appartient à un autre joueur.",ephemeral=True)
        if self.values[0]=="__none__": return await interaction.response.send_message("Tu n'as aucune ressource à vendre.",ephemeral=True)
        await interaction.response.send_modal(ResourceSellModal(self.owner_id,self.values[0]))


class MarketSellView(discord.ui.View):
    def __init__(self,owner_id:int):
        super().__init__(timeout=300); self.owner_id=int(owner_id); self.add_item(MarketSellSelect(owner_id))
        back=discord.ui.Button(label="Retour au marché",emoji="↩️",style=discord.ButtonStyle.secondary,row=1)
        async def cb(i):
            await safe_defer(i); await edit_with_asset(i,PLACES/"market.png","marche.png",MarketView(),"🛒 **Marché de Altherya**\nQue veux-tu faire ?" + npc_alcohol_reaction(i.user.id, "marchand"))
        back.callback=cb; self.add_item(back)


def market_sell_content(user_id:int)->str:
    inv=EXPEDITION_STORE.get_resources(user_id); b=ECONOMY.get_balance(user_id)
    if not inv: return f"💰 **REVENTE AU MARCHÉ**\n\nAucune ressource en stock.\n💰 Gold : **{b.wallet}**"
    lines=[]
    for name,qty in sorted(inv.items()):
        if name in RESOURCE_SELL_PRICES: lines.append(f"• **{name}** : {qty} en stock • {RESOURCE_SELL_PRICES[name]} Gold/u")
    return "💰 **REVENTE AU MARCHÉ**\n\n"+"\n".join(lines[:22])+f"\n\n💰 Gold : **{b.wallet}**\nLes prix sont volontairement modérés pour préserver la progression."


async def show_market_sell(interaction):
    await edit_with_asset(interaction,PLACES/"market.png","marche.png",MarketSellView(interaction.user.id),market_sell_content(interaction.user.id))


class BankView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        withdraw = discord.ui.Button(
            label="Retirer", emoji="💸", style=discord.ButtonStyle.primary,
            custom_id="legacy:bank:withdraw"
        )
        deposit = discord.ui.Button(
            label="Dépôt", emoji="💰", style=discord.ButtonStyle.success,
            custom_id="legacy:bank:deposit"
        )
        balance = discord.ui.Button(
            label="Solde", emoji="📊", style=discord.ButtonStyle.secondary,
            custom_id="legacy:bank:balance"
        )
        back = discord.ui.Button(
            label="Revenir en ville", emoji="🏙️", style=discord.ButtonStyle.secondary,
            custom_id="legacy:bank:back"
        )

        async def withdraw_cb(interaction: discord.Interaction):
            await interaction.response.send_modal(BankAmountModal("withdraw", interaction.user.id))

        async def deposit_cb(interaction: discord.Interaction):
            await interaction.response.send_modal(BankAmountModal("deposit", interaction.user.id))

        async def balance_cb(interaction: discord.Interaction):
            b = ECONOMY.get_balance(interaction.user.id)
            status = "✅ Retrait gratuit disponible aujourd'hui" if b.free_withdrawal_available else "⚠️ Prochains retraits aujourd'hui : 10 % de frais"
            await interaction.response.send_message(
                f"📊 **Solde bancaire**\n"
                f"💰 Sur toi : **{b.wallet:,} Gold**\n"
                f"🏦 À la banque : **{b.bank:,} Gold**\n"
                f"{status}".replace(",", " "),
                ephemeral=True,
            )

        async def back_cb(interaction: discord.Interaction):
            await return_to_hub(interaction)

        withdraw.callback = withdraw_cb
        deposit.callback = deposit_cb
        balance.callback = balance_cb
        back.callback = back_cb
        self.add_item(withdraw)
        self.add_item(deposit)
        self.add_item(balance)
        self.add_item(back)


class BankAmountModal(discord.ui.Modal):
    def __init__(self, mode:str, owner_id:int):
        super().__init__(title="Dépôt bancaire" if mode=="deposit" else "Retrait bancaire")
        self.mode=mode; self.owner_id=int(owner_id)
        self.amount_input=discord.ui.TextInput(label="Montant en Gold",placeholder="Exemple : 500",min_length=1,max_length=12,required=True)
        self.add_item(self.amount_input)
    async def on_submit(self, interaction:discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Cette interface bancaire appartient à un autre joueur.",ephemeral=True); return
        raw=str(self.amount_input.value).replace(" ","").replace(",","")
        if not raw.isdigit() or int(raw)<=0:
            await interaction.response.send_message("❌ Entre un montant entier supérieur à 0.",ephemeral=True); return
        amount=int(raw); await safe_defer(interaction)
        result=ECONOMY.deposit(self.owner_id,amount) if self.mode=="deposit" else ECONOMY.withdraw(self.owner_id,amount)
        if not result.ok:
            await interaction.followup.send(f"❌ {result.message}",ephemeral=True); return
        if self.mode=="deposit":
            await announce_player_log(interaction.guild,interaction.user,f"Dépôt bancaire de {result.requested} Gold",category="Banque",details=f"Portefeuille : {result.wallet} • Banque : {result.bank}")
            summary=f"✅ **Dépôt effectué : {result.requested:,} Gold**\n💰 Sur toi : **{result.wallet:,} Gold**\n🏦 À la banque : **{result.bank:,} Gold**"
        else:
            await announce_player_log(interaction.guild,interaction.user,f"Retrait bancaire de {result.requested} Gold",category="Banque",details=f"Reçu : {result.received} • Frais : {result.fee} • Portefeuille : {result.wallet} • Banque : {result.bank}")
            fee_line="🎁 **Premier retrait du jour : aucun frais.**" if result.was_free else f"🏦 Frais de retrait : **{result.fee:,} Gold**"
            summary=f"✅ **Retrait demandé : {result.requested:,} Gold**\n{fee_line}\n💵 Reçu : **{result.received:,} Gold**\n💰 Sur toi : **{result.wallet:,} Gold**\n🏦 À la banque : **{result.bank:,} Gold**"
        await edit_with_asset(interaction,PLACES/"bank.png","banque.png",BankView(),summary.replace(","," "))


async def show_bank_amount(interaction: discord.Interaction, mode: str, owner_id: int, amount: int = 10):
    # Compatibilité interne : le nouveau design bancaire saisit directement le montant dans un Modal.
    if not interaction.response.is_done():
        await interaction.response.send_modal(BankAmountModal(mode, owner_id))
    else:
        await interaction.followup.send("Utilise le bouton Dépôt ou Retirer pour saisir directement le montant.",ephemeral=True)


# =========================
# ARÈNE — COMBATS TOUR PAR TOUR
# =========================

def _gold(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")


async def fighter_with_equipment(user_id:int, name:str, class_key:str) -> Fighter:
    eq = await WORLD_FORGE.DB.get_equipment(user_id)
    st = WORLD_FORGE.stats_from_equipment(eq)
    level = max(1, CASTLE_STORE.current_level(user_id))
    # Les PV viennent uniquement du niveau. +35 PV par niveau après le niveau 1,
    # puis le profil de classe (Gardien +20%, Traqueur -5%, Ravageur neutre).
    base_level_hp = 1000 + 35 * (level - 1)
    class_hp_mult = CLASSES[class_key]["hp"] / 100.0
    max_hp = round(base_level_hp * class_hp_mult)
    return Fighter(user_id, name, class_key, max_hp=max_hp, equipment_atk_pct=st.atk_bonus_pct, equipment_def_pct=st.def_bonus_pct, equipment_speed_pct=st.speed_bonus_pct)

def arena_home_content(user_id: int | None = None) -> str:
    base = "⚔️ **Arène de Altherya**\nChoisis ton défi."
    if user_id is None:
        return base
    friend_left = ARENA_STORE.friend_remaining(user_id)
    champ_sec = ARENA_STORE.champion_remaining_seconds(user_id)
    prog = ARENA_STORE.progress(user_id)
    champ = "✅ Disponible" if champ_sec <= 0 else f"⏳ {champ_sec//60} min {champ_sec%60:02d} s"
    return (
        base + "\n\n"
        f"🏅 Rang : **{prog['rank']}** • **{prog['rating']} points**\n"
        f"🤝 Défis d'amis restants aujourd'hui : **{friend_left}/3**\n"
        f"👑 Champion **{prog['champion_level']}/10** : **{champ}**\n"
        "💰 Mise autorisée : **0 à 500 Gold par combattant**"
    )


class ArenaView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        champion = discord.ui.Button(label="Affronter le champion", emoji="👑", style=discord.ButtonStyle.danger,
                                     custom_id="legacy:arena:champion")
        friend = discord.ui.Button(label="Affronter un ami", emoji="⚔️", style=discord.ButtonStyle.primary,
                                   custom_id="legacy:arena:friend")
        back = discord.ui.Button(label="Revenir en ville", emoji="🏙️", style=discord.ButtonStyle.secondary,
                                 custom_id="legacy:arena:back")

        async def champion_cb(interaction: discord.Interaction):
            remaining = ARENA_STORE.champion_remaining_seconds(interaction.user.id)
            if remaining > 0:
                await interaction.response.send_message(
                    f"⏳ Tu as déjà affronté le Champion. Réessaie dans **{remaining//60} min {remaining%60:02d} s**.",
                    ephemeral=True,
                )
                return
            await safe_defer(interaction)
            await edit_with_asset(
                interaction,
                PLACES / "arena_champion.png",
                "champion_legacy.png",
                ChampionIntroView(interaction.user.id),
                f"👑 **LE CHAMPION DE LEGACY — NIVEAU {ARENA_STORE.progress(interaction.user.id)['champion_level']}/10**\nTu t'avances dans l'Arène. Le Champion t'attend." + npc_alcohol_reaction(interaction.user.id, "champion")
            )

        async def friend_cb(interaction: discord.Interaction):
            if ARENA_STORE.friend_remaining(interaction.user.id) <= 0:
                await interaction.response.send_message("❌ Tu as déjà utilisé tes **3 défis d'amis** aujourd'hui.", ephemeral=True)
                return
            await safe_defer(interaction)
            await edit_with_asset(
                interaction, PLACES / "arena.png", "arene.png",
                ArenaFriendSelectView(interaction.user.id),
                "⚔️ **Défi amical**\nChoisis le joueur que tu veux affronter."
            )

        async def back_cb(interaction: discord.Interaction):
            await return_to_hub(interaction)

        champion.callback = champion_cb
        friend.callback = friend_cb
        back.callback = back_cb
        self.add_item(champion); self.add_item(friend); self.add_item(back)


class ChampionIntroView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = int(owner_id)
        fight = discord.ui.Button(label="Combattre", emoji="⚔️", style=discord.ButtonStyle.danger)
        back = discord.ui.Button(label="Retour à l'arène", emoji="↩️", style=discord.ButtonStyle.secondary)

        async def fight_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Ce défi appartient à un autre joueur.", ephemeral=True)
                return
            remaining = ARENA_STORE.champion_remaining_seconds(interaction.user.id)
            if remaining > 0:
                await interaction.response.send_message(
                    f"⏳ Tu as déjà affronté le Champion. Réessaie dans **{remaining//60} min {remaining%60:02d} s**.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_modal(ArenaWagerModal("champion", self.owner_id))

        async def back_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Ce défi appartient à un autre joueur.", ephemeral=True)
                return
            await safe_defer(interaction)
            await edit_with_asset(
                interaction, PLACES / "arena.png", "arene.png",
                ArenaView(), arena_home_content(self.owner_id)
            )

        fight.callback = fight_cb
        back.callback = back_cb
        self.add_item(fight)
        self.add_item(back)


class ArenaFriendUserSelect(discord.ui.UserSelect):
    def __init__(self, owner_id: int):
        super().__init__(placeholder="Choisir un adversaire...", min_values=1, max_values=1)
        self.owner_id = int(owner_id)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Seul le joueur qui lance le défi peut choisir l'adversaire.", ephemeral=True)
            return
        target = self.values[0]
        if target.id == self.owner_id:
            await interaction.response.send_message("Tu ne peux pas te défier toi-même.", ephemeral=True)
            return
        if getattr(target, "bot", False):
            await interaction.response.send_message("Pour combattre un bot, utilise **Affronter le champion**.", ephemeral=True)
            return
        if ARENA_STORE.friend_remaining(target.id) <= 0:
            await interaction.response.send_message(f"❌ {target.mention} a déjà utilisé ses 3 combats amicaux du jour.", ephemeral=True)
            return
        await interaction.response.send_modal(ArenaWagerModal("friend", self.owner_id, target.id))


class ArenaFriendSelectView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.add_item(ArenaFriendUserSelect(owner_id))
        back = discord.ui.Button(label="Retour à l'arène", emoji="↩️", style=discord.ButtonStyle.secondary)
        async def back_cb(interaction: discord.Interaction):
            if interaction.user.id != owner_id:
                await interaction.response.send_message("Cette sélection appartient à un autre joueur.", ephemeral=True); return
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES / "arena.png", "arene.png", ArenaView(), arena_home_content(interaction.user.id))
        back.callback = back_cb
        self.add_item(back)


class ArenaWagerModal(discord.ui.Modal, title="Mise de l'Arène"):
    wager = discord.ui.TextInput(
        label="Mise en Gold (0 à 500)", placeholder="Exemple : 250", default="0",
        min_length=1, max_length=3, required=True
    )

    def __init__(self, mode: str, owner_id: int, opponent_id: int | None = None):
        super().__init__()
        self.mode = mode
        self.owner_id = int(owner_id)
        self.opponent_id = int(opponent_id) if opponent_id else None

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Cette mise appartient à un autre joueur.", ephemeral=True); return
        try:
            amount = int(str(self.wager.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Entre un nombre entier entre 0 et 500.", ephemeral=True); return
        if not 0 <= amount <= 500:
            await interaction.response.send_message("❌ La mise doit être comprise entre **0 et 500 Gold**.", ephemeral=True); return
        bal = ECONOMY.get_balance(self.owner_id)
        if bal.wallet < amount:
            await interaction.response.send_message(f"❌ Tu n'as que **{_gold(bal.wallet)} Gold** sur toi.", ephemeral=True); return
        await interaction.response.defer()
        if self.mode == "champion":
            view = ChampionClassView(self.owner_id, amount)
            content = (
                "👑 **Défi du Champion**\n"
                f"Mise : **{_gold(amount)} Gold**\n\n"
                "Choisis maintenant ta classe."
            )
        else:
            view = FriendLobbyView(self.owner_id, self.opponent_id, amount)
            content = friend_lobby_content(view)
        if self.mode == "champion":
            await edit_with_asset(interaction, PLACES / "arena_champion.png", "champion_legacy.png", view, content)
        else:
            await edit_with_asset(interaction, PLACES / "arena.png", "arene.png", view, content)


class ChampionClassSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_ref = parent_view
        options = [discord.SelectOption(label=c["name"], value=k, emoji=c["emoji"], description=f"{c['animal']} — {('Attaque' if k=='ravageur' else 'Défense' if k=='gardien' else 'Vitesse')}") for k,c in CLASSES.items()]
        super().__init__(placeholder="Choisir ta classe...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        v = self.parent_ref
        if interaction.user.id != v.owner_id:
            await interaction.response.send_message("Cette préparation appartient à un autre joueur.", ephemeral=True); return
        v.class_key = self.values[0]
        await interaction.response.edit_message(
            content=f"👑 **Défi du Champion**\nMise : **{_gold(v.wager)} Gold**\nClasse : {class_line(v.class_key)}\n\nQuand tu es prêt, valide le combat.",
            view=v,
        )


class ChampionClassView(discord.ui.View):
    def __init__(self, owner_id: int, wager: int):
        super().__init__(timeout=300)
        self.owner_id = int(owner_id); self.wager = int(wager); self.class_key: str | None = None
        self.add_item(ChampionClassSelect(self))
        ready = discord.ui.Button(label="Prêt", emoji="✅", style=discord.ButtonStyle.success)
        cancel = discord.ui.Button(label="Annuler", emoji="↩️", style=discord.ButtonStyle.secondary)

        async def ready_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Ce défi appartient à un autre joueur.", ephemeral=True); return
            if not self.class_key:
                await interaction.response.send_message("Choisis d'abord ta classe.", ephemeral=True); return
            await interaction.response.defer()
            ok, msg, battle_id = ARENA_STORE.start_champion(self.owner_id, self.wager)
            if not ok:
                await interaction.followup.send(f"❌ {msg}", ephemeral=True); return
            p = await fighter_with_equipment(self.owner_id, interaction.user.display_name, self.class_key)
            champion_level = ARENA_STORE.progress(self.owner_id)["champion_level"]
            profile = CHAMPION_PROFILES.get(champion_level, CHAMPION_PROFILES[1])
            bot_class = profile["class_key"]
            champ = Fighter(None, profile["name"], bot_class, champion_level=champion_level)
            state = BattleState(battle_id, "champion", self.wager, [p, champ], choose_first(p, champ))
            state.log.append(
                f"👑 **Champion {champion_level}/10 — {profile['name']}** entre dans l'arène en {class_line(bot_class)}. "
                f"*{profile['style']}*"
            )
            ACTIVE_BATTLES[battle_id] = state
            await begin_battle(interaction, state)

        async def cancel_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Ce défi appartient à un autre joueur.", ephemeral=True); return
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES / "arena.png", "arene.png", ArenaView(), arena_home_content(self.owner_id))

        ready.callback = ready_cb; cancel.callback = cancel_cb
        self.add_item(ready); self.add_item(cancel)


class FriendClassSelect(discord.ui.Select):
    def __init__(self, parent_view):
        self.parent_ref = parent_view
        options = [discord.SelectOption(label=c["name"], value=k, emoji=c["emoji"], description=c["animal"]) for k,c in CLASSES.items()]
        super().__init__(placeholder="Choisir ta classe...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        v = self.parent_ref
        if interaction.user.id not in (v.p1, v.p2):
            await interaction.response.send_message("Tu ne participes pas à ce défi.", ephemeral=True); return
        v.classes[interaction.user.id] = self.values[0]
        v.ready.discard(interaction.user.id)  # changer de classe retire l'état prêt
        await interaction.response.edit_message(content=friend_lobby_content(v), view=v)


class FriendLobbyView(discord.ui.View):
    def __init__(self, p1: int, p2: int, wager: int):
        super().__init__(timeout=300)
        self.p1=int(p1); self.p2=int(p2); self.wager=int(wager)
        self.classes: dict[int,str] = {}
        self.ready: set[int] = set()
        self.add_item(FriendClassSelect(self))
        ready = discord.ui.Button(label="Prêt", emoji="✅", style=discord.ButtonStyle.success)
        cancel = discord.ui.Button(label="Annuler / Refuser", emoji="❌", style=discord.ButtonStyle.danger)

        async def ready_cb(interaction: discord.Interaction):
            uid=interaction.user.id
            if uid not in (self.p1,self.p2):
                await interaction.response.send_message("Tu ne participes pas à ce défi.", ephemeral=True); return
            if uid not in self.classes:
                await interaction.response.send_message("Choisis d'abord ta classe.", ephemeral=True); return
            self.ready.add(uid)
            if len(self.ready) < 2:
                await interaction.response.edit_message(content=friend_lobby_content(self), view=self); return
            await interaction.response.defer()
            ok,msg,battle_id=ARENA_STORE.start_friend(self.p1,self.p2,self.wager)
            if not ok:
                self.ready.clear()
                await interaction.followup.send(f"❌ {msg}", ephemeral=True); return
            u1 = interaction.guild.get_member(self.p1) if interaction.guild else None
            u2 = interaction.guild.get_member(self.p2) if interaction.guild else None
            f1=await fighter_with_equipment(self.p1, u1.display_name if u1 else f"Joueur {self.p1}", self.classes[self.p1])
            f2=await fighter_with_equipment(self.p2, u2.display_name if u2 else f"Joueur {self.p2}", self.classes[self.p2])
            state=BattleState(battle_id,"friend",self.wager,[f1,f2],choose_first(f1,f2))
            state.log.append("⚔️ Les deux combattants sont prêts. Le duel commence !")
            ACTIVE_BATTLES[battle_id]=state
            await begin_battle(interaction,state)

        async def cancel_cb(interaction: discord.Interaction):
            if interaction.user.id not in (self.p1,self.p2):
                await interaction.response.send_message("Tu ne participes pas à ce défi.", ephemeral=True); return
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES / "arena.png", "arene.png", ArenaView(), arena_home_content(interaction.user.id))

        ready.callback=ready_cb; cancel.callback=cancel_cb
        self.add_item(ready); self.add_item(cancel)


def friend_lobby_content(v: FriendLobbyView) -> str:
    def status(uid):
        ck=v.classes.get(uid)
        cls=class_line(ck) if ck else "❔ Classe non choisie"
        rd="✅ PRÊT" if uid in v.ready else "⏳ Pas prêt"
        return f"<@{uid}> — {cls} — {rd}"
    return (
        "⚔️ **Défi amical — Préparation**\n"
        f"Mise par joueur : **{_gold(v.wager)} Gold** • Cagnotte : **{_gold(v.wager*2)} Gold**\n\n"
        f"{status(v.p1)}\n{status(v.p2)}\n\n"
        "Chaque joueur choisit sa classe puis clique sur **✅ Prêt**.\n"
        "Le combat démarre uniquement quand les deux sont prêts."
    )


def battle_content(state: BattleState) -> str:
    a,b=state.fighters
    def bar(f):
        pct=max(0,min(1,f.hp/f.max_hp)); blocks=round(pct*12)
        return "█"*blocks + "░"*(12-blocks)
    current=state.actor()
    logs="\n".join(state.log[-5:]) if state.log else "Le combat commence."
    cd = current.ultimate_cd
    return (
        f"⚔️ **ARÈNE — TOUR {state.turn_no}**\n"
        f"{a.cfg['emoji']} **{a.name}** [{a.cfg['name']}]\n❤️ {bar(a)} **{a.hp}/{a.max_hp} PV**\n\n"
        f"{b.cfg['emoji']} **{b.name}** [{b.cfg['name']}]\n❤️ {bar(b)} **{b.hp}/{b.max_hp} PV**\n\n"
        f"🎯 À **{current.name}** de jouer • ⏱️ **60 secondes**\n"
        f"🔥 Ultime : {'✅ disponible' if cd == 0 else f'⏳ {cd} tour(s)'}\n"
        f"💰 Cagnotte : **{_gold(state.wager*2)} Gold**\n\n"
        f"**Journal**\n{logs}"
    )


class BattleView(discord.ui.View):
    def __init__(self, state: BattleState):
        super().__init__(timeout=None)
        self.state=state
        actor=state.actor(); skills=actor.cfg["skills"]
        for action, style in [("light",discord.ButtonStyle.success),("heavy",discord.ButtonStyle.danger),("ultimate",discord.ButtonStyle.primary),("defend",discord.ButtonStyle.secondary)]:
            sk=skills[action]
            label=sk["name"]
            emoji=sk["emoji"]
            btn=discord.ui.Button(label=label, emoji=emoji, style=style, custom_id=f"arena:{state.battle_id[:12]}:{state.turn_no}:{action}")
            if action == "ultimate" and actor.ultimate_cd > 0:
                btn.disabled=True
            async def action_cb(interaction: discord.Interaction, act=action):
                await handle_battle_action(interaction, self.state, act)
            btn.callback=action_cb
            self.add_item(btn)


async def begin_battle(interaction: discord.Interaction, state: BattleState):
    await edit_with_asset(interaction, PLACES / "arena.png", "arene.png", BattleView(state), battle_content(state))
    # L'Arène est ouverte depuis une réponse éphémère. Il faut donc conserver
    # l'Interaction et éditer via le webhook d'interaction, jamais via Message.edit().
    if state.mode == "champion" and state.actor().user_id is None:
        await asyncio.sleep(1.0)
        await run_bot_turn(state, interaction)
    else:
        schedule_turn_timeout(state, interaction)


def schedule_turn_timeout(state: BattleState, surface):
    old=BATTLE_TIMEOUTS.pop(state.battle_id,None)
    if old and not old.done(): old.cancel()
    token=state.turn_no
    BATTLE_TIMEOUTS[state.battle_id]=asyncio.create_task(_turn_timeout(state,surface,token))


async def _turn_timeout(state: BattleState, surface, turn_token: int):
    try:
        await asyncio.sleep(60)
        if state.finished or state.turn_no != turn_token or state.battle_id not in ACTIVE_BATTLES:
            return
        loser=state.actor(); winner=state.target()
        state.finished=True; state.winner_index=1-state.current
        state.log.append(f"⏱️ **{loser.name}** n'a pas joué en 60 secondes : défaite par forfait.")
        await finish_battle_surface(surface,state,winner)
    except asyncio.CancelledError:
        pass


async def handle_battle_action(interaction: discord.Interaction, state: BattleState, action: str):
    if state.finished or state.battle_id not in ACTIVE_BATTLES:
        await interaction.response.send_message("Ce combat est déjà terminé.", ephemeral=True); return
    actor=state.actor()
    if actor.user_id != interaction.user.id:
        await interaction.response.send_message(f"⏳ Ce n'est pas ton tour. C'est à **{actor.name}** de jouer.", ephemeral=True); return
    if action == "ultimate" and actor.ultimate_cd > 0:
        await interaction.response.send_message(f"🔥 Ton ultime recharge encore pendant **{actor.ultimate_cd} tour(s)**.", ephemeral=True); return
    await interaction.response.defer()
    task=BATTLE_TIMEOUTS.pop(state.battle_id,None)
    if task and not task.done(): task.cancel()
    lines=resolve_action(state,action)
    state.log.extend(lines)
    if state.finished:
        winner=state.fighters[state.winner_index]
        await finish_battle_interaction(interaction,state,winner); return
    state.switch()
    if state.mode == "champion" and state.actor().user_id is None:
        await interaction.edit_original_response(content=battle_content(state), view=BattleView(state))
        await asyncio.sleep(1.0)
        await run_bot_turn(state, interaction)
    else:
        await interaction.edit_original_response(content=battle_content(state), view=BattleView(state))
        schedule_turn_timeout(state, interaction)


async def _edit_arena_surface(surface, *, content: str, view: discord.ui.View):
    """Édite le panneau d'Arène, y compris quand il est éphémère.

    Les messages éphémères ne sont pas de vrais messages de salon :
    ``discord.Message.edit`` retourne alors 404 / Unknown Message (10008).
    """
    if isinstance(surface, discord.Interaction):
        await surface.edit_original_response(content=content, attachments=[], embeds=[], view=view)
        return
    await surface.edit(content=content, attachments=[], embeds=[], view=view)


async def run_bot_turn(state: BattleState, surface):
    if state.finished or state.actor().user_id is not None: return
    action=bot_choose_action(state.actor(),state.target())
    state.log.extend(resolve_action(state,action))
    if state.finished:
        winner=state.fighters[state.winner_index]
        await finish_battle_surface(surface,state,winner); return
    state.switch()
    await _edit_arena_surface(surface, content=battle_content(state), view=BattleView(state))
    schedule_turn_timeout(state,surface)


async def _arena_post_finish_bookkeeping(guild: discord.Guild | None, state: BattleState, winner: Fighter, payout: int):
    """Bookkeeping non critique après affichage du résultat.

    Une erreur de journal/succès ne doit jamais laisser l'ancien panneau de combat
    affiché alors que la bataille est déjà marquée terminée en base.
    """
    winner_uid = winner.user_id
    try:
        if winner_uid is not None:
            CASTLE_STORE.record(winner_uid, "combat")
            CASTLE_STORE.record(winner_uid, "arena_win")
            if payout:
                CASTLE_STORE.record(winner_uid, "gold_earned", payout)
        for f in state.fighters:
            if f.user_id is not None and f.user_id != winner_uid:
                CASTLE_STORE.record(f.user_id, "combat")
                CASTLE_STORE.record(f.user_id, "arena_loss")
    except Exception as exc:
        print(f"[ARENA] bookkeeping impossible pour {state.battle_id}: {exc}")

    if winner_uid is not None and guild:
        try:
            wm = guild.get_member(winner_uid)
            if wm:
                await announce_player_log(
                    guild,
                    wm,
                    f"Victoire dans l'Arène — {state.mode}",
                    category="Arène",
                    details=f"Mise : {state.wager} Gold • Gain : {payout} Gold",
                )
                if state.mode == "champion":
                    wins = ARENA_STORE.progress(winner_uid)["champion_wins"]
                    milestone = {1:1, 3:2, 5:3, 7:4, 10:5}.get(wins)
                    if milestone and ACHIEVEMENT_STORE.unlock(winner_uid, f"arena_champion:{milestone}"):
                        await announce_achievement_for(guild, wm, f"arena_champion:{milestone}")
                    if wins == 5:
                        GAZETTE_STORE.record_event("champion_5", winner_uid, 5)
                    elif wins == 10:
                        GAZETTE_STORE.record_event("champion_10", winner_uid, 10)
        except Exception as exc:
            print(f"[ARENA] log impossible pour {state.battle_id}: {exc}")


def _arena_result_text(winner: Fighter, payout: int) -> str:
    return (
        f"🏆 **{winner.name} remporte le combat !**\n"
        + (f"💰 Gain : **{_gold(payout)} Gold**\n" if payout else "")
        + "\nLe combat est terminé. Retour au menu principal de l'Arène."
    )


async def finish_battle_interaction(interaction: discord.Interaction, state: BattleState, winner: Fighter):
    task = BATTLE_TIMEOUTS.pop(state.battle_id, None)
    if task and not task.done():
        task.cancel()

    # La base est réglée une seule fois. Ensuite on retire immédiatement le combat actif.
    _, payout = ARENA_STORE.finish(state.battle_id, winner.user_id)
    ACTIVE_BATTLES.pop(state.battle_id, None)

    # IMPORTANT : mettre à jour le panneau AVANT les logs/succès.
    # Ainsi, même si un système secondaire plante, Discord ne garde jamais un ancien
    # tour cliquable qui répond ensuite « combat déjà terminé ».
    await interaction.edit_original_response(
        content=_arena_result_text(winner, payout),
        attachments=[],
        embeds=[],
        view=ArenaView(),
    )

    await _arena_post_finish_bookkeeping(interaction.guild, state, winner, payout)
    for f in state.fighters:
        if f.user_id is not None:
            await show_pending_levelups(interaction, f.user_id)


async def finish_battle_surface(surface, state: BattleState, winner: Fighter):
    task = BATTLE_TIMEOUTS.pop(state.battle_id, None)
    current = asyncio.current_task()
    if task and task is not current and not task.done():
        task.cancel()

    _, payout = ARENA_STORE.finish(state.battle_id, winner.user_id)
    ACTIVE_BATTLES.pop(state.battle_id, None)

    # Même correction pour les tours du Champion / forfaits, avec support natif
    # des réponses éphémères afin d'éviter l'erreur Discord 10008 Unknown Message.
    await _edit_arena_surface(
        surface,
        content=_arena_result_text(winner, payout),
        view=ArenaView(),
    )

    guild = surface.guild if isinstance(surface, discord.Interaction) else surface.guild
    await _arena_post_finish_bookkeeping(guild, state, winner, payout)
    for f in state.fighters:
        if f.user_id is not None:
            await show_pending_levelups(surface, f.user_id)



# =========================
# FORGE — AMÉLIORATION DES OUTILS / SAC
# =========================

FORGE_EQUIPMENT={"pickaxe":("⛏️","Pioche"),"axe":("🪓","Hache"),"spear":("🗡️","Lance"),"bag":("🎒","Sac")}

def _gear_level(gear,key): return gear.bag_level if key=="bag" else gear.tool_level(key)
def _gear_name(key,level): return BAG_LEVELS[level]["name"] if key=="bag" else TOOL_LEVELS[level][key]
def _forge_asset(key,level):
    candidate=BASE/"assets"/"equipment"/f"{key}_{level}.png"
    return candidate if candidate.exists() else PLACES/"forge.png"

def forge_home_content(user_id:int)->str:
    owned=EXPEDITION_STORE.owned_equipment(user_id); g=EXPEDITION_STORE.get_gear(user_id); lvl=CASTLE_STORE.current_level(user_id)
    lines=[]
    for key,(emoji,label) in FORGE_EQUIPMENT.items():
        if owned.get(key): lines.append(f"{emoji} **{_gear_name(key,_gear_level(g,key))}** — Niv.{_gear_level(g,key)}/5")
        else: lines.append(f"{emoji} **{label}** — 🔒 à acheter au Marché")
    return "🔨 **Forge de Altherya**\n\n🔥 Niveau joueur : **"+str(lvl)+"**\n\n"+"\n".join(lines) + npc_alcohol_reaction(user_id, "forgeron")

def forge_carousel_embed(user_id:int,index:int=0,notice:str|None=None)->discord.Embed:
    """Carrousel graphique de la Forge : un équipement affiché à la fois."""
    keys=list(FORGE_EQUIPMENT.keys())
    index%=len(keys)
    key=keys[index]
    emoji,label=FORGE_EQUIPMENT[key]
    owned=EXPEDITION_STORE.owned_equipment(user_id)
    gear=EXPEDITION_STORE.get_gear(user_id)
    lvl=_gear_level(gear,key)
    player_lvl=CASTLE_STORE.current_level(user_id)
    wallet=ECONOMY.get_balance(user_id).wallet

    if not owned.get(key):
        embed=discord.Embed(
            title=f"{emoji}  {label}",
            description=(
                "*Équipement de forge*\n\n"
                f"🔒 **Cet équipement n'est pas encore possédé.**\n"
                "Achète d'abord sa version niveau 1 au Marché pour pouvoir l'améliorer."
            ),
            color=discord.Color.dark_grey(),
        )
        embed.add_field(name="🔥 Niveau joueur",value=f"**{player_lvl}**",inline=True)
        embed.add_field(name="💰 Ta bourse",value=f"**{wallet} Gold**",inline=True)
        embed.add_field(name="État",value="🔒 **À acheter au Marché**",inline=False)
    elif lvl>=5:
        embed=discord.Embed(
            title=f"{emoji}  {_gear_name(key,lvl)}",
            description="*Équipement de forge • Niveau maximum*\n\n👑 Cet équipement a atteint son niveau maximal.",
            color=discord.Color.gold(),
        )
        embed.add_field(name="⭐ Niveau équipement",value="**5 / 5**",inline=True)
        embed.add_field(name="🔥 Niveau joueur",value=f"**{player_lvl}**",inline=True)
        embed.add_field(name="État",value="👑 **Niveau maximum atteint**",inline=False)
    else:
        target=lvl+1
        req=FORGE_LEVEL_REQUIREMENTS[target]
        recipe=BAG_UPGRADE_RECIPES[target] if key=="bag" else UPGRADE_RECIPES[target]
        inv=EXPEDITION_STORE.get_resources(user_id)
        gold=FORGE_GOLD_COSTS["bag" if key=="bag" else "tool"][target]
        ready=player_lvl>=req and wallet>=gold and all(inv.get(n,0)>=q for n,q in recipe.items())
        material_lines=[]
        for name,qty in recipe.items():
            have=inv.get(name,0)
            material_lines.append(f"{'✅' if have>=qty else '❌'} {name} : **{have}/{qty}**")
        next_extra=f" • capacité **{BAG_LEVELS[target]['capacity']}**" if key=="bag" else ""
        embed=discord.Embed(
            title=f"{emoji}  {_gear_name(key,lvl)}",
            description=(
                f"*Équipement • Niveau {lvl}*\n\n"
                f"**Amélioration suivante :** {_gear_name(key,target)}{next_extra}"
            ),
            color=discord.Color.from_rgb(126,82,43),
        )
        embed.add_field(name="⭐ Niveau",value=f"**{lvl} → {target}**",inline=True)
        embed.add_field(name="🪙 Prix",value=f"**{gold} Gold**",inline=True)
        embed.add_field(name="🔥 Niveau requis",value=f"**{player_lvl}/{req}**",inline=True)
        embed.add_field(name="📦 Matériaux",value="\n".join(material_lines) if material_lines else "Aucun",inline=False)
        embed.add_field(name="💰 Ta bourse",value=f"**{wallet} Gold**",inline=True)
        embed.add_field(name="État",value="🟢 **Amélioration disponible**" if ready else "🔒 **Conditions incomplètes**",inline=True)

    if notice:
        embed.add_field(name="Résultat",value=notice,inline=False)
    embed.set_footer(text=f"Équipement {index+1}/{len(keys)} • ◀️ / ▶️ pour parcourir la Forge")
    return embed


class ForgeView(discord.ui.View):
    def __init__(self, owner_id:int|None=None):
        super().__init__(timeout=None); self.owner_id=int(owner_id) if owner_id is not None else None
        for idx,(key,(emoji,label)) in enumerate(FORGE_EQUIPMENT.items()):
            b=discord.ui.Button(label=f"{label} • Améliorer",emoji=emoji,style=discord.ButtonStyle.success,row=0 if idx<2 else 1,custom_id=f"legacy:forge:grid:{key}")
            async def cb(i,k=key):
                uid=self.owner_id or i.user.id
                if i.user.id!=uid: await i.response.send_message("Cette forge appartient à un autre joueur.",ephemeral=True); return
                await safe_defer(i); index=list(FORGE_EQUIPMENT.keys()).index(k)
                await edit_v2_surface(i,path=PLACES/"forge.png",filename="forge.png",embed=forge_carousel_embed(uid,index),view=ForgeUpgradeView(uid,index),title="⚒️ FORGE D’ALTHERYA")
            b.callback=cb; self.add_item(b)
        back=discord.ui.Button(label="Rentrer en ville",emoji="🏙️",style=discord.ButtonStyle.secondary,row=2,custom_id="legacy:forge:back")
        back.callback=return_to_hub; self.add_item(back)


class ForgeUpgradeView(discord.ui.View):
    def __init__(self,owner_id:int,index:int=0):
        super().__init__(timeout=600)
        self.owner_id=int(owner_id)
        self.index=int(index)%len(FORGE_EQUIPMENT)
        keys=list(FORGE_EQUIPMENT.keys())
        key=keys[self.index]
        owned=EXPEDITION_STORE.owned_equipment(self.owner_id)
        gear=EXPEDITION_STORE.get_gear(self.owner_id)
        lvl=_gear_level(gear,key)

        prev=discord.ui.Button(label="",emoji="⬅️",style=discord.ButtonStyle.secondary,row=0)
        improve=discord.ui.Button(label="Améliorer",emoji="🔨",style=discord.ButtonStyle.success,row=0)
        nxt=discord.ui.Button(label="",emoji="➡️",style=discord.ButtonStyle.secondary,row=0)

        # Le bouton reste visible pour garder une interface stable, mais il est désactivé
        # si l'objet n'est pas possédé ou déjà niveau 5.
        improve.disabled=(not owned.get(key,False) or lvl>=5)

        async def prev_cb(i):
            if i.user.id!=self.owner_id:
                return await i.response.send_message("Cette forge appartient à un autre joueur.",ephemeral=True)
            self.index=(self.index-1)%len(keys)
            await safe_defer(i); await edit_v2_surface(i,path=PLACES/"forge.png",filename="forge.png",embed=forge_carousel_embed(self.owner_id,self.index),view=ForgeUpgradeView(self.owner_id,self.index),title="⚒️ FORGE D’ALTHERYA")

        async def next_cb(i):
            if i.user.id!=self.owner_id:
                return await i.response.send_message("Cette forge appartient à un autre joueur.",ephemeral=True)
            self.index=(self.index+1)%len(keys)
            await safe_defer(i); await edit_v2_surface(i,path=PLACES/"forge.png",filename="forge.png",embed=forge_carousel_embed(self.owner_id,self.index),view=ForgeUpgradeView(self.owner_id,self.index),title="⚒️ FORGE D’ALTHERYA")

        async def improve_cb(i):
            if i.user.id!=self.owner_id:
                return await i.response.send_message("Cette forge appartient à un autre joueur.",ephemeral=True)
            keys2=list(FORGE_EQUIPMENT.keys())
            key2=keys2[self.index%len(keys2)]
            before=EXPEDITION_STORE.get_gear(self.owner_id)
            old=_gear_level(before,key2)
            await safe_defer(i)
            before_gold=ECONOMY.get_balance(self.owner_id).wallet
            ok,msg=EXPEDITION_STORE.upgrade(self.owner_id,key2)
            if ok:
                target=old+1
                after_gold=ECONOMY.get_balance(self.owner_id).wallet
                CASTLE_STORE.add_xp(self.owner_id,XP_REWARDS.get(f"forge_{target}",0))
                CASTLE_STORE.record(self.owner_id,"forge_upgrade",1)
                await announce_achievement(i, f"gear:{key2}:{target}")
                await announce_gold_activity(i.guild, i.user, after_gold-before_gold, f"Amélioration à la Forge : {_gear_name(key2,target)}")
            notice=("✅ **"+msg+"**") if ok else ("❌ **"+msg+"**")
            await edit_v2_surface(i,path=PLACES/"forge.png",filename="forge.png",embed=forge_carousel_embed(self.owner_id,self.index,notice),view=ForgeUpgradeView(self.owner_id,self.index),title="⚒️ FORGE D’ALTHERYA")
            if ok:
                await show_pending_levelups(i, self.owner_id)

        prev.callback=prev_cb; improve.callback=improve_cb; nxt.callback=next_cb
        self.add_item(prev); self.add_item(improve); self.add_item(nxt)

        back=discord.ui.Button(label="Retour à la forge",emoji="↩️",style=discord.ButtonStyle.primary,row=1)
        async def back_cb(i):
            if i.user.id!=self.owner_id:
                return await i.response.send_message("Cette forge appartient à un autre joueur.",ephemeral=True)
            await safe_defer(i)
            await edit_with_asset(i,PLACES/"forge.png","forge.png",ForgeView(self.owner_id),forge_home_content(self.owner_id))
        back.callback=back_cb
        self.add_item(back)


async def show_forge_carousel(interaction,index:int):
    # Même principe que le Marché : on conserve la photo de la Forge,
    # et seule la sélection d'équipement devient un carrousel graphique Discord.
    await edit_v2_surface(interaction, path=PLACES/"forge.png", filename="forge.png", embed=forge_carousel_embed(interaction.user.id,index), view=ForgeUpgradeView(interaction.user.id,index), title="⚒️ FORGE D’ALTHERYA")


def forge_upgrade_content(user_id:int,key:str)->str:
    owned=EXPEDITION_STORE.owned_equipment(user_id); gear=EXPEDITION_STORE.get_gear(user_id); lvl=_gear_level(gear,key); emoji,label=FORGE_EQUIPMENT[key]
    if not owned.get(key): return f"🔨 **FORGE**\n\n{emoji} **{label}**\n🔒 Tu dois d'abord acheter l'équipement niveau 1 au Marché."
    if lvl>=5: return f"🔨 **FORGE**\n\n{emoji} **{_gear_name(key,lvl)}**\n👑 Niveau maximum atteint."
    target=lvl+1; req=FORGE_LEVEL_REQUIREMENTS[target]; player_lvl=CASTLE_STORE.current_level(user_id)
    recipe=BAG_UPGRADE_RECIPES[target] if key=="bag" else UPGRADE_RECIPES[target]; inv=EXPEDITION_STORE.get_resources(user_id); wallet=ECONOMY.get_balance(user_id).wallet
    gold=FORGE_GOLD_COSTS["bag" if key=="bag" else "tool"][target]
    lines=[]
    for name,qty in recipe.items():
        have=inv.get(name,0); lines.append(f"{'✅' if have>=qty else '❌'} **{name}** : **{have}/{qty}**")
    lines.append(f"{'✅' if wallet>=gold else '❌'} **Gold** : **{wallet}/{gold}**")
    level_line=f"{'✅' if player_lvl>=req else '❌'} **Niveau joueur** : **{player_lvl}/{req}**"
    ready=player_lvl>=req and wallet>=gold and all(inv.get(n,0)>=q for n,q in recipe.items())
    extra=f" • capacité **{BAG_LEVELS[target]['capacity']}**" if key=="bag" else ""
    return (f"🔨 **AMÉLIORATION À LA FORGE**\n\n{emoji} **{_gear_name(key,lvl)}** → **{_gear_name(key,target)}**{extra}\n\n"
            f"{level_line}\n\n**Matériaux + Gold nécessaires**\n"+"\n".join(lines)+"\n\n"+("🟢 **Amélioration disponible.**" if ready else "🔒 **Conditions incomplètes.**")+"\nLe stock est relu en temps réel : tout objet vendu disparaît immédiatement de cette détection.")

# =========================
# EXPÉDITIONS — PRÉPARATION / LOOTS / PROGRESSION
# =========================


def expedition_home_content(user_id: int, notice: str | None = None) -> str:
    """Panneau des petites annonces installé à la place de l'ancien tableau d'expédition."""
    state = JOB_BOARD_STORE.get_board(user_id)
    lines = [
        "📌 **PANNEAU DES PETITES ANNONCES D'ALTHERYA**",
        "",
        "Choisis **un seul petit boulot** parmi les 5 propositions.",
        "Une fois une annonce acceptée, tout le panneau est retiré et sera renouvelé **1 heure plus tard**.",
    ]

    if notice:
        lines.extend(["", notice])

    pending = JOB_BOARD_STORE.pending_reward(user_id)
    if pending:
        job=pending["job"]; rarity=JOB_RARITIES[job.rarity]
        lines.extend(["", f"🧾 **Mission en cours : {job.title}**", f"{rarity['emoji']} {rarity['label']} • 💰 **{job.reward} Gold**"])
        if pending["ready"]:
            lines.extend(["", "🟢 **Mission terminée — ta récompense t'attend sur le panneau.**"])
        else:
            lines.extend(["", f"🔴 **Récompense verrouillée** • disponible <t:{pending['ready_at']}:R>"])
        return "\n".join(lines)

    if state.cooling_down:
        lines.extend([
            "",
            "⏳ **Le panneau est en cours de renouvellement.**",
            f"📜 Nouvelles annonces <t:{state.next_board_at}:R> • <t:{state.next_board_at}:t>",
            "",
            "Les 4 autres annonces du précédent tirage ont été retirées.",
        ])
        return "\n".join(lines)

    if not state.jobs:
        lines.extend(["", "🔄 Les nouvelles annonces sont en préparation. Appuie sur **Actualiser**."])
        return "\n".join(lines)

    lines.extend(["", "**ANNONCES DISPONIBLES**", ""])
    for index, job in enumerate(state.jobs, start=1):
        rarity = JOB_RARITIES[job.rarity]
        lines.append(
            f"**{index}. {job.title}**\n"
            f"{rarity['emoji']} {rarity['label']} • 💰 **{job.reward} Gold**"
        )
        if index != len(state.jobs):
            lines.append("")

    lines.extend([
        "",
        "🎲 Chaque annonce tire sa rareté **indépendamment** : il peut donc y avoir plusieurs légendaires... ou uniquement du commun.",
    ])
    return "\n".join(lines)


class ExpeditionView(discord.ui.View):
    """V1.65 : l'ancien tableau des expéditions devient le panneau de petites annonces."""
    def __init__(self, owner_id: int | None = None):
        super().__init__(timeout=1800)
        self.owner_id = int(owner_id) if owner_id is not None else None
        self.state = JOB_BOARD_STORE.get_board(self.owner_id) if self.owner_id is not None else None

        if self.state is not None and not self.state.cooling_down:
            for index, job in enumerate(self.state.jobs[:5], start=1):
                button = discord.ui.Button(
                    label=f"Annonce {index}",
                    emoji="📜",
                    style=discord.ButtonStyle.success if job.rarity in {"epic", "legendary"} else discord.ButtonStyle.primary,
                    row=0 if index <= 3 else 1,
                    custom_id=f"altherya:jobs:accept:{index}:{job.job_id}",
                )

                async def accept_cb(interaction: discord.Interaction, selected_job=job, selected_batch=self.state.batch_id):
                    if self.owner_id is not None and interaction.user.id != self.owner_id:
                        await interaction.response.send_message("Ce panneau appartient à un autre joueur.", ephemeral=True)
                        return
                    await safe_defer(interaction)
                    ok, msg, accepted, _ = JOB_BOARD_STORE.accept_job(
                        interaction.user.id,
                        selected_batch,
                        selected_job.job_id,
                    )
                    if not ok or accepted is None:
                        await edit_with_asset(
                            interaction,
                            PLACES / "expeditions.png",
                            "expeditions.png",
                            ExpeditionView(interaction.user.id),
                            expedition_home_content(interaction.user.id, f"❌ **{msg}**"),
                        )
                        return

                    rarity = JOB_RARITIES[accepted.rarity]
                    notice = (
                        f"✅ **Petit boulot accepté : {accepted.title}**\n"
                        f"{rarity['emoji']} {rarity['label']} • ⏳ **1 h de mission** avant de pouvoir récupérer **{accepted.reward} Gold** sur ce panneau."
                    )
                    await edit_with_asset(
                        interaction,
                        PLACES / "expeditions.png",
                        "expeditions.png",
                        ExpeditionView(interaction.user.id),
                        expedition_home_content(interaction.user.id, notice),
                    )

                button.callback = accept_cb
                self.add_item(button)

        pending = JOB_BOARD_STORE.pending_reward(self.owner_id) if self.owner_id is not None else None
        if pending:
            claim = discord.ui.Button(
                label="Récupérer la récompense" if pending["ready"] else f"Récompense • {short_time(pending['remaining'])}",
                emoji="🎁",
                style=discord.ButtonStyle.success if pending["ready"] else discord.ButtonStyle.danger,
                disabled=not pending["ready"],
                row=2, custom_id="altherya:jobs:claim"
            )
            async def claim_cb(interaction: discord.Interaction):
                if self.owner_id is not None and interaction.user.id != self.owner_id:
                    await interaction.response.send_message("Ce panneau appartient à un autre joueur.",ephemeral=True); return
                await safe_defer(interaction)
                ok,msg,job=JOB_BOARD_STORE.claim_reward(interaction.user.id)
                if ok and job:
                    await announce_gold_activity(interaction.guild,interaction.user,job.reward,f"Petite annonce — {job.title}",public=False)
                    notice=f"🎁 **Récompense récupérée : +{job.reward} Gold** pour *{job.title}*."
                else: notice=f"⏳ **{msg}**"
                await edit_with_asset(interaction,PLACES/"expeditions.png","expeditions.png",ExpeditionView(interaction.user.id),expedition_home_content(interaction.user.id,notice))
            claim.callback=claim_cb; self.add_item(claim)

        refresh = discord.ui.Button(
            label="Actualiser",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            row=2,
            custom_id="altherya:jobs:refresh",
        )
        back = discord.ui.Button(
            label="Revenir en ville",
            emoji="🏙️",
            style=discord.ButtonStyle.secondary,
            row=2,
            custom_id="altherya:jobs:back",
        )

        async def refresh_cb(interaction: discord.Interaction):
            if self.owner_id is not None and interaction.user.id != self.owner_id:
                await interaction.response.send_message("Ce panneau appartient à un autre joueur.", ephemeral=True)
                return
            await safe_defer(interaction)
            await edit_with_asset(
                interaction,
                PLACES / "expeditions.png",
                "expeditions.png",
                ExpeditionView(interaction.user.id),
                expedition_home_content(interaction.user.id),
            )

        async def back_cb(interaction: discord.Interaction):
            if self.owner_id is not None and interaction.user.id != self.owner_id:
                await interaction.response.send_message("Ce panneau appartient à un autre joueur.", ephemeral=True)
                return
            await return_to_hub(interaction)

        refresh.callback = refresh_cb
        back.callback = back_cb
        self.add_item(refresh)
        self.add_item(back)


# ============================================================
# V1.66 — EXPLORATION D'ELYNDOR : ELARWYN / VORAK
# ============================================================

def _activity_label(tool_key: str) -> str:
    return {
        "axe": "Couper du bois",
        "pickaxe": "Miner",
        "spear": "Chasser",
    }.get(tool_key, tool_key)


def _activity_emoji(tool_key: str) -> str:
    return TOOL_META.get(tool_key, {}).get("emoji", "🧭")


def _destination_keys(location_key: str) -> tuple[str, ...]:
    return tuple(
        key for key, meta in EXPEDITIONS.items()
        if meta.get("location_key") == location_key
    )


def _zone_asset(location_key: str) -> Path:
    assets = {
        "elarwyn": PLACES / "elarwyn.png",
        "vorak": PLACES / "vorak.png",
    }
    return assets.get(location_key, PLACES / "expeditions.png")


def _expedition_display_name(expedition_key: str) -> str:
    """Nom RP V2 affiché, indépendant des anciennes valeurs génériques en base/code."""
    return destination_name(expedition_key) or EXPEDITIONS.get(expedition_key, {}).get("name", expedition_key)


def _expedition_display_description(expedition_key: str) -> str:
    return destination_description(expedition_key) or EXPEDITIONS.get(expedition_key, {}).get("description", "")


def location_home_content(user_id: int, location_key: str, notice: str | None = None) -> str:
    meta = LOCATION_META[location_key]
    active = EXPEDITION_STORE.active_run(user_id)
    level = EXPEDITION_STORE.get_player_level(user_id)
    lines = [
        f"{meta['emoji']} **{meta['name'].upper()}**",
        meta["description"],
        "",
        f"🎚️ Ton niveau : **{level}**",
    ]
    if notice:
        lines.extend(["", notice])

    if active:
        zone = EXPEDITIONS.get(active.expedition_key, {})
        active_location = zone.get("location_key")
        if active_location == location_key:
            EXPEDITION_STORE.reveal_due_events(active.run_id)
            lines.extend(["", expedition_live_content(active, compact=True)])
        else:
            other = LOCATION_META.get(active_location, {}).get("name", "une autre zone")
            lines.extend([
                "",
                f"🔒 Tu as déjà une expédition en cours dans **{other}**.",
                "Une seule activité peut être menée à la fois.",
            ])
        return "\n".join(lines)

    lines.extend([
        "",
        "### 🗺️ DESTINATIONS",
        "Choisis l'une des **5 destinations**. Les zones plus profondes durent plus longtemps et donnent accès à des loots plus rares.",
        "",
    ])
    for key in _destination_keys(location_key):
        zone = EXPEDITIONS[key]
        lock = "✅" if level >= zone["level"] else "🔒"
        lines.append(
            f"{lock} **{_expedition_display_name(key)}** • Niveau **{zone['level']}** • ⏳ **{zone['duration_label']}** • ☠️ {zone['danger']}"
        )
    return "\n".join(lines)


class ExplorationLocationView(discord.ui.View):
    def __init__(self, owner_id: int, location_key: str):
        super().__init__(timeout=1800)
        self.owner_id = int(owner_id)
        self.location_key = location_key
        level = EXPEDITION_STORE.get_player_level(owner_id)
        active = EXPEDITION_STORE.active_run(owner_id)

        if not active:
            for idx, key in enumerate(_destination_keys(location_key), start=1):
                zone = EXPEDITIONS[key]
                unlocked = level >= zone["level"]
                button = discord.ui.Button(
                    label=_expedition_display_name(key)[:80],
                    emoji="🗺️" if unlocked else "🔒",
                    style=discord.ButtonStyle.primary if unlocked else discord.ButtonStyle.secondary,
                    disabled=not unlocked,
                    row=0 if idx <= 3 else 1,
                    custom_id=f"altherya:explore:{location_key}:dest:{idx}",
                )

                async def destination_cb(interaction: discord.Interaction, expedition_key=key):
                    if interaction.user.id != self.owner_id:
                        await interaction.response.send_message("Cette interface appartient à un autre joueur.", ephemeral=True)
                        return
                    zone_now = EXPEDITIONS[expedition_key]
                    player_level = EXPEDITION_STORE.get_player_level(self.owner_id)
                    if player_level < zone_now["level"]:
                        await interaction.response.send_message(
                            f"🔒 Niveau **{zone_now['level']}** requis. Ton niveau : **{player_level}**.",
                            ephemeral=True,
                        )
                        return
                    await interaction.response.edit_message(
                        content=activity_content(expedition_key),
                        view=ExpeditionActivityView(self.owner_id, expedition_key),
                    )

                button.callback = destination_cb
                self.add_item(button)

        refresh = discord.ui.Button(label="Actualiser", emoji="🔄", style=discord.ButtonStyle.secondary, row=2)
        world = discord.ui.Button(label="Monde", emoji="🌍", style=discord.ButtonStyle.secondary, row=2)

        async def refresh_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Cette interface appartient à un autre joueur.", ephemeral=True)
                return
            active_now = EXPEDITION_STORE.active_run(self.owner_id)
            if active_now and active_now.finished:
                await finalize_expedition_run(active_now.run_id)
            await interaction.response.edit_message(
                content=location_home_content(self.owner_id, self.location_key),
                view=ExplorationLocationView(self.owner_id, self.location_key),
            )

        async def world_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Cette interface appartient à un autre joueur.", ephemeral=True)
                return
            file = discord.File(WORLD_FORGE.WORLD_MAP, filename="elyndor_map.png")
            embed = discord.Embed(
                title="🌍 Le Monde d'Elyndor",
                description="Explore **Altherya**, **KHAZ'GORAM**, **la Tour d’Ashkar**, la **Forêt d’Elarwyn** et le **Mont Vorak**.",
                color=0xB67A2A,
            )
            embed.set_image(url="attachment://elyndor_map.png")
            await interaction.response.edit_message(content=None, embed=embed, attachments=[file], view=WorldHubView(private_session=True))

        refresh.callback = refresh_cb
        world.callback = world_cb
        self.add_item(refresh)
        self.add_item(world)


def activity_content(expedition_key: str) -> str:
    zone = EXPEDITIONS[expedition_key]
    event = current_event(zone.get("location_key", ""))
    location = LOCATION_META[zone["location_key"]]
    activities = " • ".join(f"{_activity_emoji(k)} **{_activity_label(k)}**" for k in zone["tools"])
    return (
        f"{location['emoji']} **{location['name']} — {_expedition_display_name(expedition_key)}**\n"
        f"_{_expedition_display_description(expedition_key)}_\n\n"
        f"{event['emoji']} **MONDE VIVANT — {event['name']}**\n{event['description']}\n\n"
        f"⏳ Durée : **{zone['duration_label']}**\n"
        f"🎚️ Niveau requis : **{zone['level']}**\n"
        f"☠️ Danger : **{zone['danger']}**\n\n"
        "### 🎯 CHOISIS TON ACTIVITÉ\n"
        f"{activities}\n\n"
        "⚠️ **Une expédition = une seule activité.** Une fois lancée, tu ne pourras pas changer d'activité avant la fin."
    )


class ExpeditionActivityView(discord.ui.View):
    def __init__(self, owner_id: int, expedition_key: str):
        super().__init__(timeout=900)
        self.owner_id = int(owner_id)
        self.expedition_key = expedition_key
        zone = EXPEDITIONS[expedition_key]
        owned = EXPEDITION_STORE.owned_equipment(owner_id)

        for tool_key in zone["tools"]:
            have = bool(owned.get(tool_key, False))
            button = discord.ui.Button(
                label=_activity_label(tool_key),
                emoji=_activity_emoji(tool_key),
                style=discord.ButtonStyle.primary if have else discord.ButtonStyle.secondary,
                disabled=not have,
                row=0,
            )

            async def activity_cb(interaction: discord.Interaction, selected_tool=tool_key):
                if interaction.user.id != self.owner_id:
                    await interaction.response.send_message("Cette interface appartient à un autre joueur.", ephemeral=True)
                    return
                prep = ExpeditionPreparationView(self.owner_id, self.expedition_key, selected_tool)
                await interaction.response.edit_message(content=preparation_content(prep), view=prep)

            button.callback = activity_cb
            self.add_item(button)

        back = discord.ui.Button(label="Retour aux destinations", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
        async def back_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Cette interface appartient à un autre joueur.", ephemeral=True)
                return
            location_key = EXPEDITIONS[self.expedition_key]["location_key"]
            await interaction.response.edit_message(
                content=location_home_content(self.owner_id, location_key),
                view=ExplorationLocationView(self.owner_id, location_key),
            )
        back.callback = back_cb
        self.add_item(back)


def preparation_content(view: "ExpeditionPreparationView") -> str:
    zone = EXPEDITIONS[view.expedition_key]
    location = LOCATION_META[zone["location_key"]]
    gear = EXPEDITION_STORE.get_gear(view.owner_id)
    owned = EXPEDITION_STORE.owned_equipment(view.owner_id)
    tool_owned = owned.get(view.tool_key, False)
    bag_owned = owned.get("bag", False)

    if tool_owned:
        tool_name = TOOL_LEVELS[view.tool_level][view.tool_key]
        tool_line = f"{_activity_emoji(view.tool_key)} **{tool_name}** — niveau {view.tool_level}"
    else:
        tool_line = f"🔒 **{STARTER_GEAR[view.tool_key]['name']} non possédé**"

    if bag_owned:
        bag = BAG_LEVELS[view.bag_level]
        bag_line = f"🎒 **{bag['name']}** — {bag['capacity']} places"
    else:
        bag_line = "🔒 **Aucune sacoche possédée**"

    ready = tool_owned and bag_owned
    return (
        f"🎒 **PRÉPARATION DE L'EXPÉDITION**\n\n"
        f"{location['emoji']} **{location['name']} — {zone['name']}**\n"
        f"🎯 Activité : **{_activity_label(view.tool_key)}**\n"
        f"⏳ Durée : **{zone['duration_label']}**\n\n"
        "### 🔧 CARROUSEL OUTIL\n"
        f"◀️  {tool_line}  ▶️\n"
        f"*Versions débloquées : niveau 1 à {gear.tool_level(view.tool_key)}*\n\n"
        "### 🎒 CARROUSEL SACOCHE\n"
        f"◀️  {bag_line}  ▶️\n"
        f"*Sacoches débloquées : niveau 1 à {gear.bag_level}*\n\n"
        + ("✅ **Prêt à partir.**" if ready else "❌ **Outil et sacoche obligatoires pour lancer l'expédition.**")
    )


class ExpeditionPreparationView(discord.ui.View):
    """Deux carrousels indépendants : outil + sacoche, puis lancement."""
    def __init__(self, owner_id: int, expedition_key: str, tool_key: str):
        super().__init__(timeout=900)
        self.owner_id = int(owner_id)
        self.expedition_key = expedition_key
        self.tool_key = tool_key
        gear = EXPEDITION_STORE.get_gear(owner_id)
        self.tool_level = gear.tool_level(tool_key)
        self.bag_level = gear.bag_level
        self.rebuild()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Cette préparation appartient à un autre joueur.", ephemeral=True)
            return False
        return True

    def rebuild(self):
        self.clear_items()
        gear = EXPEDITION_STORE.get_gear(self.owner_id)
        owned = EXPEDITION_STORE.owned_equipment(self.owner_id)

        tool_prev = discord.ui.Button(label="Outil", emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
        tool_next = discord.ui.Button(label="Outil", emoji="▶️", style=discord.ButtonStyle.secondary, row=0)
        bag_prev = discord.ui.Button(label="Sacoche", emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
        bag_next = discord.ui.Button(label="Sacoche", emoji="▶️", style=discord.ButtonStyle.secondary, row=1)

        tool_prev.disabled = tool_next.disabled = (not owned.get(self.tool_key, False) or gear.tool_level(self.tool_key) <= 1)
        bag_prev.disabled = bag_next.disabled = (not owned.get("bag", False) or gear.bag_level <= 1)

        async def tool_prev_cb(interaction: discord.Interaction):
            max_level = gear.tool_level(self.tool_key)
            self.tool_level = max_level if self.tool_level <= 1 else self.tool_level - 1
            self.rebuild()
            await interaction.response.edit_message(content=preparation_content(self), view=self)

        async def tool_next_cb(interaction: discord.Interaction):
            max_level = gear.tool_level(self.tool_key)
            self.tool_level = 1 if self.tool_level >= max_level else self.tool_level + 1
            self.rebuild()
            await interaction.response.edit_message(content=preparation_content(self), view=self)

        async def bag_prev_cb(interaction: discord.Interaction):
            max_level = gear.bag_level
            self.bag_level = max_level if self.bag_level <= 1 else self.bag_level - 1
            self.rebuild()
            await interaction.response.edit_message(content=preparation_content(self), view=self)

        async def bag_next_cb(interaction: discord.Interaction):
            max_level = gear.bag_level
            self.bag_level = 1 if self.bag_level >= max_level else self.bag_level + 1
            self.rebuild()
            await interaction.response.edit_message(content=preparation_content(self), view=self)

        tool_prev.callback = tool_prev_cb; tool_next.callback = tool_next_cb
        bag_prev.callback = bag_prev_cb; bag_next.callback = bag_next_cb
        self.add_item(tool_prev); self.add_item(tool_next); self.add_item(bag_prev); self.add_item(bag_next)

        can_launch = owned.get(self.tool_key, False) and owned.get("bag", False)
        launch = discord.ui.Button(
            label="Lancer l'expédition",
            emoji="🚩",
            style=discord.ButtonStyle.success,
            disabled=not can_launch,
            row=2,
        )
        back = discord.ui.Button(label="Retour", emoji="↩️", style=discord.ButtonStyle.secondary, row=2)

        async def launch_cb(interaction: discord.Interaction):
            if EXPEDITION_STORE.active_run(self.owner_id):
                await interaction.response.send_message("❌ Tu as déjà une expédition en cours.", ephemeral=True)
                return
            ok, msg, run = EXPEDITION_STORE.start(
                self.owner_id,
                self.expedition_key,
                self.tool_key,
                bag_level=self.bag_level,
                tool_level=self.tool_level,
            )
            if not ok or run is None:
                await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
                return

            # On revient immédiatement au début du lieu, comme demandé.
            location_key = EXPEDITIONS[self.expedition_key]["location_key"]
            await interaction.response.edit_message(
                content=location_home_content(self.owner_id, location_key, "🚩 **Expédition lancée !**"),
                view=ExplorationLocationView(self.owner_id, location_key),
            )

            # V1.70 : aucun panneau personnel n'est publié dans le salon de la zone.
            # Le suivi détaillé reste consultable uniquement par le joueur en revenant
            # dans la destination concernée. Seul un événement RP compact est envoyé
            # dans le salon public configuré avec /succes.
            await announce_expedition_start(interaction.guild, run)
            start_expedition_monitor(run.run_id)

        async def back_cb(interaction: discord.Interaction):
            await interaction.response.edit_message(
                content=activity_content(self.expedition_key),
                view=ExpeditionActivityView(self.owner_id, self.expedition_key),
            )

        launch.callback = launch_cb; back.callback = back_cb
        self.add_item(launch); self.add_item(back)


class ExpeditionLiveView(discord.ui.View):
    """Suivi serveur d'une expédition longue durée."""
    def __init__(self, owner_id: int, run_id: str):
        super().__init__(timeout=None)
        self.owner_id = int(owner_id)
        self.run_id = str(run_id)
        run = EXPEDITION_STORE.run_by_id(self.run_id)
        if run and not run.claimed:
            refresh = discord.ui.Button(
                label="Actualiser", emoji="🔄", style=discord.ButtonStyle.secondary,
                custom_id=f"altherya:expedition:live:refresh:{self.run_id}", row=0,
            )
            async def refresh_cb(interaction: discord.Interaction):
                if interaction.user.id != self.owner_id:
                    await interaction.response.send_message("Cette expédition appartient à un autre joueur.", ephemeral=True)
                    return
                await interaction.response.defer()
                await refresh_expedition_status(self.run_id)
            refresh.callback = refresh_cb
            self.add_item(refresh)


def expedition_live_content(run, compact: bool = False) -> str:
    zone = EXPEDITIONS[run.expedition_key]
    location = LOCATION_META[zone["location_key"]]
    tool_name = TOOL_LEVELS[run.tool_level][run.tool_key]
    bag_name = BAG_LEVELS[run.bag_level]["name"]
    revealed = run.loot if run.claimed else EXPEDITION_STORE.revealed_loot(run.run_id)
    total = sum(revealed.values())
    logs = EXPEDITION_STORE.drop_log(run.run_id, limit=6 if compact else 10)

    if run.claimed:
        status = "✅ **EXPÉDITION TERMINÉE — OBJETS TRANSFÉRÉS DANS L'INVENTAIRE**"
        timer = "00 min"
    elif run.finished:
        status = "⏳ **EXPÉDITION TERMINÉE — TRANSFERT EN COURS**"
        timer = "00 min"
    else:
        status = "🟢 **EXPÉDITION EN COURS**"
        mins = max(1, (run.remaining_seconds + 59) // 60)
        h, m = divmod(mins, 60)
        timer = f"{h} h {m:02d} min" if h else f"{m} min"

    if logs:
        log_lines = []
        for entry in logs:
            name = str(entry["resource_name"])
            qty = int(entry.get("quantity", 1))
            stamp = datetime.fromtimestamp(int(entry["drop_at"])).strftime("%H:%M")
            rarity = RARITY_EMOJI.get(RARITY.get(name, 1), "⚪")
            log_lines.append(f"`{stamp}` {rarity} **{name}** ×{qty}")
        log_text = "\n".join(log_lines)
    else:
        log_text = "*Aucun drop pour le moment…*"

    if run.claimed:
        filled = 12
    else:
        progress = min(1.0, max(0.0, (int(datetime.now().timestamp()) - run.started_at) / max(1, run.ends_at - run.started_at)))
        filled = int(progress * 12)
    bar = "█" * filled + "░" * (12 - filled)

    prefix = "" if compact else f"🧭 **EXPÉDITION DE <@{run.user_id}>**\n"
    return (
        f"{prefix}{status}\n\n"
        f"{location['emoji']} **{location['name']} — {zone['name']}**\n"
        f"🎯 **{_activity_label(run.tool_key)}**\n"
        f"{_activity_emoji(run.tool_key)} **{tool_name}**\n"
        f"🎒 **{bag_name}** — capacité {run.capacity}\n\n"
        f"⏳ **Temps restant : {timer}**\n"
        f"`{bar}`\n"
        f"📦 **Récolte : {total}/{run.capacity}**\n\n"
        f"📜 **LOGS DE L'EXPÉDITION**\n{log_text}"
    )


async def _get_expedition_status_message(run):
    if not run.status_channel_id or not run.status_message_id:
        return None
    try:
        channel = bot.get_channel(int(run.status_channel_id)) or await bot.fetch_channel(int(run.status_channel_id))
        return await channel.fetch_message(int(run.status_message_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
        return None


async def finalize_expedition_run(run_id: str) -> bool:
    """Finalise une fois, crédite l'inventaire et les récompenses de progression."""
    before = EXPEDITION_STORE.run_by_id(run_id)
    ok, _, loot, final_run = EXPEDITION_STORE.finalize_run(run_id)
    if not ok or final_run is None:
        return False

    # finalize_run n'est vrai que lors du premier transfert : XP/quête ne peuvent donc
    # pas être doublés, même si Coolify redémarre exactement au moment de la fin.
    CASTLE_STORE.record(final_run.user_id, "expedition")
    CASTLE_STORE.add_xp(final_run.user_id, 20)

    # V1.70 : le message mémorisé est l'annonce publique /succes, pas le panneau privé.
    # On transforme donc l'annonce « en cours » en résultat final au lieu de la supprimer.
    await finish_expedition_announcement(final_run)
    return True


async def refresh_expedition_status(run_id: str):
    run = EXPEDITION_STORE.run_by_id(run_id)
    if not run:
        return
    if not run.claimed:
        EXPEDITION_STORE.reveal_due_events(run_id)
        run = EXPEDITION_STORE.run_by_id(run_id) or run
        if run.finished:
            await finalize_expedition_run(run_id)
            run = EXPEDITION_STORE.run_by_id(run_id) or run
    # V1.70 : ne jamais pousser le timer/logs personnels dans un salon public.
    # Le panneau live est reconstruit à la demande dans la destination du joueur.
    return


async def monitor_expedition(run_id: str):
    """Actualise timer/logs, puis transfère automatiquement le butin à 00:00."""
    try:
        while True:
            run = EXPEDITION_STORE.run_by_id(run_id)
            if not run or run.claimed:
                return
            EXPEDITION_STORE.reveal_due_events(run_id)
            await refresh_expedition_status(run_id)
            run = EXPEDITION_STORE.run_by_id(run_id)
            if not run or run.claimed:
                return
            if run.finished:
                await finalize_expedition_run(run_id)
                return
            now = int(datetime.now().timestamp())
            next_drop = EXPEDITION_STORE.next_drop_at(run_id)
            next_minute = now + 60
            wake_at = min(next_minute, next_drop) if next_drop else next_minute
            await asyncio.sleep(max(1, wake_at - now))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(f"[EXPEDITION V1.66] monitor {run_id} : {exc}")
    finally:
        EXPEDITION_MONITORS.pop(str(run_id), None)


def start_expedition_monitor(run_id: str):
    old = EXPEDITION_MONITORS.get(str(run_id))
    if old and not old.done():
        return
    EXPEDITION_MONITORS[str(run_id)] = asyncio.create_task(monitor_expedition(str(run_id)))


async def open_exploration_location(interaction: discord.Interaction, location_key: str, *, edit: bool = False):
    if location_key not in LOCATION_META:
        if edit:
            await interaction.response.edit_message(content="Zone inconnue.", attachments=[], embeds=[], view=WorldHubView())
        else:
            await interaction.response.send_message("Zone inconnue.", ephemeral=True)
        return
    active = EXPEDITION_STORE.active_run(interaction.user.id)
    if active and active.finished:
        await finalize_expedition_run(active.run_id)
    file = discord.File(_zone_asset(location_key), filename=f"{location_key}.png")
    content = location_home_content(interaction.user.id, location_key)
    view = ExplorationLocationView(interaction.user.id, location_key)
    if edit:
        await interaction.response.edit_message(content=content, attachments=[file], embeds=[], view=view)
    else:
        # Première ouverture : une seule fenêtre privée est créée. Ensuite toute la navigation l'édite.
        await interaction.response.send_message(content=content, file=file, view=view, ephemeral=True)


# ============================================================
# RUELLE SOMBRE — 3 PNJ
# ============================================================

def alley_home_content(user_id: int) -> str:
    rep = DARK_STORE.criminal_reputation(user_id)
    remaining = DARK_STORE.ban_remaining(user_id)
    if remaining: return f"🔒 **Accès refusé**\n⏳ Retour dans **{short_time(remaining)}**."
    return ("🌑 **Ruelle sombre de Altherya**\n"
            f"🐺 Réputation : **{rep['label']}** • Méfaits : **{rep['successes']}**\n\n"
            "🔓 Petite frappe : vols de PNJ et joueurs\n🔓 Bandit : crimes\n🔓 Criminel : braquages\n🔓 Seigneur de la Ruelle : contrats spéciaux")

def thief_content(user_id: int) -> str:
    rep=DARK_STORE.criminal_reputation(user_id)
    return (f"🐺 **Le Voleur** — Rang : **{rep['label']}**\n\n"
            "Inconnu : petits larcins pour se faire un nom.\n"
            "Petite frappe : vols de PNJ et de joueurs.\n"
            "Bandit : crimes plus sérieux.\n"
            "Seigneur : contrats criminels spéciaux." + npc_alcohol_reaction(user_id, "voleur"))

def robber_content(user_id: int) -> str:
    rep=DARK_STORE.criminal_reputation(user_id)
    heist=DARK_STORE.active_heist(user_id)
    if rep['label'] not in ("Criminel","Seigneur de la Ruelle"):
        return f"🐯 **Le Braqueur**\n🔒 Rang **Criminel** requis.\nTon rang : **{rep['label']}." + npc_alcohol_reaction(user_id, "braqueur")
    if heist:
        return ("🐯 **Braquage de la Banque en cours**\n"
                f"🔐 {HEIST_CODE_LENGTH} chiffres différents • 🎯 {heist.attempts_left}/{HEIST_ATTEMPTS} essais\n"
                "🟢 bien placé · 🟠 mal placé · ⚫ incorrect" + npc_alcohol_reaction(user_id, "braqueur"))
    return ("🐯 **Le Braqueur**\nTon rang criminel permet désormais de préparer des braquages.\n"
            "🏦 Première cible disponible : **Banque de Altherya**. D'autres cibles pourront rejoindre le réseau." + npc_alcohol_reaction(user_id, "braqueur"))


def guard_content(user_id: int) -> str:
    invitations = DARK_STORE.invitation_count(user_id)
    loyalty = CASINO_STORE.loyalty(user_id)
    max_bet = VIP_MAX_BET if loyalty.get("vip") else MAX_BET
    return (
        "🐻 **Le Vigile**\n"
        "La salle de jeux clandestine est derrière lui.\n\n"
        f"🎰 Fidélité Casino : **{loyalty['label']}** • Victoires : **{loyalty['wins']}**\n"
        f"🎟️ Invitations : **{invitations}**\n"
        + ("👑 **Statut VIP : entrée gratuite.**\n\n" if loyalty["vip"] else f"💰 Entrée sans invitation : **{GUARD_ENTRY_FEE} Gold**\n\n")
        + ("Le Vigile te reconnaît désormais et te laisse entrer gratuitement." if loyalty["vip"] else "Une invitation utilisée est consommée.")
        + npc_alcohol_reaction(user_id, "vigile")
    )


async def show_alley_home(interaction: discord.Interaction):
    remaining = DARK_STORE.ban_remaining(interaction.user.id)
    if remaining:
        await safe_defer(interaction)
        await interaction.followup.send(
            f"🔒 Après ton dernier braquage, tu n'es plus le bienvenu ici.\n"
            f"⏳ Retour possible dans **{short_time(remaining)}**.",
            ephemeral=True,
        )
        return
    await safe_defer(interaction)
    await edit_with_asset(interaction, PLACES / "alley.png", "ruelle.png", DarkAlleyView(), alley_home_content(interaction.user.id))


class DarkAlleyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        thief = discord.ui.Button(label="Le Voleur", emoji="🐺", style=discord.ButtonStyle.secondary,
                                  custom_id="legacy:alley:thief")
        robber = discord.ui.Button(label="Le Braqueur", emoji="🐯", style=discord.ButtonStyle.danger,
                                   custom_id="legacy:alley:robber")
        guard = discord.ui.Button(label="Le Vigile", emoji="🐻", style=discord.ButtonStyle.primary,
                                  custom_id="legacy:alley:guard")
        panel = discord.ui.Button(label="Panneau de la Ruelle", emoji="📌", style=discord.ButtonStyle.secondary,
                                  custom_id="legacy:alley:panel")
        leave = discord.ui.Button(label="Quitter la ruelle", emoji="🚪", style=discord.ButtonStyle.secondary,
                                  custom_id="legacy:alley:leave")

        async def thief_cb(interaction: discord.Interaction):
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES/"alley_thief.png", "voleur.png", ThiefView(), thief_content(interaction.user.id))

        async def robber_cb(interaction: discord.Interaction):
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES/"alley_robber.png", "braqueur.png", RobberView(), robber_content(interaction.user.id))

        async def guard_cb(interaction: discord.Interaction):
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES/"alley_guard.png", "vigile.png", GuardView(interaction.user.id), guard_content(interaction.user.id))

        async def panel_cb(interaction: discord.Interaction):
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES / "alley.png", "ruelle.png", DarkAlleyPanelView(), alley_panel_content(interaction.user.id))

        async def leave_cb(interaction: discord.Interaction):
            await return_to_hub(interaction)

        thief.callback = thief_cb; robber.callback = robber_cb; guard.callback = guard_cb; panel.callback = panel_cb; leave.callback = leave_cb
        self.add_item(thief); self.add_item(robber); self.add_item(guard); self.add_item(panel); self.add_item(leave)


def alley_panel_content(user_id: int) -> str:
    rep = DARK_STORE.criminal_reputation(user_id)
    return (
        "📌 **PANNEAU DE LA RUELLE SOMBRE**\n"
        "Les informations qui circulent dans la Ruelle sont regroupées ici.\n\n"
        "📜 **Contrats criminels** — consulte tes missions clandestines adaptées à ta réputation.\n"
        "📋 **Casier judiciaire** — consulte l'historique de ta carrière criminelle.\n\n"
        f"🐺 Réputation actuelle : **{rep['label']}** • **{rep['successes']} méfaits**"
    )


class DarkAlleyPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        contract = discord.ui.Button(label="Contrats criminels", emoji="📜", style=discord.ButtonStyle.primary, custom_id="legacy:alley:panel:contract")
        record = discord.ui.Button(label="Casier judiciaire", emoji="📋", style=discord.ButtonStyle.secondary, custom_id="legacy:alley:panel:record")
        back = discord.ui.Button(label="Retour à la ruelle", emoji="↩️", style=discord.ButtonStyle.secondary, custom_id="legacy:alley:panel:back")

        async def contract_cb(i):
            r = DARK_STORE.special_contract(i.user.id)
            if not r.get('ok'):
                await i.response.send_message(r.get('message', 'Contrat indisponible.'), ephemeral=True); return
            if r.get('claimed'):
                await announce_gold_activity(i.guild, i.user, int(r['amount']), "Contrat criminel", public=False)
                msg = f"📜 **Contrat accompli !** Récompense : **+{r['amount']} Gold**."
            else:
                c=r.get('contract',{}); target=int(c.get('target',0)); labels={'steal_npc':f'Voler {target} PNJ', 'crime':f'Réussir {target} crime'+('s' if target>1 else ''), 'heist':f'Réussir {target} braquage'+('s' if target>1 else '')+' de Banque'}
                left=max(0,int(c.get('expires_at',0))-int(__import__('time').time()))
                msg=(f"📜 **Contrat criminel {'reçu' if r.get('new') else 'en cours'} — {r.get('rank','Ruelle')}**\n"
                     f"Mission : **{labels.get(c.get('contract_type'),'Mission clandestine')}**\n"
                     f"Progression : **{c.get('progress',0)}/{c.get('target',0)}**\n"
                     f"Récompense : **{c.get('reward',0)} Gold**\n⏳ Expire dans **{short_time(left)}**.\n"
                     f"Reviens sur le panneau une fois l'objectif terminé pour encaisser.")
            await i.response.send_message(msg, ephemeral=True)

        async def record_cb(i):
            r=DARK_STORE.criminal_record(i.user.id); rep=DARK_STORE.criminal_reputation(i.user.id)
            msg=(f"📋 **CASIER JUDICIAIRE — {i.user.display_name}**\n"
                 f"🐺 Réputation : **{rep['label']}** ({rep['successes']} méfaits)\n\n"
                 f"✅ Vols réussis : **{r['theft_success']}**\n❌ Vols ratés : **{r['theft_fail']}**\n"
                 f"🚨 Pris sur le fait : **{r['caught']}**\n🕶️ Crimes réussis : **{r['crimes_success']}**\n"
                 f"🏦 Braquages réussis : **{r['heists_success']}**\n💰 Gold volé : **{r['gold_stolen']}**\n"
                 f"💎 Plus gros butin : **{r['biggest_loot']} Gold**")
            await i.response.send_message(msg, ephemeral=True)

        async def back_cb(i):
            await show_alley_home(i)

        contract.callback=contract_cb; record.callback=record_cb; back.callback=back_cb
        self.add_item(contract); self.add_item(record); self.add_item(back)


class ThiefTargetSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Choisir le joueur à voler...", min_values=1, max_values=1,
                         custom_id="legacy:alley:thief:target")

    async def callback(self, interaction: discord.Interaction):
        target = self.values[0]
        if target.bot:
            await interaction.response.send_message("🐺 Le Voleur refuse de cibler un bot.", ephemeral=True)
            return
        result = DARK_STORE.steal(interaction.user.id, target.id)
        if not result.get("ok"):
            if result.get("cooldown"):
                await interaction.response.send_message(
                    f"⏳ Tu dois attendre **{short_time(result['cooldown'])}** avant un nouveau vol.", ephemeral=True)
            else:
                await interaction.response.send_message(result.get("message", "Vol impossible."), ephemeral=True)
            return

        outcome = result["outcome"]
        amount = int(result.get("amount", 0))
        sp,fp,cp=result.get("chances",(0,0,0)); risk=f"\n🎯 Cible **{result.get('victim_rep','Inconnu')}** — réussite {int(sp*100)}% • échec {int(fp*100)}% • riposte {int(cp*100)}%"
        if outcome == "success":
            rep = DARK_STORE.criminal_reputation(interaction.user.id)
            if rep["tier"]: await announce_achievement(interaction, f"criminal_reputation:{rep['tier']}")
            text = (f"✅ **Vol réussi !** Tu subtilises **{amount} Gold** à {target.mention}."
                    if amount else f"✅ Tu réussis ton coup... mais {target.mention} n'avait aucun Gold sur lui.")
            if amount:
                await announce_gold_activity(interaction.guild, interaction.user, amount, f"Vol réussi contre {target.display_name}", counterpart=target, public=False)
                await announce_gold_activity(interaction.guild, target, -amount, f"Victime d'un vol par {interaction.user.display_name}", counterpart=interaction.user, public=False)
                await announce_public_result(
                    interaction.guild, interaction.user, "🐺 Vol réussi",
                    f"a volé **{amount} Gold** à {target.mention}.",
                    color=discord.Color.green()
                )
            else:
                await announce_public_result(interaction.guild, interaction.user, "🐺 Vol réussi",
                                             f"a réussi à voler {target.mention}, mais n'a trouvé aucun Gold.", color=discord.Color.green())
        elif outcome == "fail":
            text = "😑 **Échec.** Tu t'y prends comme un manche et repars les mains vides."
            await announce_public_result(interaction.guild, interaction.user, "🐺 Vol raté",
                                         f"a tenté de voler {target.mention}, sans succès.", color=discord.Color.orange())
        else:
            text = (f"💥 **Pris sur le fait !** {target.mention} te corrige et récupère **{amount} Gold** sur toi."
                    if amount else f"💥 **Pris sur le fait !** {target.mention} te corrige, mais tu n'avais aucun Gold à prendre.")
            if amount:
                await announce_gold_activity(interaction.guild, interaction.user, -amount, f"Vol raté : {target.display_name} récupère ton Gold", counterpart=target, public=False)
                await announce_gold_activity(interaction.guild, target, amount, f"A surpris {interaction.user.display_name} en train de voler", counterpart=interaction.user, public=False)
                await announce_public_result(
                    interaction.guild, interaction.user, "💥 Voleur démasqué",
                    f"a tenté de voler {target.mention}, s'est fait tabasser et perd **{amount} Gold**.  **-{amount} Gold** pour {interaction.user.mention} • **+{amount} Gold** pour {target.mention}",
                    color=discord.Color.red()
                )
            else:
                await announce_public_result(interaction.guild, interaction.user, "💥 Voleur démasqué",
                                             f"a tenté de voler {target.mention} et s'est fait tabasser, sans perte de Gold.", color=discord.Color.red())
        await interaction.response.send_message(text + risk + "\n⏳ Nouveau vol possible dans 1 heure.", ephemeral=True)


class ThiefTargetView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(ThiefTargetSelect())
        back = discord.ui.Button(label="Annuler", emoji="↩️", style=discord.ButtonStyle.secondary,
                                 custom_id="legacy:alley:thief:target:back")
        async def back_cb(interaction: discord.Interaction):
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES/"alley_thief.png", "voleur.png", ThiefView(), thief_content(interaction.user.id))
        back.callback = back_cb
        self.add_item(back)


class NPCTargetSelect(discord.ui.Select):
    def __init__(self):
        options=[discord.SelectOption(label=v[0], value=k, emoji="🪙", description=f"Réussite : {int(v[3]*100)}% • Butin {v[1]}–{v[2]} Gold") for k,v in __import__('dark_alley').NPC_THEFT_TARGETS.items()]
        super().__init__(placeholder="Choisir un PNJ à voler...", options=options, custom_id="legacy:alley:npc:target")
    async def callback(self, interaction: discord.Interaction):
        result=DARK_STORE.steal_npc(interaction.user.id,self.values[0])
        if not result.get('ok'):
            msg=(f"⏳ Nouveau vol dans **{short_time(result['cooldown'])}**." if result.get('cooldown') else result.get('message','Vol impossible.'))
            await interaction.response.send_message(msg,ephemeral=True); return
        if result['outcome']=='success':
            rep=DARK_STORE.criminal_reputation(interaction.user.id)
            if rep['tier']: await announce_achievement(interaction,f"criminal_reputation:{rep['tier']}")
            await announce_gold_activity(interaction.guild,interaction.user,int(result['amount']),f"Vol du PNJ {result['target']}",public=False)
            msg=f"✅ Tu dérobes **{result['amount']} Gold** à **{result['target']}**."
        elif result['outcome']=='caught':
            amount=int(result.get('amount',0))
            if amount: await announce_gold_activity(interaction.guild,interaction.user,-amount,f"Pris en volant {result['target']}",public=False)
            msg=f"💥 **{result['target']}** te surprend et te fait payer **{amount} Gold** avant de te chasser !" if amount else f"💥 **{result['target']}** te surprend. Tu prends la fuite !"
        else: msg=f"😑 **{result['target']}** ne te laisse aucune ouverture."
        await interaction.response.send_message(msg+"\n⏳ Nouveau vol possible dans 1 heure.",ephemeral=True)

class NPCTargetView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180); self.add_item(NPCTargetSelect())

class ThiefView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        larceny=discord.ui.Button(label="Petit larcin",emoji="🪙",style=discord.ButtonStyle.secondary,custom_id="legacy:alley:larceny")
        npc=discord.ui.Button(label="Voler un PNJ",emoji="🎭",style=discord.ButtonStyle.danger,custom_id="legacy:alley:npc")
        steal=discord.ui.Button(label="Voler un joueur",emoji="💰",style=discord.ButtonStyle.danger,custom_id="legacy:alley:thief:steal")
        crime=discord.ui.Button(label="Commettre un crime",emoji="🕶️",style=discord.ButtonStyle.danger,custom_id="legacy:alley:thief:crime")
        back=discord.ui.Button(label="Retour à la ruelle",emoji="↩️",style=discord.ButtonStyle.secondary,custom_id="legacy:alley:thief:back")
        async def larceny_cb(i):
            await safe_defer(i)
            r=DARK_STORE.petty_larceny(i.user.id)
            if not r.get('ok'):
                await i.followup.send(f"⏳ Nouveau larcin dans **{short_time(r.get('cooldown',0))}**.",ephemeral=True); return
            rep=DARK_STORE.criminal_reputation(i.user.id)
            if rep['tier']: await announce_achievement(i,f"criminal_reputation:{rep['tier']}")
            if r['amount']: await announce_gold_activity(i.guild,i.user,int(r['amount']),"Petit larcin",public=False)
            await i.followup.send(f"🪙 Petit larcin réussi : **+{r['amount']} Gold**. Réputation : **{rep['label']}**.\n⏳ Nouveau larcin dans **30 min**.",ephemeral=True)
        async def npc_cb(i):
            if DARK_STORE.criminal_reputation(i.user.id)['label'] not in ("Petite frappe","Bandit","Criminel","Seigneur de la Ruelle"):
                await i.response.send_message("🔒 Rang **Petite frappe** requis.",ephemeral=True); return
            await safe_defer(i); await edit_with_asset(i,PLACES/"alley_thief.png","voleur.png",NPCTargetView(),"🎭 **Choisis le PNJ que tu veux tenter de voler.**")
        async def steal_cb(i):
            if DARK_STORE.criminal_reputation(i.user.id)['label'] not in ("Petite frappe","Bandit","Criminel","Seigneur de la Ruelle"):
                await i.response.send_message("🔒 Rang **Petite frappe** requis.",ephemeral=True); return
            cd=DARK_STORE.cooldown_remaining(i.user.id,"steal")
            if cd: await i.response.send_message(f"⏳ Nouveau vol dans **{short_time(cd)}**.",ephemeral=True); return
            await safe_defer(i); await edit_with_asset(i,PLACES/"alley_thief.png","voleur.png",ThiefTargetView(),"🐺 **Choisis le joueur à voler.**")
        async def crime_cb(i):
            r=DARK_STORE.commit_crime(i.user.id)
            if not r.get('ok'):
                msg=r.get('message') or f"⏳ Nouveau crime dans **{short_time(r.get('cooldown',0))}**."
                await i.response.send_message(msg,ephemeral=True); return
            amount=int(r.get('amount',0)); outcome=r['outcome']
            if outcome=='success':
                rep=DARK_STORE.criminal_reputation(i.user.id)
                if rep['tier']: await announce_achievement(i,f"criminal_reputation:{rep['tier']}")
                if amount: await announce_gold_activity(i.guild,i.user,amount,"Crime réussi",public=False)
                msg=f"✅ Crime réussi : **+{amount} Gold**."
            elif outcome=='caught':
                if amount: await announce_gold_activity(i.guild,i.user,-amount,"Amende après crime",public=False)
                msg=f"🚓 Pris sur le fait : **-{amount} Gold**."
            else: msg="😑 Crime raté. Rien de gagné."
            await i.response.send_message(msg,ephemeral=True)
        async def back_cb(i): await show_alley_home(i)
        larceny.callback=larceny_cb; npc.callback=npc_cb; steal.callback=steal_cb; crime.callback=crime_cb; back.callback=back_cb
        for b in (larceny,npc,steal,crime,back): self.add_item(b)


class HeistGuessModal(discord.ui.Modal, title="Code du coffre"):
    code_guess = discord.ui.TextInput(
        label="Ta combinaison",
        placeholder="Exemple : 5072",
        min_length=HEIST_CODE_LENGTH,
        max_length=HEIST_CODE_LENGTH,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        result = DARK_STORE.guess_heist(interaction.user.id, str(self.code_guess.value))
        if not result.get("ok"):
            await interaction.response.send_message(result.get("message", "Combinaison invalide."), ephemeral=True)
            return
        await safe_defer(interaction)
        icons = {"bien placé": "🟢", "mal placé": "🟠", "incorrect": "⚫"}
        fb = "\n".join(f"{icons[status]} **{digit}** : {status}" for digit, status in result.get("details", []))
        if result.get("won"):
            rep = DARK_STORE.criminal_reputation(interaction.user.id)
            if rep["tier"]: await announce_achievement(interaction, f"criminal_reputation:{rep['tier']}")
            if result.get("reward"):
                await announce_gold_activity(interaction.guild, interaction.user, int(result["reward"]), "Braquage réussi dans la Ruelle sombre")
            else:
                await announce_public_result(interaction.guild, interaction.user, "🏦 Braquage réussi",
                                             "a réussi à braquer la banque, mais le coffre était vide.", color=discord.Color.green())
            content = (
                f"💰 **BRAQUAGE RÉUSSI !**\nCombinaison **{result['guess']}** — coffre ouvert.\n"
                f"Butin : **+{result['reward']} Gold**\n\n{fb}"
            )
            await edit_with_asset(interaction, PLACES/"alley_robber.png", "braqueur.png", RobberView(), content)
            return
        if result.get("lost"):
            if result.get("fine"):
                await announce_gold_activity(interaction.guild, interaction.user, -int(result["fine"]), "Amende après un braquage raté")
            else:
                await announce_public_result(interaction.guild, interaction.user, "🚨 Braquage raté",
                                             "a tenté de braquer la banque, mais a échoué sans perte de Gold.", color=discord.Color.red())
            content = (
                f"🚨 **BRAQUAGE RATÉ !**\nLe code était **{result['code']}**.\n{fb}\n\n"
                f"💸 Amende payée : **{result['fine']} Gold**\n"
                f"🔒 Interdiction de Ruelle sombre : **5 heures**."
            )
            await edit_with_asset(interaction, PLACES/"alley_robber.png", "braqueur.png", BannedAlleyView(), content)
            return
        content = (
            f"🔐 **Combinaison proposée : {result['guess']}**\n{fb}\n"
            f"🎯 Tentatives restantes : **{result['attempts_left']}**"
        )
        await edit_with_asset(interaction, PLACES/"alley_robber.png", "braqueur.png", HeistView(), content)


class HeistView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        guess = discord.ui.Button(label="Proposer un code", emoji="🔢", style=discord.ButtonStyle.danger,
                                  custom_id="legacy:alley:heist:guess")
        leave = discord.ui.Button(label="Quitter le plan", emoji="↩️", style=discord.ButtonStyle.secondary,
                                  custom_id="legacy:alley:heist:leave")

        async def guess_cb(interaction: discord.Interaction):
            heist = DARK_STORE.active_heist(interaction.user.id)
            if not heist:
                await interaction.response.send_message("Ce braquage n'est plus actif.", ephemeral=True)
                return
            await interaction.response.send_modal(HeistGuessModal())

        async def leave_cb(interaction: discord.Interaction):
            # Quitter l'écran n'annule pas le braquage : le joueur peut revenir et reprendre ses essais.
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES/"alley_robber.png", "braqueur.png", RobberView(), robber_content(interaction.user.id))

        guess.callback = guess_cb; leave.callback = leave_cb
        self.add_item(guess); self.add_item(leave)


class RobberView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        plan = discord.ui.Button(label="Planifier le braquage", emoji="🏦", style=discord.ButtonStyle.danger,
                                 custom_id="legacy:alley:robber:plan")
        back = discord.ui.Button(label="Retour à la ruelle", emoji="↩️", style=discord.ButtonStyle.secondary,
                                 custom_id="legacy:alley:robber:back")

        async def plan_cb(interaction: discord.Interaction):
            ok, status, heist = DARK_STORE.start_heist(interaction.user.id)
            if not ok:
                if status == "rank_locked":
                    await interaction.response.send_message("🔒 Le Braqueur ne travaille qu'avec les criminels reconnus. Rang **Criminel** requis.", ephemeral=True); return
                remaining = DARK_STORE.ban_remaining(interaction.user.id)
                await interaction.response.send_message(f"🔒 Tu es interdit de Ruelle sombre encore **{short_time(remaining)}**.", ephemeral=True); return
            await safe_defer(interaction)
            prefix = "♻️ **Plan retrouvé.**" if status == "existing" else "🏦 **Le braquage commence.**"
            content = (
                f"{prefix}\nTrouve la combinaison de **{HEIST_CODE_LENGTH} chiffres différents**.\n"
                f"🎯 Tentatives restantes : **{heist.attempts_left}/{HEIST_ATTEMPTS}**\n\n"
                "🟢 bon chiffre, bonne place · 🟠 bon chiffre, mauvaise place · ⚫ chiffre absent"
            )
            await edit_with_asset(interaction, PLACES/"alley_robber.png", "braqueur.png", HeistView(), content)

        async def back_cb(interaction: discord.Interaction):
            await show_alley_home(interaction)

        plan.callback = plan_cb; back.callback = back_cb
        self.add_item(plan); self.add_item(back)


class GuardView(discord.ui.View):
    def __init__(self, owner_id: int | None = None):
        super().__init__(timeout=None)
        self.owner_id = int(owner_id) if owner_id is not None else None
        if self.owner_id is not None and DARK_STORE.has_clandestine_access(self.owner_id):
            enter = discord.ui.Button(label="Rentrer",emoji="🚪",style=discord.ButtonStyle.success,custom_id="legacy:alley:guard:enter")
            back_paid = discord.ui.Button(label="Retour à la ruelle",emoji="↩️",style=discord.ButtonStyle.secondary,custom_id="legacy:alley:guard:back_paid")
            async def enter_cb(i):
                if i.user.id != self.owner_id: await i.response.send_message("Ce pass appartient à un autre joueur.",ephemeral=True); return
                await safe_defer(i); await edit_with_asset(i,PLACES/"casino_room.png","casino.png",CasinoMainView(),casino_home_content(i.user.id))
            async def back_paid_cb(i): await show_alley_home(i)
            enter.callback=enter_cb; back_paid.callback=back_paid_cb
            self.add_item(enter); self.add_item(back_paid); return
        invite = discord.ui.Button(label="Utiliser une invitation", emoji="🎟️", style=discord.ButtonStyle.success,
                                   custom_id="legacy:alley:guard:invite")
        pay = discord.ui.Button(label=f"Payer {GUARD_ENTRY_FEE} Gold", emoji="💰", style=discord.ButtonStyle.primary,
                                custom_id="legacy:alley:guard:pay")
        vip = discord.ui.Button(label="Entrée VIP", emoji="👑", style=discord.ButtonStyle.success,
                                custom_id="legacy:alley:guard:vip")
        back = discord.ui.Button(label="Retour à la ruelle", emoji="↩️", style=discord.ButtonStyle.secondary,
                                 custom_id="legacy:alley:guard:back")

        async def invite_cb(interaction: discord.Interaction):
            result = DARK_STORE.enter_clandestine_room(interaction.user.id, True)
            if not result.get("ok"):
                await interaction.response.send_message(result["message"], ephemeral=True)
                return
            if result.get("already"):
                await safe_defer(interaction)
                await edit_with_asset(interaction, PLACES/"casino_room.png", "casino.png", CasinoMainView(), casino_home_content(interaction.user.id))
                return
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES/"casino_room.png", "casino.png", CasinoMainView(),
                                  "🎟️ **Le Vigile déchire ton invitation et te laisse passer.**\n\n" + casino_home_content(interaction.user.id))

        async def pay_cb(interaction: discord.Interaction):
            result = DARK_STORE.enter_clandestine_room(interaction.user.id, False)
            if not result.get("ok"):
                await interaction.response.send_message(result["message"], ephemeral=True)
                return

            # IMPORTANT : acquitter l'interaction Discord immédiatement après le paiement.
            # Avant ce correctif, le journal économique était envoyé AVANT le defer :
            # si l'envoi du log prenait trop de temps, Discord expirait l'interaction.
            # Le Gold était bien débité et le pass accordé, mais l'écran restait chez le Vigile.
            await safe_defer(interaction)

            if result.get("already"):
                await edit_with_asset(interaction, PLACES/"casino_room.png", "casino.png", CasinoMainView(), casino_home_content(interaction.user.id))
                return
            if result.get("method") == "vip":
                await edit_with_asset(interaction, PLACES/"casino_room.png", "casino.png", CasinoMainView(),
                                      "👑 **Le Vigile te reconnaît : entrée VIP gratuite.**\n\n" + casino_home_content(interaction.user.id))
                return

            # On fait entrer le joueur en priorité. Le journal économique est secondaire
            # et ne doit jamais bloquer l'accès à la salle après un paiement réussi.
            await edit_with_asset(interaction, PLACES/"casino_room.png", "casino.png", CasinoMainView(),
                                  f"💰 **{result['paid']} Gold remis au Vigile.** Il s'écarte sans poser de question.\n\n" + casino_home_content(interaction.user.id))
            await announce_gold_activity(interaction.guild, interaction.user, -int(result.get('paid', GUARD_ENTRY_FEE)), "Entrée payante au Casino clandestin")

        async def vip_cb(interaction: discord.Interaction):
            if not CASINO_STORE.loyalty(interaction.user.id)["vip"]:
                await interaction.response.send_message("👑 Le Vigile ne te reconnaît pas encore comme VIP.", ephemeral=True)
                return
            result = DARK_STORE.enter_clandestine_room(interaction.user.id, False)
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES/"casino_room.png", "casino.png", CasinoMainView(),
                                  "👑 **Le Vigile te reconnaît et s'écarte. Entrée VIP gratuite.**\n\n" + casino_home_content(interaction.user.id))

        async def back_cb(interaction: discord.Interaction):
            await show_alley_home(interaction)

        invite.callback = invite_cb; pay.callback = pay_cb; vip.callback = vip_cb; back.callback = back_cb
        self.add_item(invite); self.add_item(pay); self.add_item(vip); self.add_item(back)



# =========================
# SALLE DE JEUX CLANDESTINE
# =========================

CASINO_GAME_LABELS = {
    "blackjack": "Black Jack",
    "roulette": "Roulette",
    "russian": "Roulette Russe",
    "slots": "Machine à sous",
    "horses": "Courses de chevaux",
}


def casino_home_content(user_id: int) -> str:
    access = DARK_STORE.clandestine_access_info(user_id)
    wallet = CASINO_STORE.wallet(user_id)
    left = short_time(access.get("seconds_left", 0)) if access.get("valid") else "expiré"
    loyalty = CASINO_STORE.loyalty(user_id)
    # La limite de mise dépend du statut VIP.
    # Cette variable manquait auparavant, provoquant un NameError juste après
    # le paiement du Vigile : les Gold étaient débités mais l'écran du Casino
    # ne pouvait pas être rendu.
    max_bet = VIP_MAX_BET if loyalty.get("vip") else MAX_BET
    return (
        "♠️ **SALLE DE JEUX CLANDESTINE**\n"
        "Les prédateurs de Altherya misent gros et ne quittent jamais la table des yeux.\n\n"
        f"💰 Gold sur toi : **{wallet}**\n"
        f"🎰 Fidélité : **{loyalty['label']}** • **{loyalty['wins']} victoires**\n"
        f"🎟️ Accès journalier : **{left}**\n"
        f"🎲 Mise autorisée : **{MIN_BET} à {max_bet} Gold**" + (" 👑" if loyalty.get("vip") else "") + "\n\n"
        "Choisis ton jeu."
    )


async def eject_from_casino(interaction: discord.Interaction):
    await safe_defer(interaction)
    text = (
        "🐻 **Le Vigile pose une patte énorme sur ton épaule.**\n"
        "Ton accès n'est plus valide. Il te raccompagne dehors sans discussion.\n\n"
        "Pour rentrer à nouveau, paie l'entrée ou utilise une nouvelle invitation."
    )
    await edit_with_asset(interaction, PLACES/"alley_guard.png", "vigile.png", GuardView(), text)


async def casino_access_or_eject(interaction: discord.Interaction, session_id: str | None = None) -> bool:
    if DARK_STORE.has_clandestine_access(interaction.user.id):
        return True
    # Si minuit coupe une partie en cours, la mise est rendue avant l'expulsion.
    if session_id:
        CASINO_STORE.refund(session_id)
        BLACKJACK_STATES.pop(session_id, None) if "BLACKJACK_STATES" in globals() else None
        RUSSIAN_STATES.pop(session_id, None) if "RUSSIAN_STATES" in globals() else None
    await eject_from_casino(interaction)
    return False


async def show_casino_home(interaction: discord.Interaction):
    if not await casino_access_or_eject(interaction):
        return
    await safe_defer(interaction)
    await edit_with_asset(interaction, PLACES/"casino_room.png", "casino.png", CasinoMainView(), casino_home_content(interaction.user.id))


class CasinoBetModal(discord.ui.Modal):
    def __init__(self, game_type: str, horse_choice: int | None = None, horse_odds: list[float] | None = None):
        super().__init__(title=f"Mise — {CASINO_GAME_LABELS[game_type]}")
        self.game_type = game_type
        self.horse_choice = horse_choice
        self.horse_odds = list(horse_odds) if horse_odds else None
        self.bet = discord.ui.TextInput(
            label=f"Mise en Gold (VIP jusqu’à {VIP_MAX_BET})",
            placeholder="Exemple : 100",
            min_length=1,
            max_length=3,
            required=True,
        )
        self.add_item(self.bet)

    async def on_submit(self, interaction: discord.Interaction):
        if not DARK_STORE.has_clandestine_access(interaction.user.id):
            await eject_from_casino(interaction)
            return
        try:
            wager = int(str(self.bet.value).strip())
        except ValueError:
            await interaction.response.send_message("❌ Entre une mise entière en Gold.", ephemeral=True)
            return
        result = CASINO_STORE.start(interaction.user.id, self.game_type, wager)
        if not result.get("ok"):
            await interaction.response.send_message(result.get("message", "Mise impossible."), ephemeral=True)
            return
        CASTLE_STORE.record(interaction.user.id, "casino")
        await safe_defer(interaction)
        await show_pending_levelups(interaction, interaction.user.id)
        if self.game_type == "blackjack":
            await start_blackjack(interaction, result["session_id"], wager)
        elif self.game_type == "roulette":
            await edit_with_asset(interaction, PLACES/"casino_room.png", "casino.png", RouletteChoiceView(interaction.user.id, result["session_id"], wager),
                                  f"🎡 **Roulette — mise : {wager} Gold**\nChoisis ton pari avant que la roue ne parte.")
        elif self.game_type == "russian":
            await start_russian_roulette(interaction, result["session_id"], wager)
        elif self.game_type == "slots":
            await play_slots(interaction, result["session_id"], wager)
        elif self.game_type == "horses":
            await play_horse_race(interaction, result["session_id"], wager, int(self.horse_choice or 1), self.horse_odds)


class CasinoMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        specs = [
            ("Black Jack", "🃏", "blackjack", discord.ButtonStyle.primary),
            ("Roulette", "🎡", "roulette", discord.ButtonStyle.primary),
            ("Roulette Russe", "💀", "russian", discord.ButtonStyle.danger),
            ("Machine à sous", "🎰", "slots", discord.ButtonStyle.success),
            ("Courses de chevaux", "🏇", "horses", discord.ButtonStyle.primary),
        ]
        for label, emoji, game, style in specs:
            b = discord.ui.Button(label=label, emoji=emoji, style=style, custom_id=f"legacy:casino:{game}")
            async def cb(interaction: discord.Interaction, game_type=game):
                if not DARK_STORE.has_clandestine_access(interaction.user.id):
                    await eject_from_casino(interaction); return
                if game_type == "horses":
                    await safe_defer(interaction)
                    horse_view = HorseChoiceView(interaction.user.id)
                    await edit_with_asset(interaction, PLACES/"casino_room.png", "casino.png", horse_view, horse_view.content())
                    return
                await interaction.response.send_modal(CasinoBetModal(game_type))
            b.callback = cb
            self.add_item(b)
        leave = discord.ui.Button(label="Quitter la salle", emoji="🚪", style=discord.ButtonStyle.secondary, custom_id="legacy:casino:leave")
        async def leave_cb(interaction: discord.Interaction):
            await safe_defer(interaction)
            await edit_with_asset(interaction, PLACES/"alley_guard.png", "vigile.png", GuardView(interaction.user.id), guard_content(interaction.user.id))
        leave.callback = leave_cb
        self.add_item(leave)


class CasinoResultView(discord.ui.View):
    def __init__(self, owner_id: int, game_type: str, horse_choice: int | None = None):
        super().__init__(timeout=180)
        self.owner_id = int(owner_id)
        replay = discord.ui.Button(label="Rejouer", emoji="🔁", style=discord.ButtonStyle.success)
        menu = discord.ui.Button(label="Menu des jeux", emoji="♠️", style=discord.ButtonStyle.primary)
        async def replay_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Cette table appartient à un autre joueur.", ephemeral=True); return
            if not DARK_STORE.has_clandestine_access(interaction.user.id):
                await eject_from_casino(interaction); return
            if game_type == "horses":
                await safe_defer(interaction)
                horse_view = HorseChoiceView(self.owner_id)
                await edit_with_asset(interaction, PLACES/"casino_room.png", "casino.png", horse_view, horse_view.content())
            else:
                await interaction.response.send_modal(CasinoBetModal(game_type, horse_choice))
        async def menu_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Cette table appartient à un autre joueur.", ephemeral=True); return
            await show_casino_home(interaction)
        replay.callback = replay_cb; menu.callback = menu_cb
        self.add_item(replay); self.add_item(menu)


# ----- BLACK JACK -----
SUITS = ["S", "H", "D", "C"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def bj_new_deck() -> list[dict]:
    deck = [{"rank": rank, "suit": suit} for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck


def bj_total(cards: list[dict]) -> int:
    total = 0
    aces = 0
    for card in cards:
        rank = card["rank"]
        if rank == "A":
            total += 11
            aces += 1
        elif rank in {"J", "Q", "K"}:
            total += 10
        else:
            total += int(rank)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def bj_cards_text(cards: list[dict]) -> str:
    suits = {"S":"♠", "H":"♥", "D":"♦", "C":"♣"}
    return "  ".join(f"{c['rank']}{suits[c['suit']]}" for c in cards)


BLACKJACK_STATES: dict[str, dict] = {}


def blackjack_render_path(session_id: str) -> Path:
    return DATA / "renders" / f"blackjack_{session_id}.png"


async def show_blackjack(interaction: discord.Interaction, session_id: str, *, reveal: bool = False, status: str = "", view: discord.ui.View | None = None):
    st = BLACKJACK_STATES[session_id]
    path = render_blackjack(
        blackjack_render_path(session_id), st["player"], st["dealer"], st["wager"],
        reveal_dealer=reveal, status=status,
    )
    dealer_line = bj_cards_text(st["dealer"]) if reveal else f"{bj_cards_text(st['dealer'][:1])}  🂠"
    text = (
        f"🃏 **BLACK JACK — mise {st['wager']} Gold**\n"
        f"**Toi :** {bj_cards_text(st['player'])} → **{bj_total(st['player'])}**\n"
        f"**Croupier :** {dealer_line}"
    )
    if reveal:
        text += f" → **{bj_total(st['dealer'])}**"
    if status:
        text += f"\n\n{status}"
    await edit_with_asset(interaction, path, "blackjack.png", view or discord.ui.View(), text)


async def start_blackjack(interaction: discord.Interaction, session_id: str, wager: int):
    deck = bj_new_deck()
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]
    BLACKJACK_STATES[session_id] = {
        "owner": interaction.user.id, "wager": wager,
        "player": player, "dealer": dealer, "deck": deck,
    }
    player_natural = bj_total(player) == 21
    dealer_natural = bj_total(dealer) == 21
    if player_natural or dealer_natural:
        await finish_blackjack(interaction, session_id, natural=player_natural, dealer_natural=dealer_natural)
        return
    await show_blackjack(interaction, session_id, view=BlackjackView(interaction.user.id, session_id), status="Tirer une carte ou rester ?")


async def finish_blackjack(interaction: discord.Interaction, session_id: str, natural: bool=False, dealer_natural: bool=False):
    st = BLACKJACK_STATES.get(session_id)
    if not st:
        return
    p = bj_total(st["player"])
    d = bj_total(st["dealer"])
    if not dealer_natural:
        while p <= 21 and d < 17:
            st["dealer"].append(st["deck"].pop())
            d = bj_total(st["dealer"])
    wager = st["wager"]

    if natural and dealer_natural:
        payout, result = wager, f"🤝 Deux Black Jacks : mise de **{wager} Gold** rendue."
    elif dealer_natural:
        payout, result = 0, "🩸 **Black Jack du croupier.** La maison gagne."
    elif p > 21:
        payout, result = 0, "💀 **Tu dépasses 21.** La maison ramasse la mise."
    elif natural and len(st["player"]) == 2:
        payout, result = int(round(wager * 2.5)), f"🏆 **BLACK JACK !** Paiement : **{int(round(wager * 2.5))} Gold**."
    elif d > 21 or p > d:
        payout, result = wager * 2, f"🏆 **Tu gagnes !** Paiement : **{wager * 2} Gold**."
    elif p == d:
        payout, result = wager, f"🤝 **Égalité.** Mise de **{wager} Gold** rendue."
    else:
        payout, result = 0, "🩸 **Le croupier gagne.**"

    settled = CASINO_STORE.settle(session_id, payout)
    actual_payout = int(settled.get("payout", payout))
    if actual_payout > payout:
        result += f"  🎉 **Gold x2 : {actual_payout} Gold crédités.**"
    payout = actual_payout
    if payout:
        CASTLE_STORE.record(interaction.user.id, "gold_earned", payout)
    net_gold = int(payout) - int(wager)
    if net_gold:
        await announce_gold_activity(interaction.guild, interaction.user, net_gold, "Casino — Black Jack")
    wallet = settled.get("wallet", CASINO_STORE.wallet(st["owner"]))
    await show_blackjack(
        interaction, session_id, reveal=True,
        status=f"{result}   •   Solde : {wallet} Gold",
        view=CasinoResultView(st["owner"], "blackjack"),
    )
    BLACKJACK_STATES.pop(session_id, None)


class BlackjackView(discord.ui.View):
    def __init__(self, owner_id: int, session_id: str):
        super().__init__(timeout=180)
        self.owner_id, self.session_id = int(owner_id), session_id
        hit = discord.ui.Button(label="Tirer", emoji="🃏", style=discord.ButtonStyle.success)
        stand = discord.ui.Button(label="Rester", emoji="✋", style=discord.ButtonStyle.primary)

        async def hit_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Ce n'est pas ta partie.", ephemeral=True); return
            if not await casino_access_or_eject(interaction, self.session_id):
                return
            await safe_defer(interaction)
            st = BLACKJACK_STATES.get(self.session_id)
            if not st:
                return
            st["player"].append(st["deck"].pop())
            if bj_total(st["player"]) >= 21:
                await finish_blackjack(interaction, self.session_id)
            else:
                await show_blackjack(interaction, self.session_id, view=self, status="Nouvelle carte distribuée. Tirer ou rester ?")

        async def stand_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Ce n'est pas ta partie.", ephemeral=True); return
            if not await casino_access_or_eject(interaction, self.session_id):
                return
            await safe_defer(interaction)
            await finish_blackjack(interaction, self.session_id)

        hit.callback = hit_cb; stand.callback = stand_cb
        self.add_item(hit); self.add_item(stand)

    async def on_timeout(self):
        CASINO_STORE.refund(self.session_id)
        BLACKJACK_STATES.pop(self.session_id, None)


# ----- ROULETTE -----
class RouletteNumberModal(discord.ui.Modal, title="Numéro de roulette"):
    def __init__(self, owner_id: int, session_id: str, wager: int):
        super().__init__()
        self.owner_id, self.session_id, self.wager = int(owner_id), session_id, wager
        self.number = discord.ui.TextInput(label="Numéro (0 à 36)", placeholder="17", min_length=1, max_length=2)
        self.add_item(self.number)
    async def on_submit(self, interaction: discord.Interaction):
        try: n = int(str(self.number.value).strip())
        except ValueError: n = -1
        if not 0 <= n <= 36:
            await interaction.response.send_message("Choisis un numéro entre 0 et 36.", ephemeral=True); return
        if not await casino_access_or_eject(interaction, self.session_id): return
        await safe_defer(interaction)
        await play_roulette(interaction, self.session_id, self.wager, "number", n)


class RouletteChoiceView(discord.ui.View):
    def __init__(self, owner_id: int, session_id: str, wager: int):
        super().__init__(timeout=120)
        self.owner_id, self.session_id, self.wager = int(owner_id), session_id, wager
        choices = [("Rouge","🔴","red"),("Noir","⚫","black"),("Pair","2️⃣","even"),("Impair","1️⃣","odd"),("1-18","⬇️","low"),("19-36","⬆️","high")]
        for label,emoji,key in choices:
            b=discord.ui.Button(label=label,emoji=emoji,style=discord.ButtonStyle.secondary)
            async def cb(interaction: discord.Interaction, k=key):
                if interaction.user.id != self.owner_id:
                    await interaction.response.send_message("Ce n'est pas ta mise.", ephemeral=True); return
                if not await casino_access_or_eject(interaction, self.session_id): return
                await safe_defer(interaction); await play_roulette(interaction, self.session_id, self.wager, k, None)
            b.callback=cb; self.add_item(b)
        number=discord.ui.Button(label="Numéro exact",emoji="🎯",style=discord.ButtonStyle.primary)
        async def num_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Ce n'est pas ta mise.", ephemeral=True); return
            await interaction.response.send_modal(RouletteNumberModal(self.owner_id,self.session_id,self.wager))
        number.callback=num_cb; self.add_item(number)
        cancel=discord.ui.Button(label="Annuler la mise",emoji="↩️",style=discord.ButtonStyle.secondary)
        async def cancel_cb(interaction: discord.Interaction):
            if interaction.user.id != self.owner_id:
                await interaction.response.send_message("Ce n'est pas ta mise.", ephemeral=True); return
            CASINO_STORE.refund(self.session_id)
            await show_casino_home(interaction)
        cancel.callback=cancel_cb; self.add_item(cancel)

    async def on_timeout(self):
        CASINO_STORE.refund(self.session_id)


def roulette_bet_label(bet_type: str, number_choice: int | None) -> str:
    if bet_type == "number":
        return f"NUMÉRO {number_choice}"
    return {"red":"ROUGE","black":"NOIR","even":"PAIR","odd":"IMPAIR","low":"1–18","high":"19–36"}[bet_type]


async def play_roulette(interaction: discord.Interaction, session_id: str, wager: int, bet_type: str, number_choice: int|None):
    number, color = roulette_spin()
    target_index = EUROPEAN_WHEEL.index(number)
    steps = [8, 7, 6, 5, 4, 3, 2, 1, 1]
    start_index = (target_index - sum(steps)) % len(EUROPEAN_WHEEL)
    idx = start_index
    label = roulette_bet_label(bet_type, number_choice)
    path = DATA / "renders" / f"roulette_{session_id}.png"

    for frame_no, step in enumerate(steps):
        if not DARK_STORE.has_clandestine_access(interaction.user.id):
            CASINO_STORE.refund(session_id)
            await edit_with_asset(interaction, PLACES/"alley_guard.png", "vigile.png", GuardView(), "🐻 **Minuit. Le Vigile te met dehors et ta mise en cours est rendue.**")
            return
        idx = (idx + step) % len(EUROPEAN_WHEEL)
        render_roulette_strip(path, idx, label, wager, final=False)
        await edit_with_asset(interaction, path, "roulette.png", discord.ui.View(), f"🎡 **ROULETTE — {label}**\nLa roue tourne... les numéros défilent.")
        await asyncio.sleep(0.22 + frame_no * 0.055)

    # verrouillage exact sur le résultat tiré
    render_roulette_strip(path, target_index, label, wager, final=True)
    won=False; mult=0
    if bet_type=="red": won=color=="red"; mult=2
    elif bet_type=="black": won=color=="black"; mult=2
    elif bet_type=="even": won=number!=0 and number%2==0; mult=2
    elif bet_type=="odd": won=number%2==1; mult=2
    elif bet_type=="low": won=1<=number<=18; mult=2
    elif bet_type=="high": won=19<=number<=36; mult=2
    elif bet_type=="number": won=number==number_choice; mult=36
    payout=wager*mult if won else 0
    settled=CASINO_STORE.settle(session_id,payout)
    payout=int(settled.get("payout",payout))
    if payout: CASTLE_STORE.record(interaction.user.id, "gold_earned", payout)
    net_gold=int(payout)-int(wager)
    if net_gold: await announce_gold_activity(interaction.guild, interaction.user, net_gold, f"Casino — Roulette ({label})")
    icon="🟢" if color=="green" else "🔴" if color=="red" else "⚫"
    result=f"🏆 **Gagné : {payout} Gold**" if won else "💀 **Perdu.**"
    await edit_with_asset(
        interaction, path, "roulette.png", CasinoResultView(interaction.user.id,"roulette"),
        f"🎡 **ROULETTE — {label}**\nLa bille s'arrête sur **{icon} {number}**.\n\n{result}\n💰 Solde : **{settled.get('wallet',0)} Gold**"
    )


# ----- ROULETTE RUSSE (version purement fictive) -----
RUSSIAN_STATES: dict[str,dict]={}

async def start_russian_roulette(interaction: discord.Interaction, session_id: str, wager: int):
    RUSSIAN_STATES[session_id]={"owner":interaction.user.id,"wager":wager,"danger":random.randint(1,6),"step":0,"turn":"player"}
    await edit_with_asset(interaction, PLACES/"casino_room.png","casino.png",RussianRouletteView(interaction.user.id,session_id),
                          f"💀 **ROULETTE RUSSE — version fictive de Altherya**\nMise : **{wager} Gold**\n\nFace à toi, un hyène mafieux sourit. Le tour est représenté par un barillet de jeu à **6 cases**.\nÀ toi de tenter ta chance.")

class RussianRouletteView(discord.ui.View):
    def __init__(self,owner_id:int,session_id:str):
        super().__init__(timeout=120); self.owner_id=int(owner_id); self.session_id=session_id
        go=discord.ui.Button(label="Tenter",emoji="💀",style=discord.ButtonStyle.danger)
        async def go_cb(interaction: discord.Interaction):
            if interaction.user.id!=self.owner_id:
                await interaction.response.send_message("Ce n'est pas ta partie.",ephemeral=True); return
            if not await casino_access_or_eject(interaction, self.session_id): return
            await safe_defer(interaction)
            st=RUSSIAN_STATES.get(self.session_id)
            if not st:return
            st["step"]+=1
            await edit_with_asset(interaction,PLACES/"casino_room.png","casino.png",discord.ui.View(),"💀 **ROULETTE RUSSE**\n\nLe barillet de jeu tourne...\n`◌ ◌ ◌ ◌ ◌ ◌`")
            await asyncio.sleep(0.8)
            if st["step"]==st["danger"]:
                settled=CASINO_STORE.settle(self.session_id,0); RUSSIAN_STATES.pop(self.session_id,None)
                await announce_gold_activity(interaction.guild, interaction.user, -int(st["wager"]), "Casino — Roulette Russe")
                await edit_with_asset(interaction,PLACES/"casino_room.png","casino.png",CasinoResultView(self.owner_id,"russian"),
                                      f"💥 **BANG — tu perds la manche.**\nLe mafieux récupère ta mise.\n💰 Solde : **{settled.get('wallet',0)} Gold**")
                return
            await edit_with_asset(interaction,PLACES/"casino_room.png","casino.png",discord.ui.View(),"😈 **CLIC — tu restes dans la partie.**\nLe hyène prend son tour...")
            await asyncio.sleep(1.0)
            if not DARK_STORE.has_clandestine_access(interaction.user.id):
                CASINO_STORE.refund(self.session_id); RUSSIAN_STATES.pop(self.session_id,None)
                await edit_with_asset(interaction,PLACES/"alley_guard.png","vigile.png",GuardView(),"🐻 **Minuit. Le Vigile interrompt la partie, rend ta mise et te met dehors.**")
                return
            st["step"]+=1
            if st["step"]==st["danger"]:
                payout=st["wager"]*2; settled=CASINO_STORE.settle(self.session_id,payout); payout=int(settled.get("payout",payout)); CASTLE_STORE.record(interaction.user.id, "gold_earned", payout); RUSSIAN_STATES.pop(self.session_id,None)
                net_gold=int(payout)-int(st["wager"])
                if net_gold: await announce_gold_activity(interaction.guild, interaction.user, net_gold, "Casino — Roulette Russe")
                await edit_with_asset(interaction,PLACES/"casino_room.png","casino.png",CasinoResultView(self.owner_id,"russian"),
                                      f"💥 **Le mafieux tombe sur la mauvaise case !**\n🏆 Tu remportes **{payout} Gold**.\n💰 Solde : **{settled.get('wallet',0)} Gold**")
                return
            await edit_with_asset(interaction,PLACES/"casino_room.png","casino.png",self,f"😏 **Le mafieux s'en sort.**\n\nCases déjà jouées : **{st['step']}/6**\nÀ toi de retenter.")
        back=discord.ui.Button(label="Retour aux jeux",emoji="↩️",style=discord.ButtonStyle.secondary)
        async def back_cb(interaction:discord.Interaction):
            if interaction.user.id!=self.owner_id: await interaction.response.send_message("Ce n'est pas ta partie.",ephemeral=True); return
            CASINO_STORE.refund(self.session_id); RUSSIAN_STATES.pop(self.session_id,None)
            await safe_defer(interaction); await edit_with_asset(interaction,PLACES/"casino_room.png","casino.png",CasinoMainView(),casino_home_content(interaction.user.id))
        go.callback=go_cb; back.callback=back_cb; self.add_item(go); self.add_item(back)

    async def on_timeout(self):
        CASINO_STORE.refund(self.session_id)
        RUSSIAN_STATES.pop(self.session_id, None)


# ----- MACHINE À SOUS -----
def slot_render_path(session_id: str) -> Path:
    return DATA / "renders" / f"slots_{session_id}.png"


async def play_slots(interaction: discord.Interaction, session_id: str, wager: int):
    path = slot_render_path(session_id)
    # Une vraie animation visuelle : les trois rouleaux tournent puis ralentissent.
    delays = [0.16, 0.18, 0.21, 0.25, 0.30, 0.38, 0.48]
    for delay in delays:
        if not DARK_STORE.has_clandestine_access(interaction.user.id):
            CASINO_STORE.refund(session_id)
            await edit_with_asset(interaction, PLACES/"alley_guard.png", "vigile.png", GuardView(), "🐻 **Minuit. Le Vigile te met dehors et ta mise en cours est rendue.**")
            return
        fake = random.choices(SLOT_SYMBOLS, k=3)
        render_slot_machine(path, fake, wager, spinning=True)
        await edit_with_asset(interaction, path, "slots.png", discord.ui.View(), "🎰 **MACHINE À SOUS — les rouleaux tournent...**")
        await asyncio.sleep(delay)

    reels = draw_slot(); mult = slot_multiplier(reels); payout = wager * mult
    settled = CASINO_STORE.settle(session_id, payout)
    payout = int(settled.get("payout", payout))
    if payout: CASTLE_STORE.record(interaction.user.id, "gold_earned", payout)
    net_gold=int(payout)-int(wager)
    if net_gold: await announce_gold_activity(interaction.guild, interaction.user, net_gold, "Casino — Machine à sous")
    if mult > 1: result = f"JACKPOT — {payout} Gold crédités !"
    elif mult == 1: result = f"Deux 7 — mise de {wager} Gold rendue."
    else: result = "Aucune combinaison gagnante."
    render_slot_machine(path, reels, wager, spinning=False, status=result)
    await edit_with_asset(interaction, path, "slots.png", CasinoResultView(interaction.user.id,"slots"),
                          f"🎰 **MACHINE À SOUS**\n{result}\n💰 Solde : **{settled.get('wallet',0)} Gold**")


# ----- COURSES DE CHEVAUX -----
HORSES=[("Éclair","🐎"),("Cendre","🐴"),("Furie","🐎"),("Minuit","🐴")]


def _odd(a: float, b: float) -> float:
    return round(random.uniform(a, b), 1)


def generate_horse_odds() -> list[float]:
    # 1 favori, 2 intermédiaires, 1 outsider, attribués à des chevaux différents à chaque course.
    tiers = [_odd(1.5, 2.0), _odd(2.1, 2.5), _odd(2.1, 2.5), _odd(2.6, 3.0)]
    random.shuffle(tiers)
    return tiers


def horse_probability_weights(odds: list[float]) -> list[float]:
    # Les probabilités suivent les cotes sans rendre le favori écrasant.
    # L'inverse des cotes donne généralement ~30-35 % au favori, ~20-27 % aux mids, ~15-20 % à l'outsider.
    return [1.0 / max(1.01, float(o)) for o in odds]


class HorseChoiceView(discord.ui.View):
    def __init__(self,owner_id:int, odds: list[float] | None = None):
        super().__init__(timeout=120)
        self.owner_id=int(owner_id)
        self.odds = list(odds) if odds else generate_horse_odds()
        for idx,(name,emoji) in enumerate(HORSES,1):
            cote = self.odds[idx-1]
            b=discord.ui.Button(label=f"{idx}. {name} • x{cote:.1f}",emoji=emoji,style=discord.ButtonStyle.primary)
            async def cb(interaction:discord.Interaction,horse=idx):
                if interaction.user.id!=self.owner_id:
                    await interaction.response.send_message("Choisis sur ta propre table.",ephemeral=True); return
                if not DARK_STORE.has_clandestine_access(interaction.user.id): await eject_from_casino(interaction); return
                await interaction.response.send_modal(CasinoBetModal("horses",horse,self.odds))
            b.callback=cb; self.add_item(b)
        back=discord.ui.Button(label="Menu",emoji="↩️",style=discord.ButtonStyle.secondary)
        async def back_cb(interaction:discord.Interaction): await show_casino_home(interaction)
        back.callback=back_cb; self.add_item(back)

    def content(self) -> str:
        rows=[]
        for i,(name,emoji) in enumerate(HORSES):
            odd=self.odds[i]
            if odd <= 2.0: tag="⭐ Favori"
            elif odd <= 2.5: tag="⚖️ Intermédiaire"
            else: tag="🔥 Outsider"
            rows.append(f"{emoji} **{name}** — cote **x{odd:.1f}** · {tag}")
        return (
            "🏇 **COURSES DE CHEVAUX — COTES DU JOUR**\n"
            "Les cotes sont redistribuées aléatoirement à chaque nouvelle course.\n\n" +
            "\n".join(rows) +
            "\n\nChoisis ton cheval, puis indique ta mise. Le paiement total = **mise × cote**."
        )


def race_frame(pos:list[int],finish:int=24, odds:list[float]|None=None)->str:
    lines=[]
    for i,p in enumerate(pos):
        track=["·"]*finish
        track[min(p,finish-1)]=HORSES[i][1]
        cote=f" x{odds[i]:.1f}" if odds else ""
        lines.append(f"**{i+1} {HORSES[i][0]:<7}{cote}** `|{''.join(track)}|🏁`")
    return "\n".join(lines)


async def play_horse_race(interaction:discord.Interaction,session_id:str,wager:int,choice:int,odds:list[float]|None=None):
    odds = list(odds) if odds and len(odds)==4 else generate_horse_odds()
    weights = horse_probability_weights(odds)
    winner = random.choices(range(4), weights=weights, k=1)[0]
    pos=[0,0,0,0]; finish=24
    chosen_name=HORSES[choice-1][0]
    chosen_odd=odds[choice-1]
    names=[h[0] for h in HORSES]
    path=DATA / "renders" / f"horses_{session_id}.png"

    render_horse_race(path,pos,odds,names,wager,choice,finish=finish)
    await edit_with_asset(interaction,path,"horses.png",discord.ui.View(),
                          f"🏇 **COURSE — {wager} Gold sur {chosen_name} (x{chosen_odd:.1f})**\nLes chevaux se placent dans les stalles...")
    await asyncio.sleep(0.8)

    frame=0
    while pos[winner] < finish:
        if not DARK_STORE.has_clandestine_access(interaction.user.id):
            CASINO_STORE.refund(session_id)
            await edit_with_asset(interaction, PLACES/"alley_guard.png", "vigile.png", GuardView(), "🐻 **Minuit. Le Vigile arrête la course pour toi, rend ta mise et te met dehors.**")
            return
        frame += 1
        order=list(range(4)); random.shuffle(order)
        for i in order:
            # Le résultat reste pondéré par les cotes, mais l'animation laisse réellement
            # les quatre chevaux se battre et changer de leader.
            advance=random.randint(1,3)
            if random.random() < 0.35: advance += 1
            if i == winner and frame >= 4 and random.random() < 0.45: advance += 1
            pos[i]=min(finish, pos[i]+advance)
            if i != winner and pos[i] >= finish:
                pos[i]=finish-1
        if frame >= 6 and pos[winner] >= finish-2:
            pos[winner]=finish
        render_horse_race(path,pos,odds,names,wager,choice,finish=finish)
        await edit_with_asset(interaction,path,"horses.png",discord.ui.View(),
                              f"🏇 **COURSE EN DIRECT** — Mise : **{wager} Gold sur {chosen_name} x{chosen_odd:.1f}**")
        await asyncio.sleep(0.55)

    won=(winner==choice-1)
    payout=int(round(wager*chosen_odd)) if won else 0
    settled=CASINO_STORE.settle(session_id,payout)
    payout=int(settled.get("payout",payout))
    if payout: CASTLE_STORE.record(interaction.user.id, "gold_earned", payout)
    net_gold=int(payout)-int(wager)
    if net_gold: await announce_gold_activity(interaction.guild, interaction.user, net_gold, f"Casino — Course de chevaux ({chosen_name} x{chosen_odd:.1f})")
    if won:
        net=max(0,payout-wager)
        result=f"🏆 **{HORSES[winner][0]} gagne !** Paiement **{payout} Gold** (gain net +{net})."
    else:
        result=f"🏁 **{HORSES[winner][0]} franchit la ligne en premier.** Ta mise est perdue."
    render_horse_race(path,pos,odds,names,wager,choice,finish=finish,final=True,winner=winner)
    await edit_with_asset(interaction,path,"horses.png",discord.ui.View(),f"🏇 **ARRIVÉE !**\n{result}\n💰 Solde : **{settled.get('wallet',0)} Gold**")
    await asyncio.sleep(2.5)
    if DARK_STORE.has_clandestine_access(interaction.user.id):
        await edit_with_asset(interaction,PLACES/"casino_room.png","casino.png",CasinoMainView(),casino_home_content(interaction.user.id))
    else:
        await edit_with_asset(interaction,PLACES/"alley_guard.png","vigile.png",GuardView(),"🐻 **Le Vigile te met dehors : ton accès a expiré.**")

class BannedAlleyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        hub = discord.ui.Button(label="Retour à la place", emoji="🏙️", style=discord.ButtonStyle.primary,
                                custom_id="legacy:alley:banned:hub")
        async def hub_cb(interaction: discord.Interaction):
            await return_to_hub(interaction)
        hub.callback = hub_cb
        self.add_item(hub)


def castle_home_content(user_id:int):
    p=CASTLE_STORE.profile(user_id); lvl,cur,need=level_from_xp(p['xp']); b=ECONOMY.get_balance(user_id)
    return (f"🏰 **LE CHÂTEAU DE LEGACY**\n"
            f"Le cœur du royaume : prestige, progression et récompenses.\n\n"
            f"👤 Niveau **{lvl}** • XP **{cur}/{need}**\n"
            f"💰 Fortune personnelle : **{b.wallet+b.bank:,} Gold**".replace(',', ' '))

async def castle_member(guild, uid:int):
    if guild is None: return None
    m=guild.get_member(uid)
    if m: return m
    try: return await guild.fetch_member(uid)
    except Exception: return None

class CastleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        specs=[('Podium','🏆','podium'),('Récompense journalière','🎁','daily')]
        for label,emoji,key in specs:
            b=discord.ui.Button(label=label,emoji=emoji,style=discord.ButtonStyle.primary,custom_id=f'legacy:castle:{key}')
            async def cb(interaction:discord.Interaction,k=key):
                await safe_defer(interaction)
                if k=='podium': await show_castle_podium(interaction)
                else: await show_castle_daily(interaction)
            b.callback=cb; self.add_item(b)
        back=discord.ui.Button(label='Retour en ville',emoji='↩️',style=discord.ButtonStyle.secondary,custom_id='legacy:castle:back')
        back.callback=return_to_hub; self.add_item(back)

class CastleBackView(discord.ui.View):
    def __init__(self, extra=None):
        super().__init__(timeout=None)
        if extra: self.add_item(extra)
        b=discord.ui.Button(label='Retour au Château',emoji='🏰',style=discord.ButtonStyle.secondary,custom_id='legacy:castle:return')
        async def cb(i):
            await safe_defer(i); await edit_with_asset(i,PLACES/'castle.png','castle.png',CastleView(),castle_home_content(i.user.id))
        b.callback=cb; self.add_item(b)

class PodiumView(CastleBackView):
    def __init__(self):
        refresh=discord.ui.Button(label='Actualiser',emoji='🔄',style=discord.ButtonStyle.primary,custom_id='legacy:castle:podium:refresh')
        async def r(i): await safe_defer(i); await show_castle_podium(i)
        refresh.callback=r; super().__init__(refresh)

def _podium_cell(text: str, width: int) -> str:
    # Le podium doit rester compact : Discord casse rapidement les grands blocs monospace.
    text = str(text).replace("`", "'").replace("\n", " ").strip()
    if len(text) > width:
        text = text[:max(1, width - 1)] + "…"
    return text.center(width)


def _podium_text(top3):
    """Podium texte compact et stable : 2e à gauche, 1er au centre, 3e à droite.

    Les noms/fortunes sont volontairement limités à 11 caractères par colonne afin
    que Discord ne replie jamais le dessin et ne décale plus les marches.
    """
    slots = {1: ("—", 0), 2: ("—", 0), 3: ("—", 0)}
    for pos, name, total in top3:
        slots[int(pos)] = (str(name), int(total))

    n1, g1 = slots[1]
    n2, g2 = slots[2]
    n3, g3 = slots[3]
    w = 11
    gap = "  "

    def row(a="", b="", c=""):
        return f"{_podium_cell(a,w)}{gap}{_podium_cell(b,w)}{gap}{_podium_cell(c,w)}"

    def gold(v):
        # Format court pour préserver la géométrie du podium.
        if v >= 1_000_000_000:
            return f"{v/1_000_000_000:.1f}Md G".replace(".0", "")
        if v >= 1_000_000:
            return f"{v/1_000_000:.1f}M G".replace(".0", "")
        if v >= 1_000:
            return f"{v/1_000:.1f}k G".replace(".0", "")
        return f"{v} G"

    lines = [
        "```",
        row(n2, n1, n3),
        row(gold(g2), gold(g1), gold(g3)),
        row("", "┌─────────┐", ""),
        row("", "│    1    │", ""),
        row("┌─────────┐", "│         │", "┌─────────┐"),
        row("│    2    │", "│         │", "│    3    │"),
        row("│         │", "│         │", "│         │"),
        row("└─────────┘", "└─────────┘", "└─────────┘"),
        "```",
    ]
    return "\n".join(lines)

async def show_castle_podium(interaction):
    rows=CASTLE_STORE.leaderboard(3)
    top3=[]
    avatars={}
    if rows:
        for idx,row in enumerate(rows, start=1):
            m=await castle_member(interaction.guild,int(row['user_id']))
            name=m.display_name if m else 'Joueur inconnu'
            top3.append((idx,name,int(row['total'])))
            if m is not None:
                avatars[idx]=str(m.display_avatar.url)

    children=[discord.ui.TextDisplay('# 🏆 HALL OF FAME — ALTHÉRYA')]
    children.append(discord.ui.TextDisplay('*Les trois plus grandes fortunes du Royaume de IV*'))

    # Avec 3 médias, Discord affiche le 2e élément en grand à gauche,
    # le 1er en petit en haut à droite et le 3e en petit en bas à droite.
    # Ordre voulu à l'écran : grand #1, petit haut #2, petit bas #3.
    if avatars:
        gallery=discord.ui.MediaGallery()
        for pos in (2,1,3):
            if pos in avatars:
                gallery.add_item(media=avatars[pos],description=f'#{pos} du classement Altherya')
        children.append(gallery)

    children.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))
    if top3:
        children.append(discord.ui.TextDisplay(_podium_text(top3)))
        children.append(discord.ui.TextDisplay('*Fortune = Gold en poche + Gold en banque.*'))
    else:
        children.append(discord.ui.TextDisplay('*Aucun joueur classé pour le moment.*'))

    children.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))
    legacy=PodiumView()
    buttons=[item for item in legacy.children if isinstance(item,discord.ui.Button)]
    for button in buttons:
        children.append(discord.ui.Section(
            f"### {str(button.emoji or '◆')} {button.label}\n{_v2_action_description(button)}",
            accessory=button
        ))
    view=discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(*children,accent_colour=0xD6A84B))
    await interaction.edit_original_response(content=None,attachments=[],embeds=[],view=view)


async def show_player_profile(interaction):
    uid=interaction.user.id
    p=CASTLE_STORE.profile(uid); lvl,cur,need=level_from_xp(p['xp']); b=ECONOMY.get_balance(uid)
    arena=ARENA_STORE.progress(uid)
    tavern=TAVERN_STORE.tavern_reputation(uid)
    criminal=DARK_STORE.criminal_reputation(uid)
    casino=CASINO_STORE.loyalty(uid)
    achievements=len(ACHIEVEMENT_STORE.unlocked_keys(uid))
    chapters=sum(1 for chapter in range(1,31) if STORY_STORE.is_unlocked(uid,1,chapter))
    last_chapter=STORY_STORE.last_read_chapter(uid,1)
    e=discord.Embed(
        title=f'📜 Fiche de {interaction.user.display_name}',
        description=f'⭐ **Niveau {lvl}** • **{cur}/{need} XP**\nVue complète de ta progression dans Altherya.'
    )
    e.set_thumbnail(url=interaction.user.display_avatar.url)
    e.add_field(name='💰 Fortune',value=f'Poche : **{b.wallet:,}**\nBanque : **{b.bank:,}**\nTotal : **{b.wallet+b.bank:,} Gold**'.replace(',',' '),inline=True)
    e.add_field(name='⚔️ Arène',value=f'Rang : **{arena["rank"]}**\nCote : **{arena["rating"]}**\nChampion : **Niv. {arena["champion_level"]}/10**\nVictoires Champion : **{arena["champion_wins"]}**',inline=True)
    e.add_field(name='🏰 Activité',value=f'Combats : **{p["combats"]}** ({p["wins"]} V / {p["losses"]} D)\nExpéditions : **{p["expeditions"]}**\nJeux Casino : **{p["casino_games"]}**\nQuêtes terminées : **{p["quests_completed"]}**',inline=True)
    e.add_field(name='🍺 Réputation Taverne',value=f'**{tavern["label"]}**\n{tavern["drinks"]} consommation(s)',inline=True)
    e.add_field(name='🐺 Réputation Ruelle',value=f'**{criminal["label"]}**\n{criminal["successes"]} méfait(s) réussi(s)',inline=True)
    e.add_field(name='🎰 Fidélité Casino',value=f'**{casino["label"]}**\n{casino["wins"]} victoire(s)',inline=True)
    e.add_field(name='📖 Chroniques',value=f'Chapitres débloqués : **{chapters}/30**\nDernier chapitre consulté : **{last_chapter}**',inline=True)
    e.add_field(name='🏆 Succès',value=f'**{achievements}** succès débloqué(s)',inline=True)
    e.set_footer(text='Altherya • Fiche joueur • Informations mises à jour à chaque ouverture')
    await interaction.edit_original_response(content='📜 **FICHE JOUEUR — PANNEAU CENTRAL**',attachments=[],embeds=[e],view=CentralBoardBackView())

# Compatibilité interne : les anciens appels éventuels affichent désormais la fiche du panneau central.
show_castle_profile = show_player_profile

class CentralBoardView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        quests=discord.ui.Button(label='Quêtes quotidiennes',emoji='📋',style=discord.ButtonStyle.primary,custom_id='legacy:hub:board:quests')
        profile=discord.ui.Button(label='Fiche joueur',emoji='📜',style=discord.ButtonStyle.primary,custom_id='legacy:hub:board:profile')
        close=discord.ui.Button(label='Retour à la place',emoji='🏙️',style=discord.ButtonStyle.secondary,custom_id='legacy:hub:board:close')
        async def q(i): await safe_defer(i); await show_castle_quests(i)
        async def f(i): await safe_defer(i); await show_player_profile(i)
        quests.callback=q; profile.callback=f; close.callback=return_to_hub
        self.add_item(quests); self.add_item(profile); self.add_item(close)

class CentralBoardBackView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        back=discord.ui.Button(label='Retour au panneau',emoji='📋',style=discord.ButtonStyle.secondary,custom_id='legacy:hub:board:back')
        async def cb(i): await safe_defer(i); await show_central_board(i)
        back.callback=cb; self.add_item(back)

async def show_central_board(interaction):
    p=CASTLE_STORE.profile(interaction.user.id); lvl,cur,need=level_from_xp(p['xp'])
    txt=(
        '📋 **PANNEAU CENTRAL DE LEGACY**\n\n'
        'Toutes tes informations personnelles sont regroupées ici.\n'
        f'⭐ Niveau actuel : **{lvl}** • XP **{cur}/{need}**\n\n'
        '📋 **Quêtes quotidiennes** — Consulte tes 6 objectifs reliés à Ashkar, la Forge, l’Arène, la Taverne et aux activités du monde.\n'
        '📜 **Fiche joueur** — Consulte ta progression complète, tes réputations, ta fortune et tes statistiques.'
    )
    await interaction.edit_original_response(content=txt,attachments=[],embeds=[],view=CentralBoardView())

class QuestView(discord.ui.View):
    def __init__(self,ready=False,claimed=False):
        super().__init__(timeout=None)
        label='Récompense déjà récupérée' if claimed else 'Réclamer la récompense globale'
        claim=discord.ui.Button(label=label,emoji='🎁',style=discord.ButtonStyle.success,disabled=(not ready or claimed),custom_id='legacy:hub:quests:claim')
        async def cb(i):
            await safe_defer(i)
            ok,g,x,status=CASTLE_STORE.claim_quests(i.user.id)
            if ok:
                await announce_gold_activity(i.guild, i.user, g, "Récompense globale des 6 quêtes quotidiennes")
                msg=f'🎉 **6/6 quêtes terminées !** Récompense globale : **+{g} Gold** et **+{x} XP**.'
            elif status=='claimed':
                msg='🔒 La récompense globale a déjà été récupérée aujourd’hui.'
            else:
                msg='⏳ Les **6 quêtes** doivent être terminées avant de recevoir la moindre récompense.'
            await show_castle_quests(i,msg)
            if ok:
                await show_pending_levelups(i, i.user.id)
        claim.callback=cb; self.add_item(claim)
        close=discord.ui.Button(label='Retour au panneau',emoji='📋',style=discord.ButtonStyle.secondary,custom_id='legacy:hub:quests:close')
        async def back_board(i):
            await safe_defer(i); await show_central_board(i)
        close.callback=back_board; self.add_item(close)

async def show_castle_quests(interaction,notice=''):
    qs,meta=CASTLE_STORE.quests(interaction.user.id); lines=[]
    for q in qs:
        icon='✅' if q['progress']>=q['target'] else '⏳'
        lines.append(f"{icon} **{q['label']}** — **{q['progress']}/{q['target']}**")
    completed=sum(1 for q in qs if q['progress']>=q['target'])
    claimed=all(q['claimed'] for q in qs)
    ready=(completed==len(qs)) and not claimed
    status=('🎁 **Récompense disponible !**' if ready else ('🔒 **Récompense déjà récupérée aujourd’hui.**' if claimed else f'🔒 **{completed}/6 terminées — aucune récompense avant 6/6.**'))
    txt=(
        '📋 **PANNEAU DES QUÊTES — PLACE CENTRALE**\n'
        f'🐺 Difficulté adaptée à ta réputation : **{meta["label"]}**.\n'
        'Réinitialisation à **00h00, heure du serveur**.\n\n'
        + '\n\n'.join(lines)
        + f'\n\n🏆 **Récompense globale 6/6 : {meta["gold"]} Gold + {meta["xp"]} XP**\n'
        + status
    )
    if notice: txt+='\n\n'+notice
    await interaction.edit_original_response(content=txt,attachments=[],embeds=[],view=QuestView(ready,claimed))

class DailyView(CastleBackView):
    def __init__(self,available=True):
        claim=discord.ui.Button(label='Récupérer ma récompense',emoji='🎁',style=discord.ButtonStyle.success,disabled=not available,custom_id='legacy:castle:daily:claim')
        async def cb(i):
            await safe_defer(i); ok,g=CASTLE_STORE.claim_daily(i.user.id)
            if ok:
                await announce_gold_activity(i.guild, i.user, g, "Récompense journalière du Château")
                await show_castle_daily(i,f'🎉 **+{g} Gold** et **+{DAILY_XP} XP** ajoutés à ton compte.')
                await show_pending_levelups(i, i.user.id)
            else: await show_castle_daily(i,'⏳ Récompense déjà récupérée aujourd’hui.')
        claim.callback=cb; super().__init__(claim)

async def show_castle_daily(interaction,notice=''):
    available=CASTLE_STORE.daily_available(interaction.user.id)
    txt=f'🎁 **RÉCOMPENSE JOURNALIÈRE**\n\nRécompense du jour : **{DAILY_REWARD} Gold + {DAILY_XP} XP**\nDisponible **une fois par jour**, remise à zéro à 00h00 heure du serveur.\n\n'+('🟢 **Disponible maintenant.**' if available else '🔒 **Déjà récupérée aujourd’hui.**')
    if notice: txt+='\n\n'+notice
    await edit_v2_surface(interaction,path=PLACES/'castle.png',filename='castle.png',content=txt,view=DailyView(available),title='🎁 RÉCOMPENSE JOURNALIÈRE')

class PlaceView(discord.ui.View):
    def __init__(self, place_key: str):
        super().__init__(timeout=None)
        self.place_key = place_key
        back = discord.ui.Button(label="Retour à la place", emoji="↩️", style=discord.ButtonStyle.primary,
                                 custom_id=f"legacy:place:{place_key}:back")
        async def go_back(interaction: discord.Interaction):
            await return_to_hub(interaction)
        back.callback = go_back
        self.add_item(back)



# ============================================================
# V2.15 — ADAPTATEUR GLOBAL COMPONENTS V2
# Transforme les surfaces historiques texte/image/boutons en vrais LayoutView V2.
# Aucun Select n'est rendu : les choix sont exposés par boutons/pagination/modals.
# ============================================================
def _v2_action_description(button: discord.ui.Button) -> str:
    """Micro-description immersive utilisée par toutes les cartes d'action V2."""
    cid = str(getattr(button, "custom_id", "") or "").lower()
    label = str(getattr(button, "label", "Action") or "Action").lower()
    key = f"{cid} {label}"
    rules = [
        (("retour", "back", "quitter", "leave"), "Reviens à l’écran précédent sans perdre ta progression."),
        (("acheter", "buy", "boutique", "marché"), "Consulte les offres disponibles et prépare ton équipement."),
        (("vendre", "sell", "revente"), "Transforme les ressources de ton inventaire en Gold."),
        (("banque", "coffre", "déposer", "retirer"), "Gère tes Gold et sécurise ta fortune."),
        (("forge", "amélior", "upgrade"), "Renforce ton équipement et prépare les prochaines épreuves."),
        (("combat", "combatt", "arène", "défi", "attaqu"), "Prépare-toi au combat et choisis ta prochaine action."),
        (("boire", "boisson", "bar", "comptoir"), "Approche du comptoir et découvre ce que sert le tavernier."),
        (("jeu", "jouer", "table"), "Tente ta chance face aux habitués de la taverne."),
        (("troubadour", "histoire", "story"), "Écoute les récits, rumeurs et histoires du royaume."),
        (("quête", "mission", "contrat", "annonce"), "Consulte les objectifs disponibles et leurs récompenses."),
        (("explor", "forêt", "vorak", "voyager", "destination"), "Pars vers cette destination et découvre ses dangers."),
        (("inventaire", "équipement", "profil", "fiche"), "Consulte tes possessions, tes statistiques et ta progression."),
        (("récompense", "claim", "récupérer"), "Récupère la récompense disponible pour ton aventurier."),
        (("confirmer", "valider", "continuer"), "Confirme ton choix et poursuis l’aventure."),
    ]
    for needles, desc in rules:
        if any(n in key for n in needles):
            return desc
    return "Interagis avec ce lieu pour poursuivre ton aventure."

def _legacy_view_to_v2(view: discord.ui.View, *, content: str | None = None, filename: str | None = None, title: str | None = None, accent: int = 0xB67A2A) -> discord.ui.LayoutView:
    """Convertit une ancienne vue en écran RPG Components V2 à cartes d'action.

    Chaque action devient une Section native avec son vrai bouton Discord en
    accessoire. Cela donne le rendu « image + cartes interactives » sur tous
    les lieux et sous-écrans sans modifier les mécaniques existantes.
    """
    out = discord.ui.LayoutView(timeout=getattr(view, 'timeout', 1800))
    children = []
    if title:
        children.append(discord.ui.TextDisplay(f"# {title}"))
    if filename:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=f"attachment://{filename}", description=title or "Altherya")
        children.append(gallery)
    if content:
        children.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
        children.append(discord.ui.TextDisplay(content))

    buttons = [item for item in list(getattr(view, 'children', [])) if isinstance(item, discord.ui.Button)]
    if buttons:
        children.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))
        children.append(discord.ui.TextDisplay("## ⚜️ Actions disponibles"))
        for index, button in enumerate(buttons):
            emoji = str(getattr(button, 'emoji', '') or '◆')
            label = str(getattr(button, 'label', None) or 'Action')
            description = _v2_action_description(button)
            children.append(discord.ui.Section(f"### {emoji} {label}\n{description}", accessory=button))
            if index != len(buttons) - 1:
                children.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.small))
    else:
        children.append(discord.ui.Separator(spacing=discord.SeparatorSpacing.large))
        children.append(discord.ui.TextDisplay("*Aucune action disponible sur cet écran.*"))

    out.add_item(discord.ui.Container(*children, accent_colour=accent))
    return out

def _place_title_from_filename(filename: str) -> str:
    labels={
        'taverne.png':'🍺 TAVERNE D’ALTHERYA','barman.png':'🍺 COMPTOIR DE LA TAVERNE','table_jeux.png':'🎲 TABLE DE JEUX',
        'troubadour.png':'📖 LE TROUBADOUR','marche.png':'🛒 MARCHÉ D’ALTHERYA','banque.png':'🏦 BANQUE ROYALE',
        'arene.png':'⚔️ ARÈNE D’ALTHERYA','champion_legacy.png':'👑 CHAMPION DE L’ARÈNE','forge.png':'⚒️ FORGE D’ALTHERYA',
        'expeditions.png':'📌 PETITES ANNONCES','ruelle.png':'🌑 RUELLE SOMBRE','voleur.png':'🐺 LE VOLEUR',
        'braqueur.png':'🐯 LE BRAQUEUR','vigile.png':'🐻 LE VIGILE','castle.png':'🏰 CHÂTEAU D’ALTHERYA','lieu.png':'🏰 ALTHÉRYA'
    }
    return labels.get(filename, '🏰 ALTHÉRYA')



def _embed_text_v2(embed: discord.Embed | None) -> str:
    if embed is None:
        return ""
    parts=[]
    if getattr(embed, "title", None): parts.append(f"## {embed.title}")
    if getattr(embed, "description", None): parts.append(str(embed.description))
    for f in getattr(embed, "fields", []):
        parts.append(f"**{f.name}**\n{f.value}")
    footer=getattr(getattr(embed,"footer",None),"text",None)
    if footer: parts.append(f"*{footer}*")
    return "\n\n".join(parts)

async def edit_v2_surface(interaction: discord.Interaction, *, view: discord.ui.View, content: str | None=None, embed: discord.Embed | None=None, path: Path | None=None, filename: str | None=None, title: str | None=None):
    text="\n\n".join(x for x in (content, _embed_text_v2(embed)) if x)
    files=[]
    if path is not None and filename:
        files=[discord.File(path,filename=filename)]
    v2=_legacy_view_to_v2(view,content=text or None,filename=filename if files else None,title=title)
    await interaction.edit_original_response(content=None,attachments=files,embeds=[],view=v2)

async def edit_with_asset(interaction: discord.Interaction, path: Path, filename: str, view: discord.ui.View, content: str | None=None):
    file = discord.File(path, filename=filename)
    # Les sous-menus (Marché/Forge/etc.) utilisent parfois des embeds.
    # Quand on change de lieu ou qu'on revient au Hub, on les efface explicitement
    # pour éviter qu'une ancienne fiche reste affichée sous la nouvelle image.
    v2view = _legacy_view_to_v2(view, content=content, filename=filename, title=_place_title_from_filename(filename))
    await interaction.edit_original_response(
        content=None,
        attachments=[file],
        embeds=[],
        view=v2view,
    )

EVENTS = BASE / "assets" / "events"

DELAYED_SCENES = {
    "gerard_owner": ("🐔 **GÉRARD ?!**", "Le fermier s'arrête net.\n\nSon regard passe de toi à la poule. Puis de la poule à toi.\n\n**« MAIS QU'EST-CE QUE TU FOUS AVEC GÉRARD ?! »**", "gerard_owner.png"),
    "merchant_debt": ("🛒 **TOI !**", "Le Marchand se fige en te voyant.\n\n**« Tu pensais vraiment que j'avais oublié mes 120 Gold ?! »**\n\nTu n'as absolument aucun souvenir de lui avoir emprunté quoi que ce soit...", "merchant_debt.png"),
    "tavern_bill": ("🧾 **TON ADDITION.**", "Le Tavernier pose une addition interminable devant toi.\n\n**« Ça, c'est à toi. Et non, je ne veux pas savoir comment tu as réussi à commander tout ça. »**", "tavern_bill.png"),
    "pouch_owner": ("👝 **MA BOURSE !**", "Un passant s'arrête brutalement et pointe la bourse que tu avais retrouvée après ta cuite.\n\n**« C'est MA bourse ! »**", "pouch_owner.png"),
    "arm_rematch": ("💪 **LA REVANCHE !**", "Le colosse te reconnaît immédiatement et plante son coude sur la table.\n\n**« Cette fois, tu ne t'échappes pas. »**", "arm_rematch.png"),
    "stable_remembers": ("🐴 **ENCORE TOI...**", "En passant près des écuries, le fermier te reconnaît.\n\nDerrière lui, le cheval tourne lentement la tête vers toi. **Même regard.**\n\n« Tu comptes encore dormir dans ma paille cette nuit ? »", "horse_wakeup.png"),
    "ring_recognized": ("💍 **CETTE BAGUE...**", "Un inconnu remarque ta main et pâlit.\n\n**« Où est-ce que tu as trouvé cette bague ? »**", "ring_recognized.png"),
    "wolf_mark": ("🐺 **MONTRE-MOI TON BRAS.**", "Une silhouette de la Ruelle s'immobilise en apercevant la marque.\n\n**« Où est-ce que tu as eu ça ? »**\n\nTu aimerais bien le savoir aussi.", "wolf_mark.png"),
    "nameless_key": ("🗝️ **LA CLÉ RÉAGIT...**", "La Clé sans nom devient brûlante dans ta poche.\n\nDevant toi, une vieille porte que tu n'avais jamais remarquée. La serrure émet un léger **clic**.\n\n*Ce mystère sera poursuivi dans l'histoire de la Clé sans nom.*", "nameless_key.png"),
    "they_waited": ("💀 **ON T'ATTENDAIT.**", "Tu entres en pensant passer une soirée normale.\n\nToutes les conversations s'arrêtent. Plusieurs clients se retournent vers toi avec le sourire.\n\n**« Ah. Enfin. »**\n\nEux semblent parfaitement se souvenir de ta dernière cuite. Toi, absolument pas.", "they_waited.png"),
}

async def _open_place_after_scene(interaction: discord.Interaction, destination: str, notice: str | None = None):
    data = DESTINATIONS[destination]
    view = (TavernView() if destination == "tavern" else MarketView() if destination == "market" else
            BankView() if destination == "bank" else ArenaView() if destination == "arena" else
            ExpeditionView(interaction.user.id) if destination == "expeditions" else ForgeView() if destination == "forge" else
            DarkAlleyView() if destination == "alley" else CastleView() if destination == "castle" else PlaceView(destination))
    content = (arena_home_content(interaction.user.id) if destination == "arena" else
               expedition_home_content(interaction.user.id) if destination == "expeditions" else
               forge_home_content(interaction.user.id) if destination == "forge" else
               alley_home_content(interaction.user.id) if destination == "alley" else
               castle_home_content(interaction.user.id) if destination == "castle" else
               f"{data['emoji']} **{data['label']} de Altherya**")
    if notice:
        content = notice + "\n\n" + content
    await edit_with_asset(interaction, PLACES/data["image"], "lieu.png", view, content)

class SceneReturnView(discord.ui.View):
    def __init__(self, destination: str = "market"):
        super().__init__(timeout=300)
        b=discord.ui.Button(label="Continuer",emoji="➡️",style=discord.ButtonStyle.primary)
        async def cb(i):
            await safe_defer(i); await _open_place_after_scene(i,destination)
        b.callback=cb; self.add_item(b)

async def _scene_result(interaction, destination, title, text, image=None):
    await safe_defer(interaction)
    if image:
        await edit_with_asset(interaction, EVENTS/image, "scene.png", SceneReturnView(destination), f"{title}\n\n{text}")
    else:
        await _open_place_after_scene(interaction,destination,f"{title}\n{text}")

class DelayedSceneView(discord.ui.View):
    def __init__(self, consequence: dict, destination: str):
        super().__init__(timeout=300)
        self.cid=int(consequence['id']); self.key=str(consequence['consequence_key']); self.destination=destination
        specs={
          'gerard_owner':[('🐔 Rendre Gérard','return',discord.ButtonStyle.success),('🤥 Mentir','deny',discord.ButtonStyle.secondary),('🏃 Fuir avec Gérard','flee',discord.ButtonStyle.danger)],
          'merchant_debt':[('💰 Payer 120 Gold','pay',discord.ButtonStyle.success),('🤥 Nier','deny',discord.ButtonStyle.secondary),('🏃 Fuir','flee',discord.ButtonStyle.danger)],
          'tavern_bill':[('💰 Payer','pay',discord.ButtonStyle.success),('😇 Négocier','deny',discord.ButtonStyle.secondary),('🏃 Courir','flee',discord.ButtonStyle.danger)],
          'pouch_owner':[('👝 Rendre la bourse','return',discord.ButtonStyle.success),('🤥 Nier','deny',discord.ButtonStyle.secondary),('🏃 Fuir','flee',discord.ButtonStyle.danger)],
          'arm_rematch':[('💪 Accepter','fight',discord.ButtonStyle.danger),('💰 Parier 50 Gold','bet',discord.ButtonStyle.success),('🚪 Refuser','leave',discord.ButtonStyle.secondary)],
          'stable_remembers':[('💰 Dédommager 40 Gold','pay',discord.ButtonStyle.success),('🤷 Se justifier','deny',discord.ButtonStyle.secondary),('🚶 Partir discrètement','leave',discord.ButtonStyle.secondary)],
          'ring_recognized':[('💍 Montrer','show',discord.ButtonStyle.primary),('🤥 Cacher','deny',discord.ButtonStyle.secondary),('❓ Interroger','ask',discord.ButtonStyle.success)],
          'wolf_mark':[('🐺 Montrer la marque','show',discord.ButtonStyle.primary),('🗡️ Refuser','deny',discord.ButtonStyle.danger),('🏃 Partir','leave',discord.ButtonStyle.secondary)],
          'nameless_key':[('🗝️ Insérer la clé','show',discord.ButtonStyle.primary),('👂 Écouter','ask',discord.ButtonStyle.secondary),('🚶 Repartir','leave',discord.ButtonStyle.secondary)],
          'they_waited':[('🍺 Demander ce qui s’est passé','ask',discord.ButtonStyle.primary),('😐 Faire comme si de rien','deny',discord.ButtonStyle.secondary),('🚪 Ressortir','leave',discord.ButtonStyle.secondary)],
        }
        for label,action,style in specs.get(self.key,[('Continuer','leave',discord.ButtonStyle.primary)]):
            b=discord.ui.Button(label=label,style=style)
            async def cb(i,a=action): await self.resolve(i,a)
            b.callback=cb; self.add_item(b)

    async def resolve(self, i, action):
        uid=i.user.id; key=self.key
        # Résolutions économiques et jets simples. Les chances sont volontairement lisibles dans le résultat, pas dans les secrets.
        if key=='merchant_debt':
            if action=='pay':
                paid=TAVERN_STORE.charge_wallet(uid,120); TAVERN_STORE.resolve_consequence(self.cid,uid)
                return await _scene_result(i,self.destination,'💰 **DETTE RÉGLÉE**',f'Le Marchand récupère **{paid} Gold**. « On est quittes. »')
            if action=='deny':
                if random.random()<0.45:
                    TAVERN_STORE.resolve_consequence(self.cid,uid); return await _scene_result(i,self.destination,'🤥 **IL HÉSITE...**','Après un long silence, le Marchand doute suffisamment pour te laisser passer. Cette fois.')
                return await _scene_result(i,self.destination,'😡 **MAUVAISE MÉMOIRE, MAUVAIS MENSONGE**','Le Marchand reconnaît parfaitement ta tête. La dette reste active.')
            if random.random()<0.60:
                return await _scene_result(i,self.destination,'🏃 **TU T’ÉCHAPPES !**','Tu disparais dans la foule. **La dette, elle, n’a pas disparu.**')
            paid=TAVERN_STORE.charge_wallet(uid,167); TAVERN_STORE.resolve_consequence(self.cid,uid)
            return await _scene_result(i,self.destination,'💥 **IL ÉTAIT ÉTONNAMMENT RAPIDE**',f'Le Marchand te rattrape, récupère son dû et quelques pièces pour le dérangement. **-{paid} Gold**.','merchant_caught.png')
        if key=='gerard_owner':
            if action=='return':
                TAVERN_STORE.resolve_consequence(self.cid,uid); return await _scene_result(i,self.destination,'🐔 **GÉRARD RENTRE CHEZ LUI**','Le fermier serre Gérard contre lui. Le poulet ne te remercie même pas.')
            if action=='deny':
                if random.random()<0.40:
                    TAVERN_STORE.resolve_consequence(self.cid,uid); return await _scene_result(i,self.destination,'🤥 **« ...GÉRARD ? NON. JAMAIS VU. »**','Contre toute attente, le fermier hésite. Tu profites de cet instant de faiblesse pour partir.')
                return await _scene_result(i,self.destination,'🐔 **GÉRARD TE TRAHIT**','La poule répond immédiatement à son nom. Ton mensonge vient de mourir.')
            if random.random()<0.55:
                return await _scene_result(i,self.destination,'🏃🐔 **FUITE AVEC VOLAILLE**','Tu réussis à disparaître avec Gérard. Le fermier n’oubliera pas.')
            TAVERN_STORE.resolve_consequence(self.cid,uid)
            return await _scene_result(i,self.destination,'🐔 **T’AS VRAIMENT ESSAYÉ DE PARTIR AVEC GÉRARD ?!**','Le fermier te rattrape et récupère Gérard. Tu conserves surtout ta honte.','gerard_caught.png')
        if key=='tavern_bill':
            cost=180
            if action=='pay':
                paid=TAVERN_STORE.charge_wallet(uid,cost); TAVERN_STORE.resolve_consequence(self.cid,uid); return await _scene_result(i,self.destination,'🧾 **ARDOISE EFFACÉE**',f'Le Tavernier récupère **{paid} Gold** et range enfin la facture.')
            if action=='deny' and random.random()<0.50:
                paid=TAVERN_STORE.charge_wallet(uid,120); TAVERN_STORE.resolve_consequence(self.cid,uid); return await _scene_result(i,self.destination,'🤝 **MARCHÉ CONCLU**',f'Après une négociation douloureuse : **-{paid} Gold**.')
            if action=='flee' and random.random()<0.35:
                return await _scene_result(i,self.destination,'🏃 **PRESQUE DEHORS...**','Tu files avant qu’il réagisse. L’ardoise reste ouverte.')
            paid=TAVERN_STORE.charge_wallet(uid,205); TAVERN_STORE.resolve_consequence(self.cid,uid)
            return await _scene_result(i,self.destination,'🍺 **TU NE VAS NULLE PART.**',f'Le Vigile bloque la porte. Addition + supplément fuite : **-{paid} Gold**.','tavern_blocked.png')
        if key=='pouch_owner':
            if action=='return': TAVERN_STORE.resolve_consequence(self.cid,uid); return await _scene_result(i,self.destination,'👝 **RENDUE À SON PROPRIÉTAIRE**','Il récupère sa bourse et te fixe encore quelques secondes, méfiant.')
            if action=='deny' and random.random()<0.45: TAVERN_STORE.resolve_consequence(self.cid,uid); return await _scene_result(i,self.destination,'🤥 **LE DOUTE S’INSTALLE**','Il finit par te laisser tranquille.')
            if action=='flee' and random.random()<0.60: return await _scene_result(i,self.destination,'🏃 **TU DISPARAIS**','Tu gardes la bourse... et probablement un nouvel ennemi.')
            paid=TAVERN_STORE.charge_wallet(uid,90); TAVERN_STORE.resolve_consequence(self.cid,uid); return await _scene_result(i,self.destination,'💥 **RATTRAPÉ**',f'Il récupère ce qu’il estime lui appartenir. **-{paid} Gold**.')
        if key=='arm_rematch':
            wager=50 if action=='bet' else 0
            if action=='leave': TAVERN_STORE.resolve_consequence(self.cid,uid); return await _scene_result(i,self.destination,'🚪 **PAS AUJOURD’HUI**','Le colosse éclate de rire. « La prochaine fois. »')
            if wager: TAVERN_STORE.charge_wallet(uid,wager)
            if random.random()<0.38:
                TAVERN_STORE.resolve_consequence(self.cid,uid); return await _scene_result(i,self.destination,'💪 **REVANCHE GAGNÉE !**',('Tu le fais plier. La Taverne explose de cris.' + (' Ton pari est rendu avec les honneurs.' if wager else '')))
            TAVERN_STORE.resolve_consequence(self.cid,uid); return await _scene_result(i,self.destination,'💪 **T’AVAIS DIT REVANCHE. PAS HUMILIATION.**','Ton bras rencontre la table en un temps remarquablement court. Toute la Taverne éclate de rire.','arm_lost.png')
        if key=='stable_remembers':
            if action=='pay': paid=TAVERN_STORE.charge_wallet(uid,40); TAVERN_STORE.resolve_consequence(self.cid,uid); return await _scene_result(i,self.destination,'🐴 **PAIX AVEC LA PAILLE**',f'Le fermier accepte **{paid} Gold**. Le cheval continue pourtant de te juger.')
            TAVERN_STORE.resolve_consequence(self.cid,uid); return await _scene_result(i,self.destination,'🐴 **LE CHEVAL N’OUBLIE PAS**','Tu t’éloignes. Son regard te suit jusqu’au bout du chemin.')
        if key=='ring_recognized':
            TAVERN_STORE.resolve_consequence(self.cid,uid)
            texts={'show':'L’inconnu examine la bague sans la toucher. « Ne la donne à personne. »','deny':'Tu refermes la main. Il murmure : « Je sais ce que j’ai vu. » puis disparaît.','ask':'Son visage se ferme. « Si tu ne sais pas d’où elle vient, c’est pire que je pensais. »'}
            return await _scene_result(i,self.destination,'💍 **UN MAUVAIS PRESSENTIMENT**',texts.get(action,''))
        if key=='wolf_mark':
            TAVERN_STORE.resolve_consequence(self.cid,uid)
            texts={'show':'Il observe la marque, puis recule d’un pas. « Alors ils t’ont trouvé. »','deny':'La silhouette sourit. « Garde tes secrets. Eux garderont les leurs. »','leave':'Tu repars. Dans ton dos : « Tu reviendras. »'}
            return await _scene_result(i,self.destination,'🐺 **LA MARQUE RESTE**',texts.get(action,''))
        if key=='nameless_key':
            # L'histoire de la clé est volontairement mise en attente, comme demandé.
            TAVERN_STORE.resolve_consequence(self.cid,uid)
            texts={'show':'La clé entre parfaitement... puis s’arrête. **Quelque chose manque.** La porte refuse encore de livrer son secret.','ask':'Derrière la porte : trois coups lents. Puis plus rien.','leave':'Tu ranges la clé. La chaleur disparaît immédiatement.'}
            return await _scene_result(i,self.destination,'🗝️ **LE SECRET ATTENDRA**',texts.get(action,''))
        if key=='they_waited':
            TAVERN_STORE.resolve_consequence(self.cid,uid)
            texts={'ask':'Ils échangent tous le même sourire. « Tu ne te souviens vraiment de rien ? » Personne ne t’explique davantage.','deny':'Tu t’assois comme si tout était normal. Ils font exactement pareil. C’est encore plus inquiétant.','leave':'Tu ressors immédiatement. Derrière toi, toute la salle éclate de rire.'}
            return await _scene_result(i,self.destination,'💀 **UNE SOIRÉE DONT EUX SE SOUVIENNENT**',texts.get(action,''))
        TAVERN_STORE.resolve_consequence(self.cid,uid); await _scene_result(i,self.destination,'📜 **FIN DE LA SCÈNE**','Tu reprends ta route.')

async def show_delayed_scene(interaction: discord.Interaction, consequence: dict, destination: str):
    key=str(consequence['consequence_key']); title,text,image=DELAYED_SCENES[key]
    file=discord.File(EVENTS/image,filename='scene.png')
    await interaction.response.send_message(content=f"{title}\n\n{text}",file=file,view=DelayedSceneView(consequence,destination),ephemeral=True)

class HorseWakeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        b=discord.ui.Button(label='Revenir en ville',emoji='🏙️',style=discord.ButtonStyle.primary)
        async def cb(i): await return_to_hub(i)
        b.callback=cb; self.add_item(b)

async def show_horse_wakeup(interaction: discord.Interaction, drink_line: str):
    file=discord.File(EVENTS/'horse_wakeup.png',filename='scene.png')
    await interaction.response.send_message(content=(drink_line+"\n\n🐴 **IL JUGE MES CHOIX DE VIE**\n\nTu ouvres les yeux avec un mal de crâne monumental. De la paille partout. Une bouteille vide à côté de toi.\n\nUn fermier te fixe, bras croisés. Derrière lui, un cheval te regarde avec une déception si profonde que tu t’excuses spontanément.\n\n**Tu n’as absolument aucun souvenir de la façon dont tu es arrivé ici.**"),file=file,view=HorseWakeView(),ephemeral=True)

async def _send_personal_place(interaction: discord.Interaction, destination: str, *, edit: bool = False):
    """Ouvre un lieu dans une session éphémère privée au joueur.

    Le Hub public n'est jamais modifié : chaque joueur possède donc sa propre
    interface de navigation sans gêner les autres membres du serveur.
    """
    if destination == "alley":
        remaining = DARK_STORE.ban_remaining(interaction.user.id)
        if remaining:
            await interaction.response.send_message(
                f"🔒 Après ton dernier braquage, tu n'es plus le bienvenu dans la Ruelle sombre.\n"
                f"⏳ Retour possible dans **{short_time(remaining)}**.",
                ephemeral=True,
            )
            return

    delayed = TAVERN_STORE.pending_consequence(interaction.user.id, destination)
    if delayed:
        await show_delayed_scene(interaction, delayed, destination)
        return

    data = DESTINATIONS[destination]
    image = PLACES / data["image"]
    view = (
        TavernView() if destination == "tavern" else
        MarketView() if destination == "market" else
        BankView() if destination == "bank" else
        ArenaView() if destination == "arena" else
        ExpeditionView(interaction.user.id) if destination == "expeditions" else
        ForgeView() if destination == "forge" else
        DarkAlleyView() if destination == "alley" else
        CastleView() if destination == "castle" else
        PlaceView(destination)
    )
    content = (
        arena_home_content(interaction.user.id) if destination == "arena" else
        expedition_home_content(interaction.user.id) if destination == "expeditions" else
        forge_home_content(interaction.user.id) if destination == "forge" else
        alley_home_content(interaction.user.id) if destination == "alley" else
        castle_home_content(interaction.user.id) if destination == "castle" else
        f"{data['emoji']} **{data['label']} de Altherya**"
    )
    file = discord.File(image, filename="lieu.png")
    v2view = _legacy_view_to_v2(view, content=content, filename="lieu.png", title=f"{data['emoji']} {data['label'].upper()} — ALTHÉRYA")
    if edit:
        await safe_defer(interaction)
        await interaction.edit_original_response(content=None, attachments=[file], embeds=[], view=v2view)
    else:
        await interaction.response.send_message(file=file, view=v2view, ephemeral=True)

async def travel(interaction: discord.Interaction, destination: str, *, edit: bool = False):
    # Depuis le Hub public : création d'une unique session privée.
    # Depuis cette session : navigation par édition du même message, façon Oddium.
    await _send_personal_place(interaction, destination, edit=edit)

async def return_to_hub(interaction: discord.Interaction):
    """Retourne à Altherya dans LA MÊME fenêtre privée, sans empiler de messages."""
    file = discord.File(PLACES / "hub.png", filename="altherya_city.png")
    try:
        if not interaction.response.is_done():
            await interaction.response.edit_message(
                content=None,
                attachments=[file], embeds=[], view=HubView(private_session=True),
            )
        else:
            await interaction.edit_original_response(
                content=None,
                attachments=[file], embeds=[], view=HubView(private_session=True),
            )
    except (discord.NotFound, discord.HTTPException):
        pass

def _load_hub_state() -> dict:
    try:
        if HUB_STATE_FILE.exists():
            return json.loads(HUB_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        pass
    return {}

def _save_hub_state(guild_id: int, channel_id: int, message_id: int):
    DATA.mkdir(parents=True, exist_ok=True)
    HUB_STATE_FILE.write_text(
        json.dumps({
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": message_id,
        }, indent=2),
        encoding="utf-8",
    )

async def _publish_hub(channel: discord.abc.Messageable) -> discord.Message:
    # V2.10 : le texte et l'image vivent directement dans le LayoutView.
    file = discord.File(WORLD_FORGE.WORLD_MAP, filename="elyndor_map.png")
    return await channel.send(file=file, view=WorldHubView())

async def ensure_fixed_hub():
    """Réactive le Hub configuré après un redémarrage du bot."""
    state = _load_hub_state()
    channel_id = state.get("channel_id")
    message_id = state.get("message_id")
    if not channel_id or not message_id:
        return
    try:
        channel = bot.get_channel(int(channel_id)) or await bot.fetch_channel(int(channel_id))
        message = await channel.fetch_message(int(message_id))
        file = discord.File(WORLD_FORGE.WORLD_MAP, filename="elyndor_map.png")
        await message.edit(
            content=None, embeds=[], attachments=[file], view=WorldHubView(),
        )
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
        # Le Hub a probablement été supprimé ou le salon n'est plus accessible.
        # Un administrateur peut simplement relancer /legacy dans le salon voulu.
        pass


# =========================
# V1.24 — Panneau administrateur
# =========================

def _native_admin_ok(interaction: discord.Interaction) -> bool:
    return bool(interaction.guild and isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator)

def _admin_ok(interaction: discord.Interaction) -> bool:
    if _native_admin_ok(interaction):
        return True
    return bool(interaction.guild and ADMIN_STORE.has_admin_access(interaction.guild.id, interaction.user.id))

async def _admin_guard(interaction: discord.Interaction) -> bool:
    if _admin_ok(interaction):
        return True
    msg = "❌ Ce panneau est réservé aux **administrateurs autorisés**."
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)
    return False

async def _get_member(interaction: discord.Interaction, user_id: int) -> discord.Member | None:
    if not interaction.guild:
        return None
    member = interaction.guild.get_member(int(user_id))
    if member:
        return member
    try:
        return await interaction.guild.fetch_member(int(user_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None

async def announce_achievement_for(guild: discord.Guild, user: discord.abc.User, achievement_key: str):
    ach = ACHIEVEMENTS.get(achievement_key)
    if not ach:
        return
    channel_id = ACHIEVEMENT_STORE.get_channel(guild.id)
    if not channel_id:
        return
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        progress = ACHIEVEMENT_STORE.branch_progress(user.id, ach.branch)
        embed = discord.Embed(
            title="🏆 SUCCÈS DÉBLOQUÉ !",
            description=f"{user.mention} vient de débloquer un nouveau succès !\n\n### {ach.branch_emoji} {ach.title}\n{ach.description}",
            color=ach.color,
        )
        embed.add_field(name="Branche", value=f"{ach.branch_emoji} **{ach.branch_label}**", inline=True)
        embed.add_field(name="Rareté", value=f"{ach.rarity_emoji} **{ach.rarity}**", inline=True)
        embed.add_field(name="Progression", value=f"**{progress}/{branch_total}**", inline=True)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text="Altherya • Système de succès • Attribution admin")
        await channel.send(embed=embed)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass

class AdminAmountModal(discord.ui.Modal):
    def __init__(self, target_id: int, mode: str):
        super().__init__(title="Gestion du Gold")
        self.target_id = int(target_id); self.mode = mode
        self.amount = discord.ui.TextInput(label="Montant", placeholder="Exemple : 500", max_length=12)
        self.add_item(self.amount)
    async def on_submit(self, interaction: discord.Interaction):
        if not await _admin_guard(interaction): return
        try: amount = int(str(self.amount.value).replace(' ',''))
        except ValueError:
            await interaction.response.send_message("❌ Montant invalide.", ephemeral=True); return
        amount = abs(amount)
        if amount <= 0:
            await interaction.response.send_message("❌ Le montant doit être supérieur à 0.", ephemeral=True); return
        delta = amount if self.mode == 'add' else -amount
        old,new = ADMIN_STORE.adjust_gold(self.target_id, delta)
        ADMIN_STORE.log(interaction.user.id, self.target_id, f'gold_{self.mode}', f'{old}->{new}')
        member = await _get_member(interaction,self.target_id)
        if member and new != old:
            await announce_gold_activity(interaction.guild, member, new-old, f"Ajustement administrateur par {interaction.user.display_name}")
        await interaction.response.send_message(f"✅ **{member.mention if member else self.target_id}** : {old} → **{new} Gold**.", ephemeral=True)

class AdminMoneyView(discord.ui.View):
    def __init__(self, target_id:int):
        super().__init__(timeout=180); self.target_id=int(target_id)
        add=discord.ui.Button(label="Ajouter Gold",emoji="➕",style=discord.ButtonStyle.success)
        rem=discord.ui.Button(label="Retirer Gold",emoji="➖",style=discord.ButtonStyle.danger)
        async def add_cb(i):
            if await _admin_guard(i): await i.response.send_modal(AdminAmountModal(self.target_id,'add'))
        async def rem_cb(i):
            if await _admin_guard(i): await i.response.send_modal(AdminAmountModal(self.target_id,'remove'))
        add.callback=add_cb; rem.callback=rem_cb; self.add_item(add); self.add_item(rem)

class AdminLevelView(discord.ui.View):
    def __init__(self,target_id:int):
        super().__init__(timeout=180); self.target_id=int(target_id)
        plus=discord.ui.Button(label="+1 niveau",emoji="⬆️",style=discord.ButtonStyle.success)
        minus=discord.ui.Button(label="-1 niveau",emoji="⬇️",style=discord.ButtonStyle.danger)
        async def change(i,delta):
            if not await _admin_guard(i): return
            old,new,xp=ADMIN_STORE.adjust_level(self.target_id,delta)
            ADMIN_STORE.log(i.user.id,self.target_id,'level_adjust',f'{old}->{new}')
            m=await _get_member(i,self.target_id)
            if m:
                await announce_player_log(i.guild, m, f"Niveau modifié par {i.user.display_name}", category="Administration", details=f"Niveau {old} → {new}")
            await i.response.send_message(f"✅ **{m.mention if m else self.target_id}** : niveau {old} → **{new}**.",ephemeral=True)
        plus.callback=lambda i: change(i,1); minus.callback=lambda i: change(i,-1)
        self.add_item(plus); self.add_item(minus)

async def _ensure_muted_role(guild: discord.Guild) -> discord.Role:
    role = discord.utils.get(guild.roles, name="Altherya Muted")
    if role is None:
        role = await guild.create_role(name="Altherya Muted", reason="Altherya /admin — mute permanent")
    for channel in guild.channels:
        try:
            overwrite = channel.overwrites_for(role)
            if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                overwrite.send_messages=False; overwrite.add_reactions=False; overwrite.create_public_threads=False; overwrite.create_private_threads=False; overwrite.send_messages_in_threads=False
            if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                overwrite.speak=False
            await channel.set_permissions(role, overwrite=overwrite, reason="Altherya /admin — permissions mute")
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            pass
    return role

class TempMuteModal(discord.ui.Modal):
    def __init__(self,target_id:int):
        super().__init__(title="Mute temporaire"); self.target_id=int(target_id)
        self.minutes=discord.ui.TextInput(label="Durée en minutes",placeholder="60 = 1 heure • max 40320 (28 jours)",max_length=6)
        self.reason=discord.ui.TextInput(label="Raison (optionnel)",required=False,max_length=150)
        self.add_item(self.minutes); self.add_item(self.reason)
    async def on_submit(self,i):
        if not await _admin_guard(i): return
        try: mins=int(self.minutes.value)
        except ValueError:
            await i.response.send_message("❌ Durée invalide.",ephemeral=True); return
        if not 1 <= mins <= 40320:
            await i.response.send_message("❌ Entre 1 minute et 40320 minutes (28 jours).",ephemeral=True); return
        m=await _get_member(i,self.target_id)
        if not m:
            await i.response.send_message("❌ Membre introuvable.",ephemeral=True); return
        try:
            from datetime import timedelta
            await m.timeout(timedelta(minutes=mins), reason=self.reason.value or f"Mute temporaire par {i.user}")
            ADMIN_STORE.log(i.user.id,m.id,'mute_temp',f'{mins} min • {self.reason.value}')
            await i.response.send_message(f"🔇 {m.mention} est mute pour **{mins} minute(s)**.",ephemeral=True)
        except (discord.Forbidden, discord.HTTPException) as e:
            await i.response.send_message(f"❌ Impossible de mute ce membre : {e}",ephemeral=True)

class AdminModerationView(discord.ui.View):
    def __init__(self,target_id:int):
        super().__init__(timeout=180); self.target_id=int(target_id)
        kick=discord.ui.Button(label="Kick",emoji="👢",style=discord.ButtonStyle.danger)
        ban=discord.ui.Button(label="Ban",emoji="🔨",style=discord.ButtonStyle.danger)
        temp=discord.ui.Button(label="Mute temporaire",emoji="⏱️",style=discord.ButtonStyle.secondary)
        perm=discord.ui.Button(label="Mute permanent",emoji="🔇",style=discord.ButtonStyle.secondary)
        unmute=discord.ui.Button(label="Unmute",emoji="🔊",style=discord.ButtonStyle.success)
        async def k(i):
            if not await _admin_guard(i): return
            m=await _get_member(i,self.target_id)
            if not m: await i.response.send_message("❌ Membre introuvable.",ephemeral=True); return
            try:
                await m.kick(reason=f"Altherya /admin par {i.user}"); ADMIN_STORE.log(i.user.id,m.id,'kick'); await i.response.send_message(f"👢 **{m}** a été expulsé.",ephemeral=True)
            except (discord.Forbidden,discord.HTTPException) as e: await i.response.send_message(f"❌ Kick impossible : {e}",ephemeral=True)
        async def b(i):
            if not await _admin_guard(i): return
            m=await _get_member(i,self.target_id)
            if not m: await i.response.send_message("❌ Membre introuvable.",ephemeral=True); return
            try:
                await i.guild.ban(m,reason=f"Altherya /admin par {i.user}",delete_message_seconds=0); ADMIN_STORE.log(i.user.id,m.id,'ban'); await i.response.send_message(f"🔨 **{m}** a été banni.",ephemeral=True)
            except (discord.Forbidden,discord.HTTPException) as e: await i.response.send_message(f"❌ Ban impossible : {e}",ephemeral=True)
        async def t(i):
            if await _admin_guard(i): await i.response.send_modal(TempMuteModal(self.target_id))
        async def p(i):
            if not await _admin_guard(i): return
            m=await _get_member(i,self.target_id)
            if not m: await i.response.send_message("❌ Membre introuvable.",ephemeral=True); return
            try:
                role=await _ensure_muted_role(i.guild); await m.add_roles(role,reason=f"Altherya /admin par {i.user}"); ADMIN_STORE.log(i.user.id,m.id,'mute_perm'); await i.response.send_message(f"🔇 {m.mention} est mute **jusqu'à retrait manuel**.",ephemeral=True)
            except (discord.Forbidden,discord.HTTPException) as e: await i.response.send_message(f"❌ Mute impossible : {e}",ephemeral=True)
        async def u(i):
            if not await _admin_guard(i): return
            m=await _get_member(i,self.target_id)
            if not m: await i.response.send_message("❌ Membre introuvable.",ephemeral=True); return
            try:
                await m.timeout(None,reason=f"Altherya /admin unmute par {i.user}")
                role=discord.utils.get(i.guild.roles,name="Altherya Muted")
                if role and role in m.roles: await m.remove_roles(role,reason=f"Altherya /admin par {i.user}")
                ADMIN_STORE.log(i.user.id,m.id,'unmute'); await i.response.send_message(f"🔊 {m.mention} peut de nouveau parler.",ephemeral=True)
            except (discord.Forbidden,discord.HTTPException) as e: await i.response.send_message(f"❌ Unmute impossible : {e}",ephemeral=True)
        kick.callback=k; ban.callback=b; temp.callback=t; perm.callback=p; unmute.callback=u
        for x in (kick,ban,temp,perm,unmute): self.add_item(x)

class AdminAchievementSelect(discord.ui.Select):
    def __init__(self,target_id:int,mode:str):
        self.target_id=int(target_id); self.mode=mode
        opts=[]
        for key,ach in ACHIEVEMENTS.items():
            opts.append(discord.SelectOption(label=f"{ach.branch_label} — {ach.rarity}",value=key,emoji=ach.branch_emoji,description=ach.title[:100]))
        super().__init__(placeholder="Choisir un succès...",options=opts[:25],min_values=1,max_values=1)
    async def callback(self,i):
        if not await _admin_guard(i): return
        key=self.values[0]; ach=ACHIEVEMENTS[key]; m=await _get_member(i,self.target_id)
        if self.mode=='unlock':
            changed=ACHIEVEMENT_STORE.unlock(self.target_id,key)
            if changed and i.guild and m: await announce_achievement_for(i.guild,m,key)
            ADMIN_STORE.log(i.user.id,self.target_id,'achievement_unlock',key)
            if m:
                await announce_player_log(i.guild, m, f"Succès attribué par {i.user.display_name}: {ach.title}", category="Administration")
            await i.response.send_message(("✅ Succès débloqué" if changed else "ℹ️ Succès déjà débloqué")+f" : **{ach.title}**.",ephemeral=True)
        else:
            changed=ACHIEVEMENT_STORE.remove(self.target_id,key); ADMIN_STORE.log(i.user.id,self.target_id,'achievement_remove',key)
            if m:
                await announce_player_log(i.guild, m, f"Succès retiré par {i.user.display_name}: {ach.title}", category="Administration")
            await i.response.send_message(("✅ Succès supprimé" if changed else "ℹ️ Ce succès n'était pas débloqué")+f" : **{ach.title}**.",ephemeral=True)

class AdminAchievementView(discord.ui.View):
    def __init__(self,target_id:int,mode:str):
        super().__init__(timeout=180); self.add_item(AdminAchievementSelect(target_id,mode))

class ResourceAdminModal(discord.ui.Modal):
    def __init__(self,target_id:int,mode:str):
        super().__init__(title="Gestion d'un item / ressource"); self.target_id=int(target_id); self.mode=mode
        self.name=discord.ui.TextInput(label="Nom exact de l'item",placeholder="Ex: Minerai de fer ou Invitation clandestine",max_length=60)
        self.qty=discord.ui.TextInput(label="Quantité",placeholder="Ex: 5",max_length=8)
        self.add_item(self.name); self.add_item(self.qty)
    async def on_submit(self,i):
        if not await _admin_guard(i): return
        name=str(self.name.value).strip()
        allowed=set(RESOURCE_SELL_PRICES)|{INVITATION_ITEM}
        if name not in allowed:
            await i.response.send_message("❌ Item inconnu. Utilise le **nom exact** d'une ressource d'expédition ou `Invitation clandestine`.",ephemeral=True); return
        try: qty=abs(int(self.qty.value))
        except ValueError:
            await i.response.send_message("❌ Quantité invalide.",ephemeral=True); return
        if qty<=0: await i.response.send_message("❌ Quantité invalide.",ephemeral=True); return
        old,new=ADMIN_STORE.set_resource(self.target_id,name,qty if self.mode=='add' else -qty)
        ADMIN_STORE.log(i.user.id,self.target_id,f'item_{self.mode}',f'{name} {old}->{new}')
        m=await _get_member(i,self.target_id)
        if m:
            await announce_player_log(i.guild, m, f"Item modifié par {i.user.display_name}: {name}", category="Administration", details=f"Stock {old} → {new}")
        await i.response.send_message(f"✅ **{name}** : {old} → **{new}**.",ephemeral=True)

class AdminItemView(discord.ui.View):
    def __init__(self,target_id:int):
        super().__init__(timeout=180); self.target_id=int(target_id)
        for key,label,emoji in [('pickaxe','Pioche','⛏️'),('axe','Hache','🪓'),('spear','Lance','🗡️'),('bag','Sac','🎒')]:
            b=discord.ui.Button(label=label,emoji=emoji,style=discord.ButtonStyle.secondary)
            async def cb(i,k=key,l=label):
                if not await _admin_guard(i): return
                owned=EXPEDITION_STORE.has_equipment(self.target_id,k)
                ADMIN_STORE.set_gear_owned(self.target_id,k,not owned); ADMIN_STORE.log(i.user.id,self.target_id,'gear_toggle',f'{k}={not owned}')
                m=await _get_member(i,self.target_id)
                if m:
                    await announce_player_log(i.guild, m, f"Équipement {'ajouté' if not owned else 'retiré'} par {i.user.display_name}: {l}", category="Administration")
                await i.response.send_message(f"✅ **{l}** : {'ajoutée' if not owned else 'supprimée'} au joueur.",ephemeral=True)
            b.callback=cb; self.add_item(b)
        add=discord.ui.Button(label="Ajouter ressource",emoji="➕",style=discord.ButtonStyle.success,row=1)
        rem=discord.ui.Button(label="Retirer ressource",emoji="➖",style=discord.ButtonStyle.danger,row=1)
        add.callback=lambda i: i.response.send_modal(ResourceAdminModal(self.target_id,'add'))
        rem.callback=lambda i: i.response.send_modal(ResourceAdminModal(self.target_id,'remove'))
        self.add_item(add); self.add_item(rem)

class AdminTargetSelect(discord.ui.UserSelect):
    def __init__(self,action:str):
        self.action=action
        super().__init__(placeholder="Sélectionner le membre...",min_values=1,max_values=1)
    async def callback(self,i):
        if not await _admin_guard(i): return
        target=self.values[0]; tid=int(target.id)
        if self.action=='money': view=AdminMoneyView(tid); text=f"💰 Gestion du Gold de {target.mention}"
        elif self.action=='level': view=AdminLevelView(tid); text=f"📈 Gestion du niveau de {target.mention}"
        elif self.action=='moderation': view=AdminModerationView(tid); text=f"🛡️ Modération de {target.mention}"
        elif self.action=='achievement_unlock': view=AdminAchievementView(tid,'unlock'); text=f"🏆 Débloquer un succès à {target.mention}"
        elif self.action=='achievement_remove': view=AdminAchievementView(tid,'remove'); text=f"🗑️ Supprimer un succès à {target.mention}"
        elif self.action=='reset_cooldowns':
            result=ADMIN_STORE.reset_cooldowns(tid)
            ADMIN_STORE.log(i.user.id,tid,'reset_cooldowns',f"dark={result['dark_actions']} arena={result['arena_champion']} tavern={result.get('tavern_drink',0)}")
            await announce_player_log(i.guild, target, f"Cooldowns réinitialisés par {i.user.display_name}", category="Administration")
            await i.response.edit_message(content=f"✅ Tous les cooldowns temporisés de {target.mention} ont été réinitialisés.",embed=None,view=None)
            return
        elif self.action=='clear_alley_ban':
            changed=ADMIN_STORE.clear_alley_ban(tid)
            ADMIN_STORE.log(i.user.id,tid,'clear_alley_ban',f"removed={changed}")
            await announce_player_log(i.guild, target, f"Ban de la Ruelle sombre levé par {i.user.display_name}", category="Administration")
            msg=f"✅ Le ban de la Ruelle sombre de {target.mention} a été annulé." if changed else f"ℹ️ {target.mention} n'avait aucun ban actif dans la Ruelle sombre."
            await i.response.edit_message(content=msg,embed=None,view=None)
            return
        else: view=AdminItemView(tid); text=f"🎒 Gestion des items de {target.mention}"
        await i.response.edit_message(content=text,embed=None,view=view)

class AdminTargetView(discord.ui.View):
    def __init__(self,action:str): super().__init__(timeout=180); self.add_item(AdminTargetSelect(action))

class AdminEventsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        for key,(label,emoji) in EVENTS.items():
            enabled=ADMIN_STORE.event_enabled(key)
            b=discord.ui.Button(label=f"{label} : {'ON' if enabled else 'OFF'}",emoji=emoji,style=discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary)
            async def cb(i,k=key):
                if not await _admin_guard(i): return
                new=not ADMIN_STORE.event_enabled(k); ADMIN_STORE.set_event(k,new,i.user.id)
                await announce_player_log(i.guild, i.user, f"Événement {EVENTS[k][0]} {'activé' if new else 'désactivé'}", category="Administration")
                await i.response.edit_message(content="🎉 **Gestion des événements**\nLes multiplicateurs s'appliquent aux récompenses générées par Altherya.",view=AdminEventsView())
            b.callback=cb; self.add_item(b)

class AdminSuccessActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        u=discord.ui.Button(label="Débloquer un succès",emoji="🏆",style=discord.ButtonStyle.success)
        r=discord.ui.Button(label="Supprimer un succès",emoji="🗑️",style=discord.ButtonStyle.danger)
        async def uc(i):
            if await _admin_guard(i): await i.response.edit_message(content="🏆 Sélectionne le joueur.",view=AdminTargetView('achievement_unlock'))
        async def rc(i):
            if await _admin_guard(i): await i.response.edit_message(content="🗑️ Sélectionne le joueur.",view=AdminTargetView('achievement_remove'))
        u.callback=uc; r.callback=rc; self.add_item(u); self.add_item(r)

class AdminCooldownView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        enabled=ADMIN_STORE.cooldowns_enabled()
        toggle=discord.ui.Button(
            label=f"Cooldowns : {'ON' if enabled else 'OFF'}",
            emoji="⏱️",
            style=discord.ButtonStyle.success if enabled else discord.ButtonStyle.danger,
            row=0,
        )
        reset=discord.ui.Button(label="Reset cooldown joueur",emoji="🔄",style=discord.ButtonStyle.primary,row=1)
        unban=discord.ui.Button(label="Annuler ban Ruelle",emoji="🌑",style=discord.ButtonStyle.secondary,row=1)

        async def toggle_cb(i):
            if not await _admin_guard(i): return
            new=not ADMIN_STORE.cooldowns_enabled()
            ADMIN_STORE.set_cooldowns_enabled(new,i.user.id)
            await announce_player_log(i.guild, i.user, f"Cooldowns globaux {'activés' if new else 'désactivés'}", category="Administration")
            await i.response.edit_message(
                content=f"⏱️ **Gestion des cooldowns**\nÉtat global : **{'ACTIVÉS' if new else 'DÉSACTIVÉS'}**",
                view=AdminCooldownView(),
            )

        async def reset_cb(i):
            if not await _admin_guard(i): return
            await i.response.edit_message(content="🔄 Sélectionne le joueur dont tu veux réinitialiser les cooldowns.",view=AdminTargetView('reset_cooldowns'))

        async def unban_cb(i):
            if not await _admin_guard(i): return
            await i.response.edit_message(content="🌑 Sélectionne le joueur dont tu veux annuler le ban de la Ruelle sombre.",view=AdminTargetView('clear_alley_ban'))

        toggle.callback=toggle_cb
        reset.callback=reset_cb
        unban.callback=unban_cb
        self.add_item(toggle); self.add_item(reset); self.add_item(unban)

class AdminAccessSelect(discord.ui.UserSelect):
    def __init__(self, mode: str):
        self.mode = mode
        super().__init__(placeholder="Sélectionner le joueur...", min_values=1, max_values=1)

    async def callback(self, i: discord.Interaction):
        if not _native_admin_ok(i):
            await i.response.send_message("❌ Seul un administrateur Discord peut gérer les accès `/admin`.", ephemeral=True)
            return
        target = self.values[0]
        if self.mode == 'grant':
            changed = ADMIN_STORE.grant_admin_access(i.guild.id, target.id, i.user.id)
            text = f"✅ {target.mention} peut maintenant utiliser `/admin`." if changed else f"ℹ️ {target.mention} avait déjà accès à `/admin`."
        else:
            changed = ADMIN_STORE.revoke_admin_access(i.guild.id, target.id, i.user.id)
            text = f"✅ Accès `/admin` retiré à {target.mention}." if changed else f"ℹ️ {target.mention} n'avait pas d'accès délégué."
        await announce_player_log(i.guild, target, f"Accès /admin {'accordé' if self.mode == 'grant' else 'retiré'} par {i.user.display_name}", category="Administration")
        await i.response.edit_message(content=text, view=AdminAccessView())

class AdminAccessPickView(discord.ui.View):
    def __init__(self, mode: str):
        super().__init__(timeout=180)
        self.add_item(AdminAccessSelect(mode))

class AdminAccessView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        add = discord.ui.Button(label="Ajouter un joueur", emoji="➕", style=discord.ButtonStyle.success)
        remove = discord.ui.Button(label="Retirer un joueur", emoji="➖", style=discord.ButtonStyle.danger)
        listing = discord.ui.Button(label="Voir les accès", emoji="👥", style=discord.ButtonStyle.secondary)
        async def add_cb(i):
            if not _native_admin_ok(i):
                await i.response.send_message("❌ Seul un administrateur Discord peut gérer les accès `/admin`.", ephemeral=True); return
            await i.response.edit_message(content="➕ Sélectionne le joueur à autoriser.", view=AdminAccessPickView('grant'))
        async def remove_cb(i):
            if not _native_admin_ok(i):
                await i.response.send_message("❌ Seul un administrateur Discord peut gérer les accès `/admin`.", ephemeral=True); return
            await i.response.edit_message(content="➖ Sélectionne le joueur dont tu veux retirer l'accès.", view=AdminAccessPickView('revoke'))
        async def list_cb(i):
            if not _native_admin_ok(i):
                await i.response.send_message("❌ Seul un administrateur Discord peut gérer les accès `/admin`.", ephemeral=True); return
            ids = ADMIN_STORE.list_admin_access(i.guild.id)
            text = "👥 **Joueurs autorisés à utiliser `/admin`**\n" + ("\n".join(f"• <@{uid}>" for uid in ids) if ids else "*Aucun accès délégué.*")
            await i.response.edit_message(content=text, view=AdminAccessView())
        add.callback=add_cb; remove.callback=remove_cb; listing.callback=list_cb
        self.add_item(add); self.add_item(remove); self.add_item(listing)

class AdminProfileStatModal(discord.ui.Modal):
    LABELS = {
        'tavern_drinks': 'Consommations Taverne',
        'criminal_successes': 'Méfaits réussis Ruelle',
        'arena_rating': 'Cote Arène',
        'arena_champion_wins': 'Victoires Champion',
        'casino_wins': 'Victoires Casino / fidélité',
    }
    def __init__(self, target_id: int, stat: str):
        super().__init__(title=f"Modifier • {self.LABELS[stat]}")
        self.target_id=int(target_id); self.stat=stat
        self.value=discord.ui.TextInput(label=self.LABELS[stat],placeholder="Nouvelle valeur (0 ou plus)",max_length=9)
        self.add_item(self.value)
    async def on_submit(self,i: discord.Interaction):
        if not await _admin_guard(i): return
        try: value=int(str(self.value.value).replace(' ',''))
        except ValueError:
            await i.response.send_message("❌ Valeur invalide.",ephemeral=True); return
        if value < 0:
            await i.response.send_message("❌ La valeur ne peut pas être négative.",ephemeral=True); return
        old,new=ADMIN_STORE.set_profile_stat(self.target_id,self.stat,value)
        ADMIN_STORE.log(i.user.id,self.target_id,'profile_stat',f'{self.stat}: {old}->{new}')
        member=await _get_member(i,self.target_id)
        if member:
            await announce_player_log(i.guild,member,f"Profil modifié par {i.user.display_name}",category="Administration",details=f"{self.LABELS[self.stat]} : {old} → {new}")
        await i.response.send_message(f"✅ **{self.LABELS[self.stat]}** : {old} → **{new}**.",ephemeral=True)

class AdminReputationView(discord.ui.View):
    def __init__(self,target_id:int):
        super().__init__(timeout=180); self.target_id=int(target_id)
        specs=[
            ('tavern_drinks','Taverne','🍺'),('criminal_successes','Ruelle','🐺'),
            ('arena_rating','Cote Arène','⚔️'),('arena_champion_wins','Champion','👑'),('casino_wins','Casino','🎰')]
        for stat,label,emoji in specs:
            b=discord.ui.Button(label=label,emoji=emoji,style=discord.ButtonStyle.secondary)
            async def cb(i,st=stat):
                if await _admin_guard(i): await i.response.send_modal(AdminProfileStatModal(self.target_id,st))
            b.callback=cb; self.add_item(b)
        back=discord.ui.Button(label='Retour fiche',emoji='↩️',style=discord.ButtonStyle.primary)
        async def back_cb(i):
            if not await _admin_guard(i): return
            await show_admin_player_profile(i,self.target_id)
        back.callback=back_cb; self.add_item(back)

async def _admin_profile_embed(interaction: discord.Interaction, target_id: int) -> discord.Embed:
    member=await _get_member(interaction,target_id)
    name=member.display_name if member else f'Joueur {target_id}'
    p=CASTLE_STORE.profile(target_id); lvl,cur,need=level_from_xp(p['xp']); bal=ECONOMY.get_balance(target_id)
    arena=ARENA_STORE.progress(target_id); tav=TAVERN_STORE.tavern_reputation(target_id)
    criminal=DARK_STORE.criminal_reputation(target_id); casino=CASINO_STORE.loyalty(target_id)
    achievements=len(ACHIEVEMENT_STORE.unlocked_keys(target_id))
    e=discord.Embed(title=f'👤 Administration joueur — {name}',description=f'**ID Discord :** `{target_id}`\n⭐ **Niveau {lvl}** • XP **{cur}/{need}**',color=discord.Color.dark_gold())
    if member: e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name='💰 Économie',value=f'Poche : **{bal.wallet:,} Gold**\nBanque : **{bal.bank:,} Gold**\nTotal : **{bal.wallet+bal.bank:,} Gold**'.replace(',',' '),inline=True)
    e.add_field(name='🏰 Activité',value=f'Combats : **{p["combats"]}** • {p["wins"]} V / {p["losses"]} D\nExpéditions : **{p["expeditions"]}**\nCasino : **{p["casino_games"]}**\nQuêtes : **{p["quests_completed"]}**',inline=True)
    e.add_field(name='🏆 Progression',value=f'Succès : **{achievements}**\nMembre depuis : **{str(p["member_since"])[:10]}**',inline=True)
    e.add_field(name='🍺 Taverne',value=f'**{tav["label"]}**\n{tav["drinks"]} consommation(s)',inline=True)
    e.add_field(name='🐺 Ruelle',value=f'**{criminal["label"]}**\n{criminal["successes"]} méfait(s)',inline=True)
    e.add_field(name='🎰 Casino',value=f'**{casino["label"]}**\n{casino["wins"]} victoire(s)',inline=True)
    e.add_field(name='⚔️ Arène',value=f'Rang **{arena["rank"]}** • cote **{arena["rating"]}**\nChampion niv. **{arena["champion_level"]}/10** • {arena["champion_wins"]} victoire(s)',inline=False)
    notes=ADMIN_STORE.notes(target_id,3)
    if notes:
        e.add_field(name='📝 Notes staff privées',value='\n'.join(f'• {str(n["note"])[:120]}' for n in notes),inline=False)
    e.set_footer(text='Altherya Admin • Fiche joueur • Les boutons ci-dessous modifient directement ce joueur')
    return e

async def show_admin_player_profile(interaction: discord.Interaction,target_id:int):
    embed=await _admin_profile_embed(interaction,int(target_id))
    view=AdminPlayerProfileView(int(target_id))
    if interaction.response.is_done():
        await interaction.edit_original_response(content=None,embed=embed,view=view)
    else:
        await interaction.response.edit_message(content=None,embed=embed,view=view)


class AdminStaffNoteModal(discord.ui.Modal):
    def __init__(self,target_id:int):
        super().__init__(title='Note staff privée'); self.target_id=int(target_id)
        self.note=discord.ui.TextInput(label='Note',style=discord.TextStyle.paragraph,placeholder='Ex: remboursement manuel après bug...',max_length=1000)
        self.add_item(self.note)
    async def on_submit(self,i):
        if not await _admin_guard(i): return
        ADMIN_STORE.add_note(self.target_id,i.user.id,self.note.value)
        await i.response.send_message('✅ Note staff ajoutée à la fiche du joueur.',ephemeral=True)

class AdminPlayerHistoryView(discord.ui.View):
    def __init__(self,target_id:int):
        super().__init__(timeout=180); self.target_id=int(target_id)
        back=discord.ui.Button(label='Retour fiche',emoji='↩️',style=discord.ButtonStyle.primary)
        async def cb(i):
            if await _admin_guard(i): await show_admin_player_profile(i,self.target_id)
        back.callback=cb; self.add_item(back)

async def show_admin_player_history(i: discord.Interaction,target_id:int):
    member=await _get_member(i,target_id); name=member.display_name if member else str(target_id)
    rows=ADMIN_STORE.recent_audit(target_id,10)
    lines=[]
    labels={'gold_add':'Gold ajouté','gold_remove':'Gold retiré','level_adjust':'Niveau modifié','profile_stat':'Profil modifié','staff_note':'Note staff','mute_temp':'Mute temporaire','mute_perm':'Mute permanent','unmute':'Unmute','kick':'Kick','ban':'Ban'}
    for r in rows:
        when=str(r['created_at'])[5:16].replace('T',' '); action=labels.get(str(r['action']),str(r['action']).replace('_',' ').title())
        detail=(str(r['details'] or '')[:90])
        lines.append(f'`{when}` **{action}** par <@{int(r["admin_id"])}>\n↳ {detail or "—"}')
    e=discord.Embed(title=f'📜 Historique administratif — {name}',description='\n\n'.join(lines) if lines else '*Aucune action administrative enregistrée.*',color=discord.Color.dark_gold())
    if member: e.set_thumbnail(url=member.display_avatar.url)
    e.set_footer(text='Altherya Admin • Traçabilité staff')
    await i.response.edit_message(content=None,embed=e,view=AdminPlayerHistoryView(target_id))

class AdminPlayerProfileView(discord.ui.View):
    def __init__(self,target_id:int):
        super().__init__(timeout=300); self.target_id=int(target_id)
        specs=[('money','Économie','💰',discord.ButtonStyle.success),('level','Progression','📈',discord.ButtonStyle.primary),('reputation','Réputations','⭐',discord.ButtonStyle.primary),('items','Inventaire','🎒',discord.ButtonStyle.secondary),('success','Succès','🏆',discord.ButtonStyle.secondary),('history','Historique','📜',discord.ButtonStyle.secondary),('note','Note staff','📝',discord.ButtonStyle.secondary),('moderation','Modération','🛡️',discord.ButtonStyle.danger)]
        for action,label,emoji,style in specs:
            b=discord.ui.Button(label=label,emoji=emoji,style=style)
            async def cb(i,a=action):
                if not await _admin_guard(i): return
                if a=='money': view=AdminMoneyView(self.target_id); text='💰 **Modifier le Gold**'
                elif a=='level': view=AdminLevelView(self.target_id); text='📈 **Modifier le niveau**'
                elif a=='reputation': view=AdminReputationView(self.target_id); text='⭐ **Modifier les réputations / progression**\nTaverne • Ruelle • Arène • Champion • Fidélité Casino.'
                elif a=='items': view=AdminItemView(self.target_id); text='🎒 **Modifier les items / équipements**'
                elif a=='moderation': view=AdminModerationView(self.target_id); text='🛡️ **Modération du joueur**'
                elif a=='history':
                    await show_admin_player_history(i,self.target_id); return
                elif a=='note':
                    await i.response.send_modal(AdminStaffNoteModal(self.target_id)); return
                else:
                    view=AdminSuccessActionForPlayerView(self.target_id); text='🏆 **Modifier les succès**'
                await i.response.edit_message(content=text,embed=None,view=view)
            b.callback=cb; self.add_item(b)
        back=discord.ui.Button(label='Joueurs',emoji='↩️',style=discord.ButtonStyle.secondary)
        async def back_cb(i):
            if await _admin_guard(i): await i.response.edit_message(content='👥 **Administration des joueurs**\nSélectionne un joueur pour ouvrir sa fiche complète.',embed=None,view=AdminPlayersView())
        back.callback=back_cb; self.add_item(back)

class AdminSuccessActionForPlayerView(discord.ui.View):
    def __init__(self,target_id:int):
        super().__init__(timeout=180); self.target_id=int(target_id)
        u=discord.ui.Button(label='Débloquer',emoji='🏆',style=discord.ButtonStyle.success)
        r=discord.ui.Button(label='Supprimer',emoji='🗑️',style=discord.ButtonStyle.danger)
        async def uc(i):
            if await _admin_guard(i): await i.response.edit_message(content='🏆 Choisis le succès à débloquer.',view=AdminAchievementView(self.target_id,'unlock'))
        async def rc(i):
            if await _admin_guard(i): await i.response.edit_message(content='🗑️ Choisis le succès à retirer.',view=AdminAchievementView(self.target_id,'remove'))
        u.callback=uc; r.callback=rc; self.add_item(u); self.add_item(r)

class AdminPlayerProfileSelect(discord.ui.UserSelect):
    def __init__(self): super().__init__(placeholder='Sélectionner un joueur...',min_values=1,max_values=1)
    async def callback(self,i):
        if not await _admin_guard(i): return
        await show_admin_player_profile(i,int(self.values[0].id))

class AdminPlayersView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300); self.add_item(AdminPlayerProfileSelect())
        back=discord.ui.Button(label='Retour catégories',emoji='↩️',style=discord.ButtonStyle.secondary)
        async def cb(i):
            if await _admin_guard(i): await i.response.edit_message(content=None,embed=admin_home_embed(),view=AdminPanelView())
        back.callback=cb; self.add_item(back)

class AdminServerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        specs=[('events','Événements','🎉'),('cooldowns','Cooldowns','⏱️'),('access','Accès /admin','👥')]
        for action,label,emoji in specs:
            b=discord.ui.Button(label=label,emoji=emoji,style=discord.ButtonStyle.primary if action!='access' else discord.ButtonStyle.secondary)
            async def cb(i,a=action):
                if not await _admin_guard(i): return
                if a=='events': await i.response.edit_message(content='🎉 **Gestion serveur • Événements**',embed=None,view=AdminEventsView())
                elif a=='cooldowns': await i.response.edit_message(content='⏱️ **Gestion serveur • Cooldowns**',embed=None,view=AdminCooldownView())
                elif not _native_admin_ok(i): await i.response.send_message('❌ Seul un administrateur Discord peut gérer les accès `/admin`.',ephemeral=True)
                else: await i.response.edit_message(content='👥 **Gestion serveur • Accès /admin**',embed=None,view=AdminAccessView())
            b.callback=cb; self.add_item(b)
        back=discord.ui.Button(label='Retour catégories',emoji='↩️',style=discord.ButtonStyle.secondary)
        async def back_cb(i):
            if await _admin_guard(i): await i.response.edit_message(content=None,embed=admin_home_embed(),view=AdminPanelView())
        back.callback=back_cb; self.add_item(back)

def admin_home_embed():
    gold='🟢 ON' if ADMIN_STORE.event_enabled('gold_x2') else '⚫ OFF'; xp='🟢 ON' if ADMIN_STORE.event_enabled('xp_x2') else '⚫ OFF'
    cooldowns='🟢 ON' if ADMIN_STORE.cooldowns_enabled() else '🔴 OFF'; snap=ADMIN_STORE.server_snapshot()
    e=discord.Embed(title="🏰 ALTHERYA • CENTRE DE COMMANDEMENT",description="Administration centrale du royaume. **Serveur** et **Joueurs** disposent chacun de leur espace dédié.",color=discord.Color.dark_gold())
    e.add_field(name='📊 Vue d’ensemble',value=(f'Joueurs enregistrés : **{snap["players"]:,}**\nGold en circulation : **{snap["wallet"]:,}**\nGold en banque : **{snap["bank"]:,}**').replace(',',' '),inline=True)
    e.add_field(name='🛡️ Administration',value=f'Accès délégués : **{snap["admins"]}**\nActions journalisées : **{snap["audit"]}**\nCooldowns : **{cooldowns}**',inline=True)
    e.add_field(name='🖥️ SERVEUR',value=f'Événements • cooldowns • accès staff • supervision\nGold x2 **{gold}** • XP x2 **{xp}**',inline=False)
    e.add_field(name='👥 JOUEURS',value='Fiche complète • économie • progression • réputations • inventaire • succès • historique • notes staff • modération.',inline=False)
    e.set_footer(text='Altherya Admin • Centre de commandement • Actions sensibles journalisées')
    return e

class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        server=discord.ui.Button(label='Serveur',emoji='🖥️',style=discord.ButtonStyle.primary)
        players=discord.ui.Button(label='Joueurs',emoji='👥',style=discord.ButtonStyle.success)
        async def server_cb(i):
            if await _admin_guard(i): await i.response.edit_message(content='🖥️ **ADMINISTRATION SERVEUR**',embed=None,view=AdminServerView())
        async def players_cb(i):
            if await _admin_guard(i): await i.response.edit_message(content='👥 **ADMINISTRATION DES JOUEURS**\nSélectionne un joueur pour ouvrir sa fiche complète.',embed=None,view=AdminPlayersView())
        server.callback=server_cb; players.callback=players_cb; self.add_item(server); self.add_item(players)


def _player_profile_embed(member: discord.Member) -> discord.Embed:
    uid = member.id
    bal = ECONOMY.get_balance(uid)
    castle = CASTLE_STORE.profile(uid)
    level = level_from_xp(int(castle.get("xp", 0)))[0]
    tav = TAVERN_STORE.tavern_reputation(uid)
    criminal = DARK_STORE.criminal_reputation(uid)
    casino = CASINO_STORE.loyalty(uid)
    arena = ARENA_STORE.progress(uid)
    unlocked = len(ACHIEVEMENT_STORE.unlocked_keys(uid))
    gear = EXPEDITION_STORE.get_gear(uid)
    active = EXPEDITION_STORE.active_run(uid)
    e = discord.Embed(
        title=f"⚔️ {member.display_name} • Chronique d’Altherya",
        description=f"**Niveau {level}** • {int(castle.get('xp',0)):,} XP\nUn habitant d’Elyndor dont les actes façonnent peu à peu sa légende.".replace(',', ' '),
        color=discord.Color.dark_gold(),
    )
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="💰 Fortune", value=f"Poche **{bal.wallet:,}** Gold\nBanque **{bal.bank:,}** Gold".replace(',', ' '), inline=True)
    e.add_field(name="🏆 Parcours", value=f"⚔️ {int(castle.get('combats',0))} combats\n🏅 {int(castle.get('wins',0))} victoires\n🧭 {int(castle.get('expeditions',0))} expéditions\n✨ {unlocked} succès", inline=True)
    e.add_field(name="⭐ Réputations", value=(f"🍺 Taverne : **{tav.get('label','Inconnu')}**\n🌑 Ruelle : **{criminal.get('label','Inconnu')}**\n🎰 Casino : **{casino.get('label','Visiteur')}**\n⚔️ Arène : **{arena.get('rank','Bronze')}** ({arena.get('rating',0)})"), inline=False)
    e.add_field(name="🎒 Équipement", value=f"⛏️ Pioche niv. **{gear.pickaxe_level}** • 🪓 Hache niv. **{gear.axe_level}** • 🗡️ Lance niv. **{gear.spear_level}** • 🎒 Sac niv. **{gear.bag_level}**", inline=False)
    if active:
        zone = EXPEDITIONS.get(active.expedition_key, {})
        state = "terminée, à récupérer" if active.finished else f"encore {format_duration(active.remaining_seconds)}"
        e.add_field(name="🧭 Expédition", value=f"{zone.get('emoji','🗺️')} **{zone.get('name','Terres sauvages')}** — {state}", inline=False)
    e.set_footer(text="Altherya • Ta légende appartient au monde d’Elyndor")
    return e

@bot.tree.command(name="profil", description="Affiche ta fiche d’aventurier Altherya")
async def profil(interaction: discord.Interaction, joueur: discord.Member | None = None):
    # ACK immédiat : la construction du profil touche plusieurs stores et peut dépasser
    # la fenêtre Discord de 3 secondes. Si un middleware a déjà acquitté l'interaction,
    # on réutilise simplement le followup au lieu de répondre une seconde fois (40060).
    if not interaction.response.is_done():
        try:
            await interaction.response.defer(thinking=True)
        except discord.HTTPException:
            pass
    member = joueur or interaction.user
    if not isinstance(member, discord.Member):
        await interaction.followup.send("❌ Profil indisponible.", ephemeral=True)
        return
    embed = _player_profile_embed(member)
    await interaction.followup.send(embed=embed, ephemeral=False)

@bot.tree.command(name="admin", description="Ouvre le panneau d'administration de Altherya")
async def admin(interaction: discord.Interaction):
    # V1.67.2 — ACK immédiat : évite les 10062/40060 si SQLite ou Discord prend > 3 s.
    if interaction.guild is None:
        await interaction.response.send_message("❌ Cette commande doit être utilisée dans un serveur.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)

    # IMPORTANT : aucun has_permissions(administrator=True) Discord ici.
    # L'accès est décidé par _admin_ok : administrateur Discord OU joueur délégué.
    if not _admin_ok(interaction):
        await interaction.followup.send("❌ Ce panneau est réservé aux **administrateurs autorisés**.", ephemeral=True)
        return

    await interaction.followup.send(embed=admin_home_embed(), view=AdminPanelView(), ephemeral=True)

@admin.error
async def admin_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # Réponse sûre : ne jamais acquitter deux fois la même interaction.
    msg = "❌ Impossible d'ouvrir `/admin`."
    if isinstance(error, app_commands.CheckFailure):
        msg = "❌ Ce panneau est réservé aux **administrateurs autorisés**."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except (discord.NotFound, discord.HTTPException):
        pass
    if not isinstance(error, app_commands.CheckFailure):
        raise error

@bot.tree.command(name="succes", description="Définit le salon public des succès et résultats de jeux de Altherya")
@app_commands.checks.has_permissions(manage_guild=True)
async def succes(interaction: discord.Interaction):
    """Configure le salon public dans lequel les succès seront annoncés."""
    if interaction.guild is None or interaction.channel is None:
        await interaction.response.send_message("❌ Cette commande doit être utilisée dans un serveur.", ephemeral=True)
        return
    ACHIEVEMENT_STORE.set_channel(interaction.guild.id, interaction.channel.id)
    await interaction.response.send_message(
        f"✅ Ce salon devient le **salon officiel des succès et des résultats de jeux** de Altherya.",
        ephemeral=True,
    )
    await interaction.channel.send(embed=achievements_setup_embed())

@succes.error
async def succes_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ Seul un administrateur disposant de **Gérer le serveur** peut configurer le salon des succès."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return
    raise error


@bot.tree.command(name="logs", description="Définit le salon privé des logs complets de Altherya")
@app_commands.checks.has_permissions(manage_guild=True)
async def logs(interaction: discord.Interaction):
    if interaction.guild is None or interaction.channel is None:
        await interaction.response.send_message("❌ Cette commande doit être utilisée dans un serveur.", ephemeral=True)
        return
    ACHIEVEMENT_STORE.set_log_channel(interaction.guild.id, interaction.channel.id)
    await interaction.response.send_message("✅ Ce salon devient le **salon des logs complets** de Altherya.", ephemeral=True)
    embed = discord.Embed(
        title="📋 Logs Altherya activés",
        description=(
            "Ce salon reçoit les actions détaillées des joueurs : achats, ventes, banque, Forge, expéditions, "
            "mouvements de Gold, casino, succès et actions administratives reliées au bot.\n\n"
            "⚠️ Ce salon contient des informations privées de jeu : il est conseillé de le rendre visible uniquement au staff."
        ),
        color=discord.Color.dark_grey(),
    )
    embed.set_footer(text="Altherya • Journal administrateur")
    await interaction.channel.send(embed=embed)

@logs.error
async def logs_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ Seul un administrateur disposant de **Gérer le serveur** peut configurer le salon des logs."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return
    raise error



async def publish_gazette(guild: discord.Guild, config: dict, now_ts: int | None = None) -> bool:
    """Publie uniquement des faits réellement présents dans la BDD Altherya."""
    now_ts = int(now_ts or __import__('time').time())
    since_ts = int(config.get('last_published_at') or (now_ts - 24 * 3600))
    channel_id = int(config['channel_id'])
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
        return False

    member_cache = {}
    def name_for(uid: int) -> str:
        if uid in member_cache:
            return member_cache[uid]
        member = guild.get_member(uid)
        name = member.display_name if member else f"Habitant #{str(uid)[-4:]}"
        member_cache[uid] = name
        return name

    items = GAZETTE_STORE.build_items(since_ts, now_ts, name_for, max_alcohol=4)
    embed = discord.Embed(
        title="📰 LA GAZETTE DE LEGACY",
        description="*Les nouvelles réellement survenues dans les Trois Terres depuis la dernière édition.*",
        color=discord.Color.from_rgb(176, 132, 67),
    )
    if not items:
        embed.add_field(name="🌤️ Une journée étonnamment calme", value="Aucun fait suffisamment marquant n'a été enregistré depuis la dernière édition.", inline=False)
    else:
        for title, text in items[:7]:
            embed.add_field(name=title, value=text, inline=False)
    embed.set_footer(text="Altherya • Gazette quotidienne • Aucun événement inventé")
    try:
        await channel.send(embed=embed)
        GAZETTE_STORE.mark_published(guild.id, datetime.now().date().isoformat(), now_ts)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


@tasks.loop(seconds=30)
async def gazette_clock():
    # Heure locale de la machine serveur, conformément au reste de Altherya : aucune dépendance timezone.
    now = datetime.now()
    if now.hour < 9:
        return
    today = now.date().isoformat()
    for config in GAZETTE_STORE.configs():
        if str(config.get('last_published_day') or '') == today:
            continue
        guild = bot.get_guild(int(config['guild_id']))
        if guild is not None:
            await publish_gazette(guild, config)


@gazette_clock.before_loop
async def before_gazette_clock():
    await bot.wait_until_ready()


@bot.tree.command(name="gazette", description="Définit ce salon comme salon de la Gazette quotidienne de Altherya")
@app_commands.checks.has_permissions(manage_guild=True)
async def gazette(interaction: discord.Interaction):
    if interaction.guild is None or interaction.channel is None:
        await interaction.response.send_message("❌ Cette commande doit être utilisée dans un serveur.", ephemeral=True)
        return
    GAZETTE_STORE.configure(interaction.guild.id, interaction.channel.id)
    await interaction.response.send_message(
        f"✅ {interaction.channel.mention} devient le **salon officiel de la Gazette de Altherya**.\n"
        "🕘 Une édition sera publiée automatiquement **tous les jours à 09:00 (heure locale du serveur)**.\n"
        "📌 La Gazette utilisera uniquement des événements réellement enregistrés par Altherya.", ephemeral=True)
    embed = discord.Embed(title="📰 La Gazette de Altherya s'installe ici !",
                          description="Dès demain matin, retrouvez les exploits, catastrophes et lendemains difficiles des habitants de Altherya.",
                          color=discord.Color.from_rgb(176,132,67))
    embed.set_footer(text="Rendez-vous à 09:00")
    await interaction.channel.send(embed=embed)


@gazette.error
async def gazette_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ Seul un administrateur disposant de **Gérer le serveur** peut configurer la Gazette."
        if interaction.response.is_done(): await interaction.followup.send(msg, ephemeral=True)
        else: await interaction.response.send_message(msg, ephemeral=True)
        return
    raise error


@bot.tree.command(name="altherya", description="Installe ou déplace la carte du monde permanente de Altherya dans ce salon")
@app_commands.checks.has_permissions(manage_guild=True)
async def altherya(interaction: discord.Interaction):
    """Installe ou déplace le Hub public d'Altherya.

    V1.66.2 : Discord exige qu'une interaction soit acquittée en quelques
    secondes. L'acquittement est donc la toute première opération du callback.
    Les interactions devenues invalides (10062 / Unknown Interaction) sont
    ignorées proprement afin d'éviter une seconde erreur trompeuse.
    """
    # IMPORTANT : aucune I/O, aucun accès disque et aucun traitement ne doit
    # précéder cet ACK. C'est volontairement la première opération asynchrone.
    try:
        await interaction.response.defer(ephemeral=True, thinking=True)
    except discord.NotFound as exc:
        # 10062 = interaction déjà expirée/inconnue côté Discord. Une telle
        # interaction ne peut plus recevoir de réponse : on journalise puis on
        # quitte proprement sans faire remonter une fausse CommandNotFound.
        if getattr(exc, "code", None) == 10062:
            created = getattr(interaction, "created_at", None)
            age = None
            try:
                age = (discord.utils.utcnow() - created).total_seconds() if created else None
            except Exception:
                pass
            age_txt = f" (âge ≈ {age:.2f}s)" if age is not None else ""
            print(f"[ALTHERYA /altherya] Interaction Discord expirée avant ACK{age_txt}; commande abandonnée proprement.")
            return
        raise

    if interaction.guild is None or interaction.channel is None:
        try:
            await interaction.edit_original_response(content="❌ Cette commande doit être utilisée dans un serveur.")
        except (discord.NotFound, discord.HTTPException):
            pass
        return

    old = _load_hub_state()

    # Supprime l'ancien Hub s'il existe. Un ancien message inaccessible ne doit
    # jamais empêcher l'installation du nouveau Hub.
    try:
        old_channel_id = old.get("channel_id")
        old_message_id = old.get("message_id")
        if old_channel_id and old_message_id:
            old_channel = bot.get_channel(int(old_channel_id))
            if old_channel is None:
                old_channel = await asyncio.wait_for(
                    bot.fetch_channel(int(old_channel_id)), timeout=8.0
                )
            old_message = await asyncio.wait_for(
                old_channel.fetch_message(int(old_message_id)), timeout=8.0
            )
            await asyncio.wait_for(old_message.delete(), timeout=8.0)
    except asyncio.TimeoutError:
        print("[ALTHERYA /altherya] Timeout pendant la suppression de l'ancien Hub ; installation poursuivie.")
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError) as exc:
        print(f"[ALTHERYA /altherya] Ancien Hub ignoré : {type(exc).__name__}: {exc}")

    # Publie le nouveau Hub avec une limite de temps. En cas d'échec, on rend
    # toujours la main à Discord avec un diagnostic au lieu de laisser tourner
    # « réfléchit… » sans fin.
    try:
        message = await asyncio.wait_for(_publish_hub(interaction.channel), timeout=20.0)
        _save_hub_state(interaction.guild.id, interaction.channel.id, message.id)
        await asyncio.wait_for(
            interaction.edit_original_response(
                content=f"✅ **Carte du monde de Altherya installée.** Il restera fixe dans {interaction.channel.mention}.\n"
                        "Les joueurs peuvent maintenant naviguer chacun dans leur propre interface privée."
            ),
            timeout=10.0,
        )
    except asyncio.TimeoutError:
        print("[ALTHERYA /altherya] ERREUR : timeout pendant la publication du Hub.")
        try:
            await interaction.edit_original_response(
                content="❌ **Le Hub Altherya n'a pas pu être publié : délai d'attente dépassé.**\n"
                        "La commande a été arrêtée proprement au lieu de rester bloquée. "
                        "Consulte les logs du conteneur pour identifier l'étape qui ne répond pas."
            )
        except (discord.HTTPException, discord.NotFound):
            pass
    except Exception as exc:
        print(f"[ALTHERYA /altherya] ERREUR publication Hub : {type(exc).__name__}: {exc}")
        try:
            await interaction.edit_original_response(
                content=f"❌ **Impossible d'installer le Hub Altherya.**\n"
                        f"Erreur : `{type(exc).__name__}: {str(exc)[:700]}`"
            )
        except (discord.HTTPException, discord.NotFound):
            pass

@altherya.error
async def altherya_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ Seul un administrateur disposant de **Gérer le serveur** peut installer ou déplacer le Hub Altherya."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.NotFound as exc:
            if getattr(exc, "code", None) != 10062:
                raise
        return

    # Si Discord a déjà invalidé l'interaction (10062), la commande ne peut
    # plus répondre. On absorbe uniquement ce cas précis au lieu de générer
    # une cascade d'erreurs dans le gestionnaire de commandes.
    if isinstance(error, app_commands.CommandInvokeError):
        original = getattr(error, "original", None)
        if isinstance(original, discord.NotFound) and getattr(original, "code", None) == 10062:
            print("[ALTHERYA /altherya] Unknown Interaction (10062) absorbée par le gestionnaire d'erreur.")
            return
    raise error

async def _oddium_bridge_event(event: dict):
    """Route Oddium audit/results into Altherya's configured channels."""
    guild = bot.get_guild(int(GUILD_ID)) if GUILD_ID else (bot.guilds[0] if bot.guilds else None)
    if guild is None:
        return
    user_id = int(event.get("user_id") or 0)
    if not user_id:
        return
    user = guild.get_member(user_id) or bot.get_user(user_id)
    if user is None:
        try:
            user = await bot.fetch_user(user_id)
        except (discord.NotFound, discord.HTTPException):
            user = user_id

    kind = str(event.get("type") or "")
    stake = int(event.get("stake") or 0)
    home = str(event.get("home_team") or "")
    away = str(event.get("away_team") or "")
    combo_count = int(event.get("combo_count") or 0)

    if kind == "bet_placed":
        if combo_count:
            action = f"a parié **{stake:,} Gold** sur un combiné de **{combo_count} matchs**".replace(",", " ")
            details = f"Cote totale : **{float(event.get('odd') or 0):.2f}**"
        else:
            action = f"a parié **{stake:,} Gold** sur le match **{home} - {away}**".replace(",", " ")
            details = f"Ticket : **{event.get('reference', 'Oddium')}**"
        await announce_player_log(guild, user, action, category="Administrateur", details=details)
        return

    if kind != "ticket_settled":
        return
    status = str(event.get("status") or "")
    payout = int(event.get("payout") or 0)
    is_combo = bool(event.get("is_combo") or event.get("combo_id"))
    game = f"Oddium — Combiné ×{combo_count or 'multi'}" if is_combo else f"Oddium — {home} - {away}"
    mention = getattr(user, "mention", f"<@{user_id}>")
    channel_id = ACHIEVEMENT_STORE.get_channel(guild.id)
    if not channel_id:
        return
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        if status == "WON":
            title = "🎲 GAIN DE JEU"
            description = f"{mention} **gagne {payout:,} Gold**.\n**Jeu :** {game}".replace(",", " ")
            color = discord.Color.green()
        elif status == "LOST":
            title = "🎲 PERTE DE JEU"
            description = f"{mention} **perd {stake:,} Gold**.\n**Jeu :** {game}".replace(",", " ")
            color = discord.Color.red()
        else:
            title = "♻️ REMBOURSEMENT DE JEU"
            description = f"{mention} **récupère {payout or stake:,} Gold**.\n**Jeu :** {game}".replace(",", " ")
            color = discord.Color.light_grey()
        e = discord.Embed(title=title, description=description, color=color)
        avatar = getattr(getattr(user, "display_avatar", None), "url", None)
        if avatar:
            e.set_thumbnail(url=avatar)
        e.set_footer(text="Altherya • Résultats publics")
        await channel.send(embed=e)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
        pass


_COMMAND_TREE_SYNCED = False



async def _altherya_setup_hook():
    """Synchronise l'arbre applicatif avant la connexion au Gateway.

    V2.02 : la synchro dans on_ready() pouvait laisser Discord afficher une
    commande distante alors que l'arbre de l'instance n'était pas encore dans
    un état déterministe au moment des premières interactions. setup_hook est
    le point prévu par discord.py pour cette initialisation.
    """
    global _COMMAND_TREE_SYNCED
    local_names = sorted(command.name for command in bot.tree.get_commands())
    print(f"[COMMANDES] Arbre local chargé ({len(local_names)}) : {', '.join(local_names)}")
    if bot.tree.get_command("altherya") is None:
        raise RuntimeError("Commande critique /altherya absente de l'arbre local avant synchronisation")

    try:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            scope = f"serveur {GUILD_ID}"
        else:
            synced = await bot.tree.sync()
            scope = "global"
        synced_names = sorted(command.name for command in synced)
        _COMMAND_TREE_SYNCED = True
        print(f"✅ Commandes {scope} synchronisées ({len(synced_names)}) : {', '.join(synced_names)}")
        if "altherya" not in synced_names:
            raise RuntimeError("Discord n'a pas retourné /altherya après la synchronisation")
        print("✅ /altherya confirmée dans l'arbre Discord synchronisé")
    except Exception as exc:
        _COMMAND_TREE_SYNCED = False
        print(f"❌ Synchronisation des commandes au démarrage : {type(exc).__name__}: {exc}")
        raise


# discord.py appelle setup_hook une seule fois, avant on_ready et avant le
# traitement normal des interactions Gateway. Affectation volontaire à
# l'instance afin de conserver l'architecture historique du projet.
bot.setup_hook = _altherya_setup_hook


@tasks.loop(seconds=3)
async def shared_economy_event_worker():
    if not shared_economy_enabled():
        return
    for event_id, payload in await asyncio.to_thread(pending_events, 25):
        try:
            await _oddium_bridge_event(payload)
            await asyncio.to_thread(mark_event_processed, event_id)
        except Exception as exc:
            print(f"[ECONOMIE COMMUNE] événement {event_id} en attente: {type(exc).__name__}: {exc}")
            break



# ============================================================
# V2.11 — NO-SELECT UI OVERRIDES
# Toute sélection visible passe par boutons/pagination ou modal ID.
# Les anciennes classes Select restent uniquement comme adaptateurs de logique
# et ne sont jamais ajoutées à une View utilisateur.
# ============================================================
_LegacyTavernDrinkSelect = TavernDrinkSelect
_LegacyMarketSellSelect = MarketSellSelect
_LegacyArenaFriendUserSelect = ArenaFriendUserSelect
_LegacyChampionClassSelect = ChampionClassSelect
_LegacyFriendClassSelect = FriendClassSelect
_LegacyThiefTargetSelect = ThiefTargetSelect
_LegacyNPCTargetSelect = NPCTargetSelect
_LegacyAdminAchievementSelect = AdminAchievementSelect
_LegacyAdminTargetSelect = AdminTargetSelect
_LegacyAdminAccessSelect = AdminAccessSelect
_LegacyAdminPlayerProfileSelect = AdminPlayerProfileSelect

async def _v211_member(guild, raw: str):
    """Résout un membre par pseudo Discord / pseudo serveur.

    L'ID reste accepté en secours pour compatibilité interne, mais les interfaces
    joueur/admin n'ont plus besoin de l'afficher ni de le demander.
    """
    if not guild:
        return None
    query = str(raw or "").strip()
    if not query:
        return None

    # Compatibilité silencieuse avec les anciens appels qui fournissent un ID.
    digits = ''.join(ch for ch in query if ch.isdigit())
    if digits == query and len(digits) >= 5:
        uid = int(digits)
        member = guild.get_member(uid)
        if member:
            return member
        try:
            return await guild.fetch_member(uid)
        except Exception:
            return None

    q = query.casefold()
    members = list(getattr(guild, "members", []) or [])

    def names(m):
        vals = [getattr(m, "display_name", ""), getattr(m, "name", "")]
        global_name = getattr(m, "global_name", None)
        if global_name:
            vals.append(global_name)
        return [str(v).strip() for v in vals if v]

    # 1) correspondance exacte : pseudo serveur, nom global ou username.
    exact = [m for m in members if any(n.casefold() == q for n in names(m))]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return ("ambiguous", exact[:10])

    # 2) début du pseudo, plus naturel pour une recherche admin rapide.
    starts = [m for m in members if any(n.casefold().startswith(q) for n in names(m))]
    if len(starts) == 1:
        return starts[0]
    if len(starts) > 1:
        return ("ambiguous", starts[:10])

    # 3) recherche partielle.
    partial = [m for m in members if any(q in n.casefold() for n in names(m))]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        return ("ambiguous", partial[:10])
    return None

class _V211MemberModal(discord.ui.Modal):
    def __init__(self, title: str, handler):
        super().__init__(title=title); self.handler=handler
        self.member=discord.ui.TextInput(
            label="Nom du joueur",
            placeholder="Ex : Mor.Gan",
            min_length=1,
            max_length=64,
        )
        self.add_item(self.member)

    async def on_submit(self, i):
        result = await _v211_member(i.guild, self.member.value)
        if isinstance(result, tuple) and result and result[0] == "ambiguous":
            matches = result[1]
            names = "\n".join(f"• **{m.display_name}** (@{m.name})" for m in matches[:8])
            return await i.response.send_message(
                "⚠️ **Plusieurs joueurs correspondent à cette recherche.**\n"
                "Précise davantage le nom :\n" + names,
                ephemeral=True,
            )
        if not result:
            return await i.response.send_message(
                f"❌ Aucun joueur trouvé pour **{self.member.value.strip()}**.\n"
                "Essaie son pseudo affiché sur le serveur ou son nom Discord.",
                ephemeral=True,
            )
        await self.handler(i, result)

class TavernDrinksView(discord.ui.View):
    def __init__(self, user_id: int | None = None):
        super().__init__(timeout=300); tier=TAVERN_STORE.tavern_reputation(user_id)["tier"] if user_id else 5
        for key,label,emoji,required in TAVERN_DRINKS:
            if tier < required: continue
            b=discord.ui.Button(label=label,emoji=emoji,style=discord.ButtonStyle.primary)
            async def cb(i,k=key):
                sel=_LegacyTavernDrinkSelect(i.user.id); sel._values=[k]; await sel.callback(i)
            b.callback=cb; self.add_item(b)
        back=discord.ui.Button(label="Retour au comptoir",emoji="↩️",style=discord.ButtonStyle.secondary)
        async def back_cb(i):
            await safe_defer(i); await edit_with_asset(i,PLACES/"tavern_barman.png","barman.png",TavernBarView(),"🍺 **Le comptoir de Altherya**\n"+tavern_reputation_content(i.user.id))
        back.callback=back_cb; self.add_item(back)

class TavernFriendSelectView(discord.ui.View):
    def __init__(self, owner_id:int, game_type:str):
        super().__init__(timeout=90); self.owner_id=int(owner_id); self.game_type=game_type
        b=discord.ui.Button(label="Rechercher un ami",emoji="🤝",style=discord.ButtonStyle.primary)
        async def cb(i):
            if i.user.id!=self.owner_id: return await i.response.send_message("Cette préparation appartient à un autre joueur.",ephemeral=True)
            async def picked(ii,m):
                if m.id==ii.user.id or m.bot: return await ii.response.send_message("❌ Choisis un autre joueur humain.",ephemeral=True)
                await ii.response.send_modal(TavernFriendBetModal(self.game_type,m.id))
            await i.response.send_modal(_V211MemberModal("Choisir l’ami",picked))
        b.callback=cb; self.add_item(b)

class MarketSellView(discord.ui.View):
    def __init__(self, owner_id:int, page:int=0):
        super().__init__(timeout=300); self.owner_id=int(owner_id); self.page=max(0,int(page))
        inv=EXPEDITION_STORE.get_resources(owner_id); items=[n for n,q in sorted(inv.items()) if RESOURCE_SELL_PRICES.get(n,0)>0]
        pages=max(1,(len(items)+4)//5); self.page=min(self.page,pages-1)
        for name in items[self.page*5:self.page*5+5]:
            qty=inv[name]; price=RESOURCE_SELL_PRICES[name]
            b=discord.ui.Button(label=f"{name} ×{qty} • {price}G/u",emoji="💰",style=discord.ButtonStyle.success)
            async def cb(i,n=name): await i.response.send_modal(ResourceSellModal(self.owner_id,n))
            b.callback=cb; self.add_item(b)
        if not items:
            self.add_item(discord.ui.Button(label="Aucune ressource vendable",disabled=True,style=discord.ButtonStyle.secondary))
        prev=discord.ui.Button(label="Précédent",emoji="◀️",style=discord.ButtonStyle.secondary,disabled=self.page<=0)
        nxt=discord.ui.Button(label="Suivant",emoji="▶️",style=discord.ButtonStyle.secondary,disabled=self.page>=pages-1)
        async def nav(i,d):
            await safe_defer(i); await edit_with_asset(i,PLACES/"market.png","marche.png",MarketSellView(self.owner_id,self.page+d),market_sell_content(self.owner_id))
        prev.callback=lambda i: nav(i,-1); nxt.callback=lambda i: nav(i,1); self.add_item(prev); self.add_item(nxt)
        back=discord.ui.Button(label="Retour au marché",emoji="↩️",style=discord.ButtonStyle.secondary)
        async def bk(i): await safe_defer(i); await edit_with_asset(i,PLACES/"market.png","marche.png",MarketView(),"🛒 **Marché de Altherya**\nQue veux-tu faire ?"+npc_alcohol_reaction(i.user.id,"marchand"))
        back.callback=bk; self.add_item(back)

class ArenaFriendSelectView(discord.ui.View):
    def __init__(self, owner_id:int):
        super().__init__(timeout=300); self.owner_id=int(owner_id)
        b=discord.ui.Button(label="Choisir l’adversaire par ID",emoji="⚔️",style=discord.ButtonStyle.danger)
        async def cb(i):
            async def picked(ii,m):
                if m.id==self.owner_id or m.bot: return await ii.response.send_message("❌ Choisis un autre joueur humain.",ephemeral=True)
                if ARENA_STORE.friend_remaining(m.id)<=0: return await ii.response.send_message(f"❌ {m.mention} a déjà utilisé ses combats amicaux du jour.",ephemeral=True)
                await ii.response.send_modal(ArenaWagerModal("friend",self.owner_id,m.id))
            await i.response.send_modal(_V211MemberModal("Choisir l’adversaire",picked))
        b.callback=cb; self.add_item(b)

_ChampionClassViewBase=ChampionClassView
class ChampionClassView(_ChampionClassViewBase):
    def __init__(self, owner_id:int, wager:int):
        super().__init__(owner_id,wager)
        for item in list(self.children):
            if isinstance(item,discord.ui.Select): self.remove_item(item)
        for key,c in CLASSES.items():
            b=discord.ui.Button(label=c['name'],emoji=c['emoji'],style=discord.ButtonStyle.primary)
            async def cb(i,k=key):
                self.class_key=k; await safe_defer(i); await edit_with_asset(i,PLACES/"arena_champion.png","champion_legacy.png",self,f"👑 **Défi du Champion**\nMise : **{_gold(self.wager)} Gold**\nClasse : {class_line(k)}\n\nQuand tu es prêt, valide le combat.")
            b.callback=cb; self.add_item(b)

_FriendLobbyViewBase=FriendLobbyView
class FriendLobbyView(_FriendLobbyViewBase):
    def __init__(self,p1:int,p2:int,wager:int):
        super().__init__(p1,p2,wager)
        for item in list(self.children):
            if isinstance(item,discord.ui.Select): self.remove_item(item)
        for key,c in CLASSES.items():
            b=discord.ui.Button(label=c['name'],emoji=c['emoji'],style=discord.ButtonStyle.primary)
            async def cb(i,k=key):
                if i.user.id not in (self.p1,self.p2): return await i.response.send_message("Tu ne participes pas à ce défi.",ephemeral=True)
                self.classes[i.user.id]=k; self.ready.discard(i.user.id); await safe_defer(i); await edit_with_asset(i,PLACES/"arena.png","arene.png",self,friend_lobby_content(self))
            b.callback=cb; self.add_item(b)

class ThiefTargetView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        b=discord.ui.Button(label="Rechercher une cible",emoji="🐺",style=discord.ButtonStyle.danger)
        async def cb(i):
            async def picked(ii,m):
                sel=_LegacyThiefTargetSelect(); sel._values=[m]; await sel.callback(ii)
            await i.response.send_modal(_V211MemberModal("Cible du vol",picked))
        b.callback=cb; self.add_item(b)

class NPCTargetView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180); sel=_LegacyNPCTargetSelect()
        for opt in sel.options:
            b=discord.ui.Button(label=opt.label,emoji="🪙",style=discord.ButtonStyle.danger)
            async def cb(i,v=opt.value):
                x=_LegacyNPCTargetSelect(); x._values=[v]; await x.callback(i)
            b.callback=cb; self.add_item(b)

class AdminAchievementView(discord.ui.View):
    def __init__(self,target_id:int,mode:str,page:int=0):
        super().__init__(timeout=180); self.target_id=int(target_id); self.mode=mode
        sel=_LegacyAdminAchievementSelect(target_id,mode); opts=list(sel.options); pages=max(1,(len(opts)+4)//5); self.page=max(0,min(page,pages-1))
        for opt in opts[self.page*5:self.page*5+5]:
            b=discord.ui.Button(label=opt.label[:75],emoji=opt.emoji,style=discord.ButtonStyle.success if mode=='unlock' else discord.ButtonStyle.danger)
            async def cb(i,v=opt.value): x=_LegacyAdminAchievementSelect(self.target_id,self.mode); x._values=[v]; await x.callback(i)
            b.callback=cb; self.add_item(b)
        prev=discord.ui.Button(label="Précédent",emoji="◀️",style=discord.ButtonStyle.secondary,disabled=self.page==0)
        nxt=discord.ui.Button(label="Suivant",emoji="▶️",style=discord.ButtonStyle.secondary,disabled=self.page>=pages-1)
        prev.callback=lambda i: i.response.edit_message(view=AdminAchievementView(self.target_id,self.mode,self.page-1))
        nxt.callback=lambda i: i.response.edit_message(view=AdminAchievementView(self.target_id,self.mode,self.page+1))
        self.add_item(prev); self.add_item(nxt)

class AdminTargetView(discord.ui.View):
    def __init__(self,action:str):
        super().__init__(timeout=180); self.action=action
        b=discord.ui.Button(label="Rechercher un joueur",emoji="👤",style=discord.ButtonStyle.primary)
        async def cb(i):
            async def picked(ii,m):
                x=_LegacyAdminTargetSelect(self.action); x._values=[m]; await x.callback(ii)
            await i.response.send_modal(_V211MemberModal("Joueur à administrer",picked))
        b.callback=cb; self.add_item(b)

class AdminAccessPickView(discord.ui.View):
    def __init__(self,mode:str):
        super().__init__(timeout=180); self.mode=mode
        b=discord.ui.Button(label="Rechercher un joueur",emoji="👥",style=discord.ButtonStyle.primary)
        async def cb(i):
            async def picked(ii,m): x=_LegacyAdminAccessSelect(self.mode); x._values=[m]; await x.callback(ii)
            await i.response.send_modal(_V211MemberModal("Accès /admin",picked))
        b.callback=cb; self.add_item(b)

# V2.25: l'écran Administration des joueurs utilise la définition native
# AdminPlayerProfileSelect/AdminPlayersView déclarée plus haut.
# Suppression de la seconde définition afin d'éviter toute route divergente.

@bot.event
async def on_ready():
    if shared_economy_enabled() and not shared_economy_event_worker.is_running():
        shared_economy_event_worker.start()
    if bot.get_cog("LegacyWorldForge") is None:
        await WORLD_FORGE.setup(bot)

    # Reprend les expéditions longues après un redémarrage Coolify.
    # Si le timer s'est terminé pendant l'arrêt, le butin est transféré automatiquement.
    for run in EXPEDITION_STORE.active_runs():
        # V1.70 : status_message_id référence l'annonce publique /succes ;
        # aucune vue de suivi personnel persistante n'est attachée à ce message.
        if run.finished:
            asyncio.create_task(refresh_expedition_status(run.run_id))
        else:
            start_expedition_monitor(run.run_id)

    bot.add_view(WorldHubView())
    if not gazette_clock.is_running():
        gazette_clock.start()
    bot.add_view(HubView())
    bot.add_view(TavernView())
    bot.add_view(TavernBarView())
    bot.add_view(TavernDrinksView())
    bot.add_view(TavernGamesView())
    bot.add_view(TroubadourView())
    bot.add_view(MarketView())
    bot.add_view(BankView())
    bot.add_view(ArenaView())
    bot.add_view(ForgeView())
    bot.add_view(DarkAlleyView())
    bot.add_view(ThiefView())
    bot.add_view(DarkAlleyPanelView())
    bot.add_view(RobberView())
    bot.add_view(HeistView())
    bot.add_view(GuardView())
    bot.add_view(BannedAlleyView())
    bot.add_view(CasinoMainView())
    bot.add_view(CastleView())
    bot.add_view(PodiumView())
    bot.add_view(CentralBoardView())
    bot.add_view(CentralBoardBackView())
    bot.add_view(QuestView())
    bot.add_view(DailyView(True))
    bot.add_view(CastleBackView())
    # Views de retour persistantes pour chaque lieu
    for key in DESTINATIONS:
        bot.add_view(PlaceView(key))
    # V2.02 : l'arbre de commandes est déjà synchronisé dans setup_hook(),
    # avant la connexion au Gateway. Ne jamais resynchroniser ici : on_ready
    # peut être rappelé après une reconnexion Discord.
    if not _COMMAND_TREE_SYNCED:
        print("⚠️ Arbre de commandes non confirmé comme synchronisé.")
    # Le message du Hub reste dans le salon entre les redémarrages.
    # On rattache simplement sa vue persistante si un Hub a déjà été installé.
    await ensure_fixed_hub()
    if RECOVERED_CASINO_GAMES:
        print(f"♻️ {RECOVERED_CASINO_GAMES} partie(s) de casino interrompue(s) remboursée(s) au démarrage")
    if RECOVERED_ARENA_BATTLES:
        print(f"♻️ {RECOVERED_ARENA_BATTLES} combat(s) interrompu(s) remboursé(s) au démarrage")
    if RECOVERED_TAVERN_GAMES:
        print(f"♻️ {RECOVERED_TAVERN_GAMES} partie(s) de taverne interrompue(s) remboursée(s) au démarrage")
    print(f"🏙️ Altherya V1 connecté : {bot.user}")

if __name__ == "__main__":
    if not TOKEN or TOKEN == "COLLE_TON_TOKEN_ICI":
        raise SystemExit("Ajoute DISCORD_TOKEN dans le fichier .env")
    bot.run(TOKEN)
