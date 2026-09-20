"""Altherya — socle visuel Discord Components V2.

Aucun Select n'est utilisé ici. Les interfaces reposent sur Container, Section,
TextDisplay, MediaGallery, Separator, ActionRow et Button.
"""
from __future__ import annotations
import discord

BRONZE = 0xB67A2A
GOLD = 0xD6A84B
DARK = 0x2B2118
RED = 0x8C2F39
GREEN = 0x3E6B4F


def media_gallery(filename: str, description: str | None = None) -> discord.ui.MediaGallery:
    gallery = discord.ui.MediaGallery()
    gallery.add_item(media=f"attachment://{filename}", description=description or "Illustration Altherya")
    return gallery


def action_row(*buttons: discord.ui.Button) -> discord.ui.ActionRow:
    return discord.ui.ActionRow(*buttons)


def header(title: str, subtitle: str | None = None) -> discord.ui.TextDisplay:
    text = f"# {title}"
    if subtitle:
        text += f"\n*{subtitle}*"
    return discord.ui.TextDisplay(text)


def stat_line(items: list[tuple[str, str]]) -> discord.ui.TextDisplay:
    return discord.ui.TextDisplay("　•　".join(f"{emoji} **{value}**" for emoji, value in items))


def separator(big: bool = False) -> discord.ui.Separator:
    spacing = discord.SeparatorSpacing.large if big else discord.SeparatorSpacing.small
    return discord.ui.Separator(spacing=spacing)


def container(*children, colour: int = BRONZE) -> discord.ui.Container:
    return discord.ui.Container(*children, accent_colour=colour)
