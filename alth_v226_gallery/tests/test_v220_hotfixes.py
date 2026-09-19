from pathlib import Path


def test_larceny_is_30_minutes():
    src=Path('dark_alley.py').read_text(encoding='utf-8')
    assert 'LARCENY_COOLDOWN = 30 * 60' in src
    assert 'action_type == "larceny"' in src


def test_job_board_reward_is_delayed_and_claimable():
    src=Path('job_board_engine.py').read_text(encoding='utf-8')
    assert 'pending_job_json' in src
    assert 'reward_ready_at' in src
    assert 'def claim_reward' in src
    # accept_job must no longer credit the reward immediately
    accept=src.split('def accept_job',1)[1]
    assert 'pending_job_json=?' in accept


def test_bank_uses_direct_amount_modal():
    src=Path('main.py').read_text(encoding='utf-8')
    assert 'class BankAmountModal' in src
    assert 'Montant en Gold' in src
    assert '−100' not in src and '+100' not in src


def test_russian_roulette_has_return_and_v2_safe_updates():
    src=Path('main.py').read_text(encoding='utf-8')
    rr=src.split('# ----- ROULETTE RUSSE',1)[1].split('# ----- MACHINE À SOUS',1)[0]
    assert 'Retour aux jeux' in rr
    assert 'interaction.edit_original_response(content=' not in rr


def test_castle_daily_and_podium_use_v2_renderer():
    src=Path('main.py').read_text(encoding='utf-8')
    podium=src.split('async def show_castle_podium',1)[1].split('async def show_player_profile',1)[0]
    daily=src.split('async def show_castle_daily',1)[1].split('class PlaceView',1)[0]
    assert ('edit_v2_surface' in podium or 'discord.ui.LayoutView' in podium)
    assert 'edit_v2_surface' in daily
