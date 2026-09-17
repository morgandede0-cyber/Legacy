from pathlib import Path

def test_admin_command_center_present():
    s=Path('main.py').read_text(encoding='utf-8')
    assert 'CENTRE DE COMMANDEMENT' in s
    assert 'AdminStaffNoteModal' in s
    assert 'show_admin_player_history' in s
    assert "('history','Historique'" in s
    assert "('note','Note staff'" in s

def test_admin_store_migrations_present():
    s=Path('admin_engine.py').read_text(encoding='utf-8')
    assert 'CREATE TABLE IF NOT EXISTS admin_notes' in s
    assert 'access_role' in s
    assert 'def server_snapshot' in s
    assert 'def recent_audit' in s
