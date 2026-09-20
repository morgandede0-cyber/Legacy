from __future__ import annotations
import hashlib, json, os, sqlite3, threading, uuid
from pathlib import Path

try:
    import psycopg
except Exception:
    psycopg = None

def _url(): return os.getenv('ECONOMY_DATABASE_URL','').strip()
_LOCK = threading.RLock()

class SharedEconomyError(RuntimeError): pass
class SharedEconomyInsufficientFunds(SharedEconomyError): pass

def enabled(): return bool(_url())

def _pg():
    url=_url()
    if not url:
        raise SharedEconomyError('ECONOMY_DATABASE_URL absente')
    if psycopg is None:
        raise SharedEconomyError('psycopg indisponible')
    return psycopg.connect(url, autocommit=False)

def init_schema():
    if not enabled(): return
    with _LOCK, _pg() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS economy_wallets(
          user_id BIGINT PRIMARY KEY, balance BIGINT NOT NULL DEFAULT 0 CHECK(balance>=0), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')
        c.execute('''CREATE TABLE IF NOT EXISTS economy_transactions(
          id BIGSERIAL PRIMARY KEY, source TEXT NOT NULL, reference TEXT NOT NULL, user_id BIGINT NOT NULL,
          amount BIGINT NOT NULL, reason TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          UNIQUE(source,reason,reference))''')
        c.execute('''CREATE TABLE IF NOT EXISTS economy_events(
          id BIGSERIAL PRIMARY KEY, source TEXT NOT NULL, event_key TEXT NOT NULL UNIQUE, payload JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), processed_at TIMESTAMPTZ)''')
        c.execute('''CREATE TABLE IF NOT EXISTS economy_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')
        c.commit()

def diagnostics():
    if not enabled(): return None
    init_schema()
    with _LOCK, _pg() as c:
        row=c.execute("SELECT current_database(), current_user, inet_server_addr()::text, inet_server_port()").fetchone()
        count=int(c.execute("SELECT COUNT(*) FROM economy_wallets").fetchone()[0]); c.commit()
    return {"database":str(row[0]),"user":str(row[1]),"host":str(row[2]),"port":int(row[3]),"wallets":count,"fingerprint":hashlib.sha256(_url().encode("utf-8")).hexdigest()[:12]}

def migrate_legacy_wallets(db_path: str|Path):
    """Bootstrap PostgreSQL from Altherya SQLite without overwriting live shared balances.

    A local wallet is imported when the shared wallet does not exist, or when it is
    still zero and has never had an economy transaction. This also repairs the case
    where Oddium created a zero wallet before Altherya performed its first import.
    """
    if not enabled(): return 0
    init_schema(); db_path=Path(db_path)
    if not db_path.exists(): return 0
    imported=0
    with _LOCK, _pg() as pg:
        sq=sqlite3.connect(db_path); sq.row_factory=sqlite3.Row
        try:
            exists=sq.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='players'").fetchone()
            rows=sq.execute('SELECT user_id,wallet_gold FROM players').fetchall() if exists else []
            for r in rows:
                uid=int(r['user_id']); local=max(0,int(r['wallet_gold']))
                if local <= 0: continue
                shared=pg.execute('SELECT balance FROM economy_wallets WHERE user_id=%s',(uid,)).fetchone()
                has_tx=pg.execute('SELECT 1 FROM economy_transactions WHERE user_id=%s LIMIT 1',(uid,)).fetchone()
                if shared is None:
                    pg.execute('INSERT INTO economy_wallets(user_id,balance) VALUES(%s,%s)',(uid,local)); imported+=1
                elif int(shared[0]) == 0 and not has_tx:
                    pg.execute('UPDATE economy_wallets SET balance=%s,updated_at=NOW() WHERE user_id=%s',(local,uid)); imported+=1
            pg.execute("INSERT INTO economy_meta(key,value) VALUES('altherya_sqlite_wallet_migrated_v2',%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()",(str(imported),))
            pg.commit(); return imported
        finally: sq.close()


# One-time recovery of the known pre-shared Altherya wallet.
# Safe/idempotent: it only seeds an existing/new zero wallet when that user has
# never had a shared-economy transaction. Once seeded (or once any transaction
# exists), this code can never overwrite the live shared balance.
def recover_known_legacy_wallet(user_id:int, legacy_balance:int)->bool:
    if not enabled(): return False
    init_schema(); uid=int(user_id); legacy_balance=max(0,int(legacy_balance))
    if legacy_balance <= 0: return False
    with _LOCK, _pg() as c:
        c.execute('INSERT INTO economy_wallets(user_id,balance) VALUES(%s,0) ON CONFLICT DO NOTHING',(uid,))
        row=c.execute('SELECT balance FROM economy_wallets WHERE user_id=%s FOR UPDATE',(uid,)).fetchone()
        has_tx=c.execute('SELECT 1 FROM economy_transactions WHERE user_id=%s LIMIT 1',(uid,)).fetchone()
        if int(row[0]) != 0 or has_tx:
            c.rollback(); return False
        c.execute('UPDATE economy_wallets SET balance=%s,updated_at=NOW() WHERE user_id=%s',(legacy_balance,uid))
        c.execute('INSERT INTO economy_transactions(source,reference,user_id,amount,reason) VALUES(%s,%s,%s,%s,%s)',
                  ('ALTHERYA','legacy-wallet-recovery-v1',uid,legacy_balance,'LEGACY_RECOVERY'))
        c.commit(); return True

def get_balance(user_id:int)->int:
    init_schema()
    with _LOCK, _pg() as c:
        c.execute('INSERT INTO economy_wallets(user_id,balance) VALUES(%s,0) ON CONFLICT DO NOTHING',(int(user_id),))
        row=c.execute('SELECT balance FROM economy_wallets WHERE user_id=%s',(int(user_id),)).fetchone(); c.commit(); return int(row[0])

def mutate(user_id:int, amount:int, reason:str, reference:str, source='ALTHERYA'):
    init_schema(); uid=int(user_id); amount=int(amount)
    with _LOCK, _pg() as c:
        old=c.execute('SELECT amount FROM economy_transactions WHERE source=%s AND reason=%s AND reference=%s',(source,reason,reference)).fetchone()
        if old:
            bal=c.execute('SELECT balance FROM economy_wallets WHERE user_id=%s',(uid,)).fetchone(); c.rollback(); return True,int(bal[0] if bal else 0),True
        c.execute('INSERT INTO economy_wallets(user_id,balance) VALUES(%s,0) ON CONFLICT DO NOTHING',(uid,))
        if amount < 0:
            row=c.execute('UPDATE economy_wallets SET balance=balance+%s,updated_at=NOW() WHERE user_id=%s AND balance >= %s RETURNING balance',(amount,uid,-amount)).fetchone()
            if not row: c.rollback(); return False,get_balance(uid),False
        else:
            row=c.execute('UPDATE economy_wallets SET balance=balance+%s,updated_at=NOW() WHERE user_id=%s RETURNING balance',(amount,uid)).fetchone()
        c.execute('INSERT INTO economy_transactions(source,reference,user_id,amount,reason) VALUES(%s,%s,%s,%s,%s)',(source,reference,uid,amount,reason))
        c.commit(); return True,int(row[0]),False

def enqueue_event(payload:dict, source='ODDIUM'):
    init_schema(); key=str(payload.get('event_key') or payload.get('reference') or f"{payload.get('type','event')}:{payload.get('user_id','')}:{payload.get('bet_id',payload.get('combo_id',''))}")
    with _LOCK,_pg() as c:
        c.execute('INSERT INTO economy_events(source,event_key,payload) VALUES(%s,%s,%s::jsonb) ON CONFLICT(event_key) DO NOTHING',(source,key,json.dumps(payload,ensure_ascii=False))); c.commit()

def pending_events(limit=50):
    if not enabled(): return []
    init_schema()
    with _LOCK,_pg() as c:
        rows=c.execute('SELECT id,payload FROM economy_events WHERE processed_at IS NULL ORDER BY id LIMIT %s',(int(limit),)).fetchall(); c.commit()
        return [(int(r[0]), r[1] if isinstance(r[1],dict) else json.loads(r[1])) for r in rows]

def mark_event_processed(event_id:int):
    with _LOCK,_pg() as c: c.execute('UPDATE economy_events SET processed_at=NOW() WHERE id=%s',(int(event_id),)); c.commit()

def _wallets_pg():
    if not enabled(): return {}
    init_schema()
    with _LOCK,_pg() as c:
        rows=c.execute('SELECT user_id,balance FROM economy_wallets').fetchall(); c.commit(); return {int(a):int(b) for a,b in rows}

class SharedConnection(sqlite3.Connection):
    def _sync_in(self):
        self._shared_baseline={}
        if not enabled(): return
        try:
            if not super().execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='players'").fetchone(): return
            wallets=_wallets_pg()
            for uid,bal in wallets.items():
                super().execute('INSERT OR IGNORE INTO players(user_id) VALUES(?)',(uid,))
                super().execute('UPDATE players SET wallet_gold=? WHERE user_id=?',(bal,uid))
            rows=super().execute('SELECT user_id,wallet_gold FROM players').fetchall()
            self._shared_baseline={int(r[0]):int(r[1]) for r in rows}
            super().commit()
        except Exception:
            try: super().rollback()
            except Exception: pass
            raise
    def commit(self):
        baseline=getattr(self,'_shared_baseline',None)
        if enabled() and baseline is not None:
            try:
                rows=super().execute('SELECT user_id,wallet_gold FROM players').fetchall()
            except sqlite3.OperationalError:
                rows=[]
            current={int(r[0]):int(r[1]) for r in rows}
            changes=[]
            for uid,val in current.items():
                delta=val-baseline.get(uid,0)
                if delta: changes.append((uid,delta))
            applied=[]
            try:
                for uid,delta in changes:
                    ref=f'altherya-sqlite:{uuid.uuid4().hex}'
                    ok,bal,_=mutate(uid,delta,'ALTHERYA_GAME',ref,'ALTHERYA')
                    if not ok: raise SharedEconomyInsufficientFunds(f'Solde Gold insuffisant pour {uid}')
                    applied.append((uid,delta,ref))
                    super().execute('UPDATE players SET wallet_gold=? WHERE user_id=?',(bal,uid)); current[uid]=bal
                super().commit(); self._shared_baseline=current
            except Exception:
                super().rollback()
                # Compensation for deltas already committed to PG.
                for uid,delta,ref in reversed(applied):
                    mutate(uid,-delta,'ALTHERYA_COMPENSATE',ref+':rollback','ALTHERYA')
                raise
        else:
            super().commit()
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb):
        if exc_type is None: self.commit()
        else: self.rollback()
        self.close(); return False

def connect_shared(database, *args, **kwargs):
    # Always delegate to sqlite3.connect. Calling connect_shared here recursively
    # prevents Altherya from opening its local database.
    if not enabled():
        return sqlite3.connect(database, *args, **kwargs)
    kwargs['factory'] = SharedConnection
    c = sqlite3.connect(database, *args, **kwargs)
    c._sync_in()
    return c
