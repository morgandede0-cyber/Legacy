from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

CARD_W, CARD_H = 128, 180
SUIT_SYMBOLS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
RED_SUITS = {"H", "D"}

ROULETTE_RED = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
EUROPEAN_WHEEL = [0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26]


def _font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int = 34, bold: bool = True):
    size = start_size
    while size > 12:
        f = _font(size, bold)
        if draw.textbbox((0, 0), text, font=f)[2] <= max_width:
            return f
        size -= 2
    return _font(12, bold)


def _card_value_text(card: dict) -> str:
    return str(card.get("rank", "?"))


def _draw_card(draw: ImageDraw.ImageDraw, x: int, y: int, card: dict | None, hidden: bool = False):
    radius = 14
    if hidden:
        draw.rounded_rectangle((x, y, x + CARD_W, y + CARD_H), radius=radius, fill=(28, 56, 112), outline=(221, 187, 86), width=4)
        for yy in range(y + 14, y + CARD_H - 8, 18):
            draw.line((x + 10, yy, x + CARD_W - 10, yy), fill=(48, 88, 160), width=3)
        draw.text((x + CARD_W // 2, y + CARD_H // 2), "L", anchor="mm", font=_font(72, True), fill=(235, 199, 89))
        return

    suit = card.get("suit", "S") if card else "S"
    rank = _card_value_text(card or {})
    red = suit in RED_SUITS
    ink = (185, 36, 44) if red else (25, 25, 28)
    draw.rounded_rectangle((x, y, x + CARD_W, y + CARD_H), radius=radius, fill=(247, 244, 235), outline=(205, 197, 175), width=3)
    draw.text((x + 13, y + 8), rank, font=_font(30, True), fill=ink)
    draw.text((x + 18, y + 44), SUIT_SYMBOLS.get(suit, "♠"), font=_font(30), fill=ink)
    draw.text((x + CARD_W // 2, y + CARD_H // 2 + 10), SUIT_SYMBOLS.get(suit, "♠"), anchor="mm", font=_font(74), fill=ink)


def render_blackjack(path: str | Path, player: list[dict], dealer: list[dict], wager: int, reveal_dealer: bool = False, status: str = "") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1100, 650
    im = Image.new("RGB", (width, height), (20, 71, 49))
    draw = ImageDraw.Draw(im)

    # Felt table + gold rim.
    draw.rounded_rectangle((30, 25, width - 30, height - 25), radius=48, fill=(24, 92, 62), outline=(203, 165, 71), width=8)
    draw.ellipse((265, 70, 835, 590), outline=(221, 199, 130), width=3)
    draw.text((width // 2, 44), "LEGACY BLACK JACK", anchor="ma", font=_font(34, True), fill=(238, 213, 139))
    draw.text((width // 2, 92), f"MISE : {wager} GOLD", anchor="ma", font=_font(22, True), fill=(245, 240, 220))

    # Dealer.
    draw.text((70, 145), "CROUPIER", font=_font(24, True), fill=(240, 232, 205))
    start_x = 220
    dealer_step = min(145, max(72, 650 // max(1, len(dealer))))
    for i, c in enumerate(dealer):
        _draw_card(draw, start_x + i * dealer_step, 125, c, hidden=(i == 1 and not reveal_dealer))
    visible = dealer if reveal_dealer else dealer[:1]
    draw.text((900, 180), f"TOTAL  {blackjack_total(visible)}", anchor="ra", font=_font(26, True), fill=(240, 232, 205))

    # Player.
    draw.text((70, 390), "JOUEUR", font=_font(24, True), fill=(240, 232, 205))
    player_step = min(145, max(72, 650 // max(1, len(player))))
    for i, c in enumerate(player):
        _draw_card(draw, start_x + i * player_step, 365, c, hidden=False)
    draw.text((900, 420), f"TOTAL  {blackjack_total(player)}", anchor="ra", font=_font(26, True), fill=(240, 232, 205))

    if status:
        font = _fit_text(draw, status, width - 140, 28, True)
        draw.text((width // 2, 607), status, anchor="ms", font=font, fill=(250, 236, 181))
    im.save(path, "PNG", optimize=True)
    return path


def blackjack_total(cards: list[dict]) -> int:
    total = 0
    aces = 0
    for c in cards:
        r = str(c.get("rank", ""))
        if r == "A":
            total += 11; aces += 1
        elif r in {"J", "Q", "K"}:
            total += 10
        else:
            try: total += int(r)
            except Exception: pass
    while total > 21 and aces:
        total -= 10; aces -= 1
    return total


def roulette_color(number: int) -> tuple[int, int, int]:
    if number == 0:
        return (28, 125, 74)
    if number in ROULETTE_RED:
        return (174, 35, 45)
    return (30, 31, 35)


def render_roulette_strip(path: str | Path, center_index: int, bet_label: str, wager: int, final: bool = False) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1100, 430
    im = Image.new("RGB", (width, height), (36, 25, 20))
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((25, 20, width - 25, height - 20), radius=36, fill=(62, 35, 28), outline=(205, 163, 75), width=7)
    draw.text((width // 2, 48), "ROULETTE DE LEGACY", anchor="ma", font=_font(34, True), fill=(240, 209, 128))
    draw.text((width // 2, 96), f"{bet_label}  •  MISE {wager} GOLD", anchor="ma", font=_font(20, True), fill=(242, 232, 214))

    count = 9
    box_w = 104
    gap = 8
    strip_w = count * box_w + (count - 1) * gap
    x0 = (width - strip_w) // 2
    y0 = 170
    mid = count // 2
    for j in range(count):
        idx = (center_index + j - mid) % len(EUROPEAN_WHEEL)
        n = EUROPEAN_WHEEL[idx]
        x = x0 + j * (box_w + gap)
        fill = roulette_color(n)
        outline = (239, 203, 112) if j == mid else (105, 86, 68)
        ow = 6 if j == mid else 2
        draw.rounded_rectangle((x, y0, x + box_w, y0 + 120), radius=12, fill=fill, outline=outline, width=ow)
        draw.text((x + box_w // 2, y0 + 60), str(n), anchor="mm", font=_font(38, True), fill=(248, 242, 226))

    cx = x0 + mid * (box_w + gap) + box_w // 2
    draw.polygon([(cx - 18, y0 - 22), (cx + 18, y0 - 22), (cx, y0 + 2)], fill=(246, 211, 109))
    draw.text((width // 2, 330), "LA BILLE RALENTIT..." if not final else "RÉSULTAT", anchor="ma", font=_font(24, True), fill=(244, 229, 195))
    im.save(path, "PNG", optimize=True)
    return path

# ----- Machine à sous réaliste -----
SLOT_LABELS = {"🍒": "CERISE", "🔔": "CLOCHE", "💎": "DIAMANT", "👑": "COURONNE", "7️⃣": "7"}


def _draw_slot_symbol(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], symbol: str):
    x0, y0, x1, y1 = box
    cx, cy = (x0+x1)//2, (y0+y1)//2
    if symbol == "7️⃣":
        draw.text((cx, cy-4), "7", anchor="mm", font=_font(88, True), fill=(205, 39, 48))
    elif symbol == "🍒":
        r = 25
        draw.ellipse((cx-48-r, cy+12-r, cx-48+r, cy+12+r), fill=(183, 35, 44), outline=(90, 20, 25), width=3)
        draw.ellipse((cx+18-r, cy+18-r, cx+18+r, cy+18+r), fill=(194, 39, 49), outline=(90, 20, 25), width=3)
        draw.line((cx-48, cy-12, cx-8, cy-58), fill=(62, 120, 58), width=6)
        draw.line((cx+18, cy-6, cx-8, cy-58), fill=(62, 120, 58), width=6)
        draw.ellipse((cx-12, cy-66, cx+25, cy-45), fill=(71, 132, 64))
    elif symbol == "🔔":
        draw.pieslice((cx-55, cy-55, cx+55, cy+55), start=180, end=360, fill=(217, 174, 64), outline=(122, 90, 30), width=4)
        draw.rectangle((cx-55, cy, cx+55, cy+34), fill=(217, 174, 64), outline=(122, 90, 30), width=4)
        draw.ellipse((cx-12, cy+27, cx+12, cy+51), fill=(150, 106, 31))
        draw.rectangle((cx-8, cy-67, cx+8, cy-50), fill=(217, 174, 64))
    elif symbol == "💎":
        pts = [(cx, cy-65),(cx+62, cy-15),(cx+34, cy+56),(cx-34, cy+56),(cx-62, cy-15)]
        draw.polygon(pts, fill=(77, 179, 224), outline=(220, 244, 255))
        draw.line((cx-62,cy-15,cx+62,cy-15),fill=(224,247,255),width=3)
        draw.line((cx,cy-65,cx-18,cy-15,cx,cy+56,cx+18,cy-15,cx,cy-65),fill=(205,236,250),width=3)
    elif symbol == "👑":
        pts=[(cx-66,cy+35),(cx-58,cy-42),(cx-22,cy-2),(cx,cy-58),(cx+25,cy-3),(cx+61,cy-43),(cx+66,cy+35)]
        draw.polygon(pts, fill=(223, 177, 52), outline=(130, 91, 24))
        draw.rectangle((cx-66,cy+28,cx+66,cy+51), fill=(205,151,39), outline=(130,91,24), width=3)
    else:
        draw.text((cx, cy), SLOT_LABELS.get(symbol, symbol), anchor="mm", font=_font(28, True), fill=(30,30,30))


def render_slot_machine(path: str | Path, reels: list[str], wager: int, *, spinning: bool = False, status: str = "") -> Path:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1100, 650
    im = Image.new("RGB", (width, height), (28, 19, 20))
    draw = ImageDraw.Draw(im)

    # Cabinet.
    draw.rounded_rectangle((120, 25, 980, 625), radius=48, fill=(105, 23, 32), outline=(221, 174, 64), width=9)
    draw.rounded_rectangle((170, 78, 930, 190), radius=24, fill=(20, 17, 18), outline=(184, 139, 48), width=5)
    draw.text((550, 105), "LEGACY JACKPOT", anchor="ma", font=_font(42, True), fill=(244, 207, 106))
    draw.text((550, 158), f"MISE : {wager} GOLD", anchor="ma", font=_font(22, True), fill=(238, 225, 194))

    # Reel window.
    draw.rounded_rectangle((185, 230, 915, 470), radius=30, fill=(16, 16, 18), outline=(226, 190, 87), width=7)
    reel_w = 205
    gap = 28
    start_x = 218
    for i, sym in enumerate(reels[:3]):
        x = start_x + i*(reel_w+gap)
        draw.rounded_rectangle((x, 255, x+reel_w, 445), radius=18, fill=(244, 237, 214), outline=(110, 88, 52), width=4)
        _draw_slot_symbol(draw, (x+8, 265, x+reel_w-8, 430), sym)
        if spinning:
            # Motion streaks give a physical reel impression.
            for yy in range(280, 425, 32):
                draw.line((x+22, yy, x+reel_w-22, yy), fill=(205, 196, 172), width=2)

    # Payline.
    draw.line((180, 350, 920, 350), fill=(231, 60, 70), width=5)
    draw.polygon([(165,350),(185,339),(185,361)], fill=(239,202,94))
    draw.polygon([(935,350),(915,339),(915,361)], fill=(239,202,94))

    # Lever.
    draw.rounded_rectangle((975, 205, 1030, 480), radius=20, fill=(47, 40, 42), outline=(190, 153, 70), width=4)
    draw.line((1003, 205, 1003, 125), fill=(180, 180, 180), width=12)
    draw.ellipse((977, 85, 1029, 137), fill=(178, 34, 43), outline=(226, 178, 76), width=4)

    footer = "LES ROULEAUX TOURNENT..." if spinning else (status or "RÉSULTAT")
    f = _fit_text(draw, footer, 760, 30, True)
    draw.text((550, 540), footer, anchor="ma", font=f, fill=(247, 222, 142))
    draw.text((550, 590), "3 symboles identiques = gain • Deux 7 = mise rendue", anchor="ma", font=_font(18), fill=(211, 199, 173))
    im.save(path, "PNG", optimize=True)
    return path


# ----- Course hippique visuelle -----
def render_horse_race(path: str | Path, positions: list[int], odds: list[float], names: list[str], wager: int, choice: int, *, finish: int = 24, final: bool = False, winner: int | None = None) -> Path:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1200, 690
    im = Image.new("RGB", (width, height), (50, 74, 45))
    draw = ImageDraw.Draw(im)

    draw.rounded_rectangle((25, 20, width-25, height-20), radius=42, fill=(57, 92, 54), outline=(218, 177, 75), width=8)
    draw.text((600, 43), "HIPPODROME CLANDESTIN DE LEGACY", anchor="ma", font=_font(34, True), fill=(244, 214, 133))
    draw.text((600, 88), f"MISE : {wager} GOLD  •  TON CHEVAL : {names[choice-1]} x{odds[choice-1]:.1f}", anchor="ma", font=_font(20, True), fill=(239, 234, 210))

    track_x0, track_x1 = 245, 1110
    top = 145
    lane_h = 110
    usable = track_x1-track_x0-50
    for i in range(4):
        y = top+i*lane_h
        fill = (79, 112, 70) if i % 2 == 0 else (70, 101, 64)
        draw.rounded_rectangle((55,y,1145,y+88), radius=14, fill=fill, outline=(225,218,185), width=2)
        # left info board
        rank_tag = "★ FAVORI" if odds[i] <= 2.0 else ("MID" if odds[i] <= 2.5 else "OUTSIDER")
        draw.text((78,y+18), f"{i+1}. {names[i]}", font=_font(22,True), fill=(250,244,221))
        draw.text((78,y+51), f"x{odds[i]:.1f}  {rank_tag}", font=_font(17,True), fill=(244,207,101))
        # track markings
        for k in range(0, finish+1, 4):
            xx = track_x0 + int((k/finish)*usable)
            draw.line((xx,y+8,xx,y+80), fill=(111,139,96), width=1)
        # finish line checker
        fx = track_x0+usable+10
        for yy in range(y+8,y+80,12):
            for xx in range(fx,fx+28,14):
                on = ((yy-(y+8))//12 + (xx-fx)//14) % 2 == 0
                draw.rectangle((xx,yy,xx+13,yy+11), fill=(245,245,235) if on else (25,25,25))
        # horse marker
        p=max(0,min(int(positions[i]),finish))
        hx = track_x0 + int((p/finish)*usable)
        hy = y+44
        selected = (i == choice-1)
        draw.ellipse((hx-29,hy-29,hx+29,hy+29), fill=(28,43,74) if selected else (78,49,30), outline=(242,205,103), width=4 if selected else 2)
        draw.text((hx,hy-2), "♞", anchor="mm", font=_font(39,True), fill=(248,237,205))

    if final and winner is not None:
        status=f"ARRIVÉE — {names[winner]} GAGNE !"
    else:
        # show current leader by position, not predetermined winner.
        leader=max(range(4), key=lambda j: positions[j])
        status=f"EN DIRECT — {names[leader]} EST EN TÊTE"
    draw.rounded_rectangle((210,610,990,660), radius=18, fill=(23,31,25), outline=(204,165,70), width=3)
    draw.text((600,635), status, anchor="mm", font=_fit_text(draw,status,730,26,True), fill=(247,220,136))
    im.save(path, "PNG", optimize=True)
    return path
