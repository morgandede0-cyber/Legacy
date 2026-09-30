from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter


ZONE_CROPS = {
    "forest": (846, 205, 1177, 400),
    "hills": (1180, 205, 1500, 400),
    "ruins": (846, 403, 1177, 592),
    "swamp": (1180, 403, 1500, 592),
    "desert": (846, 596, 1177, 788),
    "mountains": (1180, 596, 1500, 788),
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _fit_text(draw: ImageDraw.ImageDraw, text: str, box_width: int, start_size: int, min_size: int = 18, bold: bool = False):
    size = start_size
    while size > min_size:
        font = _font(size, bold=bold)
        if draw.textbbox((0, 0), text, font=font)[2] <= box_width:
            return font
        size -= 1
    return _font(min_size, bold=bold)


def render_expedition_live_card(
    *,
    base_image: str | Path,
    output_path: str | Path,
    expedition_key: str,
    expedition_name: str,
    duration_label: str,
    danger: str,
    tool_name: str,
    tool_level: int,
    bag_name: str,
    capacity: int,
    object1_name: str,
    object2_name: str,
) -> Path:
    """Crée l'image statique affichée pendant une expédition.

    L'image est créée une seule fois au lancement. Le timer, le compteur et les logs
    restent dans le message Discord et sont édités sans ré-uploader l'image.
    """
    base_image = Path(base_image)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    base = Image.open(base_image).convert("RGB")
    w, h = base.size

    # Fond assombri + léger flou pour conserver l'identité visuelle de l'interface.
    blurred = base.filter(ImageFilter.GaussianBlur(radius=2.2))
    overlay = Image.new("RGBA", (w, h), (5, 7, 10, 118))
    canvas = Image.alpha_composite(blurred.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(canvas)

    # Grand panneau principal.
    panel = (180, 145, w - 180, h - 115)
    draw.rounded_rectangle(panel, radius=18, fill=(15, 16, 17, 238), outline=(164, 103, 38, 255), width=5)
    inner = (205, 170, w - 205, h - 140)
    draw.rounded_rectangle(inner, radius=14, fill=(25, 22, 18, 236), outline=(92, 64, 34, 255), width=2)

    # Titre.
    title_font = _font(58, bold=True)
    subtitle_font = _font(24, bold=False)
    title = "EXPÉDITION EN COURS"
    tb = draw.textbbox((0, 0), title, font=title_font)
    tx = (w - (tb[2] - tb[0])) // 2
    draw.text((tx + 2, 188 + 2), title, font=title_font, fill=(0, 0, 0, 180))
    draw.text((tx, 188), title, font=title_font, fill=(230, 186, 111, 255))
    sub = "LEGACY  •  EXPLORER  •  RÉCOLTER  •  REVENIR"
    sb = draw.textbbox((0, 0), sub, font=subtitle_font)
    draw.text(((w - (sb[2] - sb[0])) // 2, 258), sub, font=subtitle_font, fill=(188, 142, 78, 255))

    # Carte de destination extraite du panneau d'origine.
    crop_box = ZONE_CROPS.get(expedition_key)
    if crop_box:
        zone_img = base.crop(crop_box)
        zone_img.thumbnail((485, 300), Image.Resampling.LANCZOS)
        zx, zy = 255, 330
        frame = (zx - 10, zy - 10, zx + zone_img.width + 10, zy + zone_img.height + 10)
        draw.rounded_rectangle(frame, radius=12, fill=(8, 8, 8, 255), outline=(193, 127, 46, 255), width=4)
        canvas.alpha_composite(zone_img.convert("RGBA"), dest=(zx, zy))
    else:
        zx, zy = 255, 330
        draw.rounded_rectangle((zx - 10, zy - 10, zx + 485, zy + 300), radius=12, fill=(10, 10, 10, 255), outline=(193, 127, 46, 255), width=4)

    # Colonne d'informations.
    info_x = 790
    name_font = _fit_text(draw, expedition_name.upper(), w - info_x - 250, 42, 26, bold=True)
    draw.text((info_x, 330), expedition_name.upper(), font=name_font, fill=(236, 205, 151, 255))

    label_font = _font(24, bold=True)
    value_font = _font(24)
    y = 405
    rows = [
        ("Destination", expedition_name),
        ("Durée", duration_label),
        ("Danger", danger),
        ("Outil", f"{tool_name} — Niveau {tool_level}"),
        ("Sac", f"{bag_name} — {capacity} places"),
        ("Objet 1", object1_name),
        ("Objet 2", object2_name),
    ]
    for label, value in rows:
        draw.text((info_x, y), f"{label} :", font=label_font, fill=(195, 137, 70, 255))
        val_font = _fit_text(draw, value, w - info_x - 300, 24, 18)
        draw.text((info_x + 175, y), value, font=val_font, fill=(226, 218, 198, 255))
        y += 46

    # Zone d'état en bas.
    status_box = (255, 720, w - 255, 850)
    draw.rounded_rectangle(status_box, radius=14, fill=(8, 19, 12, 245), outline=(77, 136, 75, 255), width=4)
    status_font = _font(34, bold=True)
    status = "EXPÉDITION LANCÉE"
    st = draw.textbbox((0, 0), status, font=status_font)
    draw.text(((w - (st[2] - st[0])) // 2, 742), status, font=status_font, fill=(150, 218, 133, 255))
    hint = "Le timer est mis à jour chaque minute • Les drops et les logs apparaissent en temps réel"
    hint_font = _fit_text(draw, hint, status_box[2] - status_box[0] - 60, 23, 17)
    hb = draw.textbbox((0, 0), hint, font=hint_font)
    draw.text(((w - (hb[2] - hb[0])) // 2, 798), hint, font=hint_font, fill=(205, 197, 177, 255))

    canvas.convert("RGB").save(output_path, format="PNG", optimize=True)
    return output_path
