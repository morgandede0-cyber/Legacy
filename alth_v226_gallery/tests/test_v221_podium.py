from pathlib import Path

SRC=Path(__file__).resolve().parents[1]/"main.py"

def test_podium_is_compact_three_step_text_layout():
    src=SRC.read_text(encoding="utf-8")
    block=src.split("def _podium_text",1)[1].split("async def show_castle_podium",1)[0]
    assert 'w = 11' in block
    assert '│    1    │' in block
    assert '│    2    │' in block
    assert '│    3    │' in block
    assert 'row(n2, n1, n3)' in block
    assert 'row(gold(g2), gold(g1), gold(g3))' in block

def test_podium_uses_top_three_discord_names_and_avatars():
    src=SRC.read_text(encoding="utf-8")
    block=src.split("async def show_castle_podium",1)[1].split("async def show_player_profile",1)[0]
    assert "CASTLE_STORE.leaderboard(3)" in block
    assert "m.display_name" in block
    assert "m.display_avatar.url" in block
    assert "for pos in (1,2,3)" in block
    assert "_podium_text(top3)" in block
