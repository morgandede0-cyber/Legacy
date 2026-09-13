from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math

W,H = 1000,560


def _font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p,size)
        except Exception:
            pass
    return ImageFont.load_default()


def _base(title, wager):
    im=Image.new("RGB",(W,H),(52,35,24)); d=ImageDraw.Draw(im)
    d.rounded_rectangle((24,24,W-24,H-24),radius=26,fill=(75,48,29),outline=(193,151,75),width=4)
    d.rectangle((45,95,W-45,H-70),fill=(34,66,50),outline=(146,111,57),width=3)
    d.text((55,42),title,font=_font(36,True),fill=(245,222,169))
    d.text((W-260,48),f"Mise : {wager} Gold",font=_font(24,True),fill=(241,206,107))
    return im,d


def _die_sprite(n:int, size:int=120, angle:float=0):
    """Crée un vrai dé graphique, puis le fait pivoter pour simuler le roulement."""
    pad=28
    canvas=Image.new("RGBA",(size+pad*2,size+pad*2),(0,0,0,0))
    d=ImageDraw.Draw(canvas)
    x0=y0=pad; x1=y1=pad+size
    # ombre
    d.rounded_rectangle((x0+7,y0+10,x1+7,y1+10),radius=22,fill=(0,0,0,75))
    d.rounded_rectangle((x0,y0,x1,y1),radius=22,fill=(239,230,207,255),outline=(69,47,30,255),width=5)
    pts={
        1:[(.5,.5)],
        2:[(.29,.29),(.71,.71)],
        3:[(.29,.29),(.5,.5),(.71,.71)],
        4:[(.29,.29),(.71,.29),(.29,.71),(.71,.71)],
        5:[(.29,.29),(.71,.29),(.5,.5),(.29,.71),(.71,.71)],
        6:[(.29,.25),(.71,.25),(.29,.5),(.71,.5),(.29,.75),(.71,.75)],
    }
    r=max(7,int(size*.075))
    for px,py in pts.get(int(n),[]):
        cx=x0+int(size*px); cy=y0+int(size*py)
        d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=(34,28,24,255))
    if angle:
        canvas=canvas.rotate(angle,resample=Image.Resampling.BICUBIC,expand=True)
    return canvas


def _paste_die(im:Image.Image, center:tuple[int,int], n:int, angle:float=0, size:int=120):
    spr=_die_sprite(n,size=size,angle=angle)
    x=int(center[0]-spr.width/2); y=int(center[1]-spr.height/2)
    im.paste(spr,(x,y),spr)


def render_dice(path: Path, wager:int, player=None, bot=None, status="", angles=None, left_label="TOI", right_label="TAVERNIER"):
    """
    Lance de dés façon casino : 2 dés par joueur.
    `player` et `bot` acceptent chacun un tuple/list de deux valeurs.
    `angles` = ((a1,a2),(b1,b2)) pour l'animation du roulement.
    """
    im,d=_base("LANCER DE DÉS",wager)
    if player is None or bot is None:
        d.text((300,220),"Les dés roulent sur la table...",font=_font(32,True),fill=(245,222,169))
    else:
        # Compatibilité si une ancienne valeur simple arrivait encore ici.
        if isinstance(player,int): player=(player,roll_safe(player))
        if isinstance(bot,int): bot=(bot,roll_safe(bot))
        player=tuple(player); bot=tuple(bot)
        if angles is None: angles=((0,0),(0,0))
        p_ang,b_ang=angles

        d.text((155,125),str(left_label)[:18].upper(),font=_font(26,True),fill=(245,222,169))
        d.text((650,125),str(right_label)[:18].upper(),font=_font(26,True),fill=(245,222,169))
        _paste_die(im,(220,260),player[0],p_ang[0],118)
        _paste_die(im,(365,260),player[1],p_ang[1],118)
        _paste_die(im,(660,260),bot[0],b_ang[0],118)
        _paste_die(im,(805,260),bot[1],b_ang[1],118)

        p_total=sum(player); b_total=sum(bot)
        d.rounded_rectangle((160,382,425,448),radius=18,fill=(47,40,28),outline=(193,151,75),width=2)
        d.rounded_rectangle((575,382,840,448),radius=18,fill=(47,40,28),outline=(193,151,75),width=2)
        d.text((185,398),f"TOTAL : {p_total}",font=_font(27,True),fill=(241,206,107))
        d.text((600,398),f"TOTAL : {b_total}",font=_font(27,True),fill=(241,206,107))
    if status:
        d.text((55,485),status,font=_font(21,True),fill=(245,222,169))
    path.parent.mkdir(parents=True,exist_ok=True); im.save(path); return path


def roll_safe(seed:int) -> int:
    # Uniquement pour compatibilité d'affichage, jamais utilisé pour décider d'un résultat.
    return ((int(seed)+2) % 6) + 1


def render_coin(path: Path, wager:int, choice:str, result:str|None=None, status=""):
    im,d=_base("PILE OU FACE",wager)
    d.text((65,120),f"Ton choix : {choice.upper()}",font=_font(28,True),fill=(245,222,169))
    cx,cy=500,300; r=110
    d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=(218,169,57),outline=(248,226,143),width=8)
    text="?" if result is None else ("P" if result=="pile" else "F")
    bb=d.textbbox((0,0),text,font=_font(100,True)); d.text((cx-(bb[2]-bb[0])/2,cy-(bb[3]-bb[1])/2-8),text,font=_font(100,True),fill=(80,55,20))
    if result: d.text((405,420),result.upper(),font=_font(32,True),fill=(245,222,169))
    if status: d.text((55,485),status,font=_font(23,True),fill=(245,222,169))
    path.parent.mkdir(parents=True,exist_ok=True); im.save(path); return path


# ----------- EMOJIS PFC -----------
# Sprites emoji pré-rendus et embarqués avec le bot : rendu identique sur Windows/Linux,
# sans dépendre de la prise en charge des emojis par la police du serveur.
RPS_EMOJIS = {"pierre": "✊", "feuille": "✋", "ciseaux": "✌️"}
RPS_LABELS = {"pierre": "Pierre", "feuille": "Feuille", "ciseaux": "Ciseaux"}
RPS_ASSET_DIR = Path(__file__).resolve().parent / "assets" / "rps"

def _emoji_sprite(kind: str, target_size: int = 230):
    asset = RPS_ASSET_DIR / f"{kind}.png"
    if asset.exists():
        spr = Image.open(asset).convert("RGBA")
        ratio = target_size / max(spr.width, spr.height)
        return spr.resize((max(1,int(spr.width*ratio)), max(1,int(spr.height*ratio))), Image.Resampling.LANCZOS)
    # Fallback lisible si un asset est supprimé accidentellement.
    canvas = Image.new("RGBA", (target_size, target_size), (0,0,0,0))
    d = ImageDraw.Draw(canvas)
    symbol = {"pierre":"✊", "feuille":"✋", "ciseaux":"✌"}.get(kind, "?")
    f = _font(int(target_size*.72), True)
    bb = d.textbbox((0,0), symbol, font=f)
    d.text(((target_size-(bb[2]-bb[0]))/2, (target_size-(bb[3]-bb[1]))/2-bb[1]), symbol, font=f, fill=(245,222,169,255))
    return canvas

def _paste_rps_emoji(im: Image.Image, center: tuple[int,int], kind: str, size: int = 230):
    spr = _emoji_sprite(kind, size)
    im.paste(spr, (int(center[0]-spr.width/2), int(center[1]-spr.height/2)), spr)


def render_rps(path: Path, wager:int, player:str, bot:str|None=None, status="", left_label="TOI", right_label="TAVERNIER"):
    im,d=_base("PIERRE • FEUILLE • CISEAUX",wager)
    if bot is None:
        _paste_rps_emoji(im,(300,270),player,235)
        d.text((225,395),"TON CHOIX",font=_font(22,True),fill=(245,222,169))
        label=RPS_LABELS.get(player, player.title())
        bb=d.textbbox((0,0),label,font=_font(20,True))
        d.text((300-(bb[2]-bb[0])/2,430),label,font=_font(20,True),fill=(229,210,169))
        d.text((560,220),"Le tavernier",font=_font(28,True),fill=(245,222,169))
        d.text((545,270),"prépare son coup...",font=_font(25),fill=(229,210,169))
        d.text((623,330),"?",font=_font(72,True),fill=(241,206,107))
    else:
        _paste_rps_emoji(im,(275,270),player,235)
        _paste_rps_emoji(im,(725,270),bot,235)
        d.text((185,395),str(left_label)[:18].upper(),font=_font(23,True),fill=(245,222,169))
        d.text((620,395),str(right_label)[:18].upper(),font=_font(23,True),fill=(245,222,169))
        d.text((470,245),"VS",font=_font(42,True),fill=(241,206,107))
        pl=RPS_LABELS.get(player,player.title()); bl=RPS_LABELS.get(bot,bot.title())
        d.text((215,430),pl,font=_font(20,True),fill=(229,210,169))
        d.text((665,430),bl,font=_font(20,True),fill=(229,210,169))
    if status:
        d.text((55,485),status,font=_font(21,True),fill=(245,222,169))
    path.parent.mkdir(parents=True,exist_ok=True); im.save(path); return path

