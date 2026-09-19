from pathlib import Path

def test_podium_is_real_three_step_text_layout():
    src=Path('main.py').read_text(encoding='utf-8')
    block=src.split('def _podium_text',1)[1].split('async def show_castle_podium',1)[0]
    assert '┃       1        ┃' in block
    assert '┃       2        ┃' in block
    assert '┃       3        ┃' in block
    assert '🥇' in block and '🥈' in block and '🥉' in block

def test_podium_uses_top_three_discord_names_and_avatars():
    src=Path('main.py').read_text(encoding='utf-8')
    block=src.split('async def show_castle_podium',1)[1].split('async def show_player_profile',1)[0]
    assert 'leaderboard(3)' in block
    assert 'm.display_name' in block
    assert 'm.display_avatar.url' in block
    assert 'discord.ui.MediaGallery()' in block
    assert 'for pos in (2,1,3)' in block
    assert '_podium_text(top3)' in block
    assert 'attachments=[]' in block
