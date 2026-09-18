from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_shared_economy_wired_before_stores():
    main=(ROOT/'main.py').read_text(encoding='utf-8')
    shared=(ROOT/'shared_economy.py').read_text(encoding='utf-8')
    assert main.index('migrate_legacy_wallets(DATA / "legacy.sqlite3")') < main.index('ECONOMY = Economy')
    assert 'economy_wallets' in shared and 'economy_transactions' in shared and 'economy_events' in shared
    assert 'OddiumBridgeServer(' not in main
    assert 'shared_economy_event_worker' in main

def test_wallet_engines_use_shared_connection():
    for name in ['economy.py','tavern_engine.py','legacy_world_forge.py','story_engine.py','dark_alley.py','castle_engine.py','expedition_engine.py','casino_engine.py','admin_engine.py','arena_engine.py','job_board_engine.py']:
        txt=(ROOT/name).read_text(encoding='utf-8')
        assert 'connect_shared(' in txt, name
