from pathlib import Path
import ast, re
ROOT=Path(__file__).resolve().parents[1]
PYFILES=[p for p in ROOT.rglob('*.py') if '.pytest_cache' not in p.parts]

def test_all_python_parses():
    for p in PYFILES: ast.parse(p.read_text(encoding='utf-8'), filename=str(p))

def test_no_plain_discord_token():
    pat=re.compile(r'MT[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{20,}')
    assert not [(p,pat.search(p.read_text(errors='ignore')).group(0)) for p in PYFILES if pat.search(p.read_text(errors='ignore'))]

def test_shared_economy_uses_environment():
    s=(ROOT/'shared_economy.py').read_text(encoding='utf-8')
    assert 'ECONOMY_DATABASE_URL' in s

def test_v2_core_has_no_select_component():
    s=(ROOT/'ui_v2.py').read_text(encoding='utf-8')
    assert 'discord.ui.Select' not in s and 'UserSelect' not in s

def test_hub_asset_exists():
    assert (ROOT/'assets'/'places'/'hub.png').exists()

def test_required_place_assets_exist():
    names=['tavern.png','market.png','bank.png','arena.png','forge.png','alley.png','castle.png']
    missing=[n for n in names if not (ROOT/'assets'/'places'/n).exists()]
    assert not missing

def test_tower_runtime_no_embed_in_combat_paths():
    s=(ROOT/'tower_engine.py').read_text(encoding='utf-8')
    # Les combats migrés doivent utiliser le renderer V2.
    assert 'async def _edit_v2' in s
    assert 'await _edit_v2(interaction, title="⚔️ Combat — Tour d\'Ashkar"' in s
