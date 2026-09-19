from admin_engine import AdminStore

def test_admin_access_roundtrip(tmp_path):
    store = AdminStore(tmp_path / 'test.sqlite3')
    assert not store.has_admin_access(10, 20)
    assert store.grant_admin_access(10, 20, 1) is True
    assert store.has_admin_access(10, 20)
    assert store.list_admin_access(10) == [20]
    assert store.grant_admin_access(10, 20, 1) is False
    assert store.revoke_admin_access(10, 20, 1) is True
    assert not store.has_admin_access(10, 20)
