from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 720


def _font(size: int, bold: bool=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _center(draw: ImageDraw.ImageDraw, text: str, y: int, font, fill, x1: int, x2: int):
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    draw.text((x1 + ((x2 - x1) - width) / 2, y), text, font=font, fill=fill)


def render_story_book(path: str|Path, *, season:int, chapter:int, total:int, title:str, text:str|None,
                      unlocked:bool, previous_ok:bool, requirements:list[str], inventory:dict[str,int], notice:str|None=None):
    """Livre purement visuel : aucun récit ni liste d'objets en petit dans l'image.

    Le texte et les prérequis sont affichés dans le message Discord pour garantir
    leur lisibilité sur mobile. L'image conserve seulement l'identité du livre.
    """
    im = Image.new("RGB", (W, H), (48, 28, 17))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, H), fill=(48, 28, 17))
    d.ellipse((85, 62, 1115, 690), fill=(28, 17, 11))

    # Couverture et double page vieillie.
    d.rounded_rectangle((95, 55, 1105, 665), radius=34, fill=(78, 43, 24), outline=(170, 112, 53), width=7)
    d.rounded_rectangle((120, 78, 590, 640), radius=23, fill=(226, 205, 160), outline=(137, 92, 45), width=3)
    d.rounded_rectangle((610, 78, 1080, 640), radius=23, fill=(226, 205, 160), outline=(137, 92, 45), width=3)
    d.polygon([(588, 84), (612, 84), (612, 637), (588, 637)], fill=(111, 72, 38))

    # Quelques ornements larges, sans lignes de texte minuscules.
    gold = (112, 70, 28)
    ink = (49, 33, 22)
    green = (54, 94, 52)
    red = (126, 44, 34)
    muted = (103, 77, 54)
    for x in (148, 652):
        d.line((x, 145, x + 390, 145), fill=gold, width=2)
        d.line((x, 555, x + 390, 555), fill=gold, width=2)

    _center(d, f"SAISON {season}", 105, _font(30, True), gold, 135, 575)
    _center(d, f"CHAPITRE {chapter}", 205, _font(54, True), ink, 135, 575)

    # Le titre est volontairement court et très grand. S'il n'est pas encore
    # fourni, on garde simplement "Chapitre X".
    display_title = str(title or f"Chapitre {chapter}")
    if len(display_title) > 28:
        display_title = display_title[:27] + "…"
    _center(d, display_title, 300, _font(31, True), gold, 145, 565)
    _center(d, f"PAGE {chapter} / {total}", 500, _font(23, True), muted, 145, 565)

    # Page droite : état du chapitre, visible immédiatement même en miniature.
    if unlocked:
        _center(d, "DÉBLOQUÉ", 205, _font(46, True), green, 625, 1065)
        _center(d, "✦", 305, _font(88, True), gold, 625, 1065)
        _center(d, "Le Troubadour peut raconter ce chapitre", 455, _font(22, True), muted, 625, 1065)
    else:
        _center(d, "VERROUILLÉ", 205, _font(46, True), red, 625, 1065)
        # Symbole simple dessiné pour ne pas dépendre d'un glyphe emoji.
        d.rounded_rectangle((790, 330, 900, 440), radius=15, outline=red, width=12)
        d.arc((810, 270, 880, 365), 180, 360, fill=red, width=12)
        d.line((810, 318, 810, 350), fill=red, width=12)
        d.line((880, 318, 880, 350), fill=red, width=12)
        if previous_ok:
            _center(d, "Réunis les objets indiqués dans Discord", 475, _font(22, True), muted, 625, 1065)
        else:
            _center(d, "Débloque d'abord le chapitre précédent", 475, _font(22, True), muted, 625, 1065)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "PNG", optimize=True)
    return str(path)
