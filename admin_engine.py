from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path
from progression import xp_needed_for_level, level_from_xp

EVENTS = {
    'gold_x2': ('Gold x2', '💰'),
    'xp_x2': ('XP x2', '✨'),
}

class AdminStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _c(self):
        c = sqlite3.connect(self.db_path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self):
        with self._c() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('''CREATE TABLE IF NOT EXISTS bot_events(
                event_key TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS admin_audit(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                target_id INTEGER,
                action TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS admin_access(
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                granted_by INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(guild_id,user_id)
            )''')
            c.commit()

    def has_admin_access(self, guild_id: int, user_id: int) -> bool:
        with self._c() as c:
            row = c.execute('SELECT 1 FROM admin_access WHERE guild_id=? AND user_id=?',
                            (int(guild_id), int(user_id))).fetchone()
        return row is not None

    def grant_admin_access(self, guild_id: int, user_id: int, granted_by: int) -> bool:
        with self._c() as c:
            cur = c.execute('INSERT OR IGNORE INTO admin_access(guild_id,user_id,granted_by) VALUES(?,?,?)',
                            (int(guild_id), int(user_id), int(granted_by)))
            c.commit()
        changed = cur.rowcount > 0
        self.log(granted_by, user_id, 'admin_access_grant', f'guild_id={int(guild_id)} changed={changed}')
        return changed

    def revoke_admin_access(self, guild_id: int, user_id: int, revoked_by: int) -> bool:
        with self._c() as c:
            cur = c.execute('DELETE FROM admin_access WHERE guild_id=? AND user_id=?',
                            (int(guild_id), int(user_id)))
            c.commit()
        changed = cur.rowcount > 0
        self.log(revoked_by, user_id, 'admin_access_revoke', f'guild_id={int(guild_id)} changed={changed}')
        return changed

    def list_admin_access(self, guild_id: int) -> list[int]:
        with self._c() as c:
            rows = c.execute('SELECT user_id FROM admin_access WHERE guild_id=? ORDER BY created_at,user_id',
                             (int(guild_id),)).fetchall()
        return [int(r['user_id']) for r in rows]

    def log(self, admin_id: int, target_id: int | None, action: str, details: str = ''):
        with self._c() as c:
            c.execute('INSERT INTO admin_audit(admin_id,target_id,action,details) VALUES(?,?,?,?)',
                      (int(admin_id), int(target_id) if target_id is not None else None, str(action), str(details)))
            c.commit()

    def event_enabled(self, key: str) -> bool:
        with self._c() as c:
            r = c.execute('SELECT enabled FROM bot_events WHERE event_key=?', (str(key),)).fetchone()
        return bool(r['enabled']) if r else False

    def set_event(self, key: str, enabled: bool, admin_id: int):
        with self._c() as c:
            c.execute('''INSERT INTO bot_events(event_key,enabled,updated_at,updated_by) VALUES(?,?,?,?)
                         ON CONFLICT(event_key) DO UPDATE SET enabled=excluded.enabled,updated_at=excluded.updated_at,updated_by=excluded.updated_by''',
                      (str(key), 1 if enabled else 0, datetime.now().isoformat(timespec='seconds'), int(admin_id)))
            c.commit()
        self.log(admin_id, None, 'event', f'{key}={enabled}')

    def adjust_gold(self, user_id: int, delta: int) -> tuple[int,int]:
        uid, delta = int(user_id), int(delta)
        with self._c() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT OR IGNORE INTO players(user_id) VALUES(?)', (uid,))
            row = c.execute('SELECT wallet_gold FROM players WHERE user_id=?', (uid,)).fetchone()
            old = int(row['wallet_gold'])
            new = max(0, old + delta)
            c.execute('UPDATE players SET wallet_gold=? WHERE user_id=?', (new, uid))
            c.commit()
        return old, new

    @staticmethod
    def _xp_floor(level: int) -> int:
        return sum(xp_needed_for_level(i) for i in range(1, max(1, int(level))))

    def adjust_level(self, user_id: int, delta_levels: int) -> tuple[int,int,int]:
        uid = int(user_id)
        delta_levels = int(delta_levels)
        with self._c() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT OR IGNORE INTO castle_profiles(user_id) VALUES(?)', (uid,))
            row = c.execute('SELECT xp FROM castle_profiles WHERE user_id=?', (uid,)).fetchone()
            xp = int(row['xp'])
            old_level, remaining, _ = level_from_xp(xp)
            new_level = max(1, old_level + delta_levels)
            next_need = xp_needed_for_level(new_level)
            new_xp = self._xp_floor(new_level) + min(remaining, max(0, next_need - 1))
            c.execute('UPDATE castle_profiles SET xp=? WHERE user_id=?', (new_xp, uid))
            c.execute('INSERT OR IGNORE INTO expedition_profiles(user_id) VALUES(?)', (uid,))
            c.execute('UPDATE expedition_profiles SET player_level=? WHERE user_id=?', (new_level, uid))
            c.commit()
        return old_level, new_level, new_xp


    def cooldowns_enabled(self) -> bool:
        # Les cooldowns sont actifs par défaut. La clé stockée représente leur désactivation globale.
        return not self.event_enabled('cooldowns_disabled')

    def set_cooldowns_enabled(self, enabled: bool, admin_id: int):
        self.set_event('cooldowns_disabled', not bool(enabled), admin_id)
        self.log(admin_id, None, 'cooldowns_global', f'enabled={bool(enabled)}')

    def reset_cooldowns(self, user_id: int) -> dict[str, int]:
        """Réinitialise les vrais cooldowns temporisés d'un joueur.

        Cela concerne actuellement la Ruelle sombre (vol/crime), le Champion d'Arène
        et le délai entre deux verres à la Taverne. Les limites journalières ne sont
        volontairement pas considérées comme des cooldowns.
        """
        uid = int(user_id)
        result = {'dark_actions': 0, 'arena_champion': 0, 'tavern_drink': 0}
        with self._c() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                cur = c.execute('DELETE FROM dark_actions WHERE user_id=?', (uid,))
                result['dark_actions'] = max(0, cur.rowcount)
            except sqlite3.OperationalError:
                pass
            try:
                cur = c.execute('DELETE FROM arena_champion WHERE user_id=?', (uid,))
                result['arena_champion'] = max(0, cur.rowcount)
            except sqlite3.OperationalError:
                pass
            try:
                cur = c.execute('UPDATE tavern_drink_limits SET last_drink_at=NULL WHERE user_id=? AND last_drink_at IS NOT NULL', (uid,))
                result['tavern_drink'] = max(0, cur.rowcount)
            except sqlite3.OperationalError:
                pass
            c.commit()
        return result

    def clear_alley_ban(self, user_id: int) -> bool:
        uid = int(user_id)
        with self._c() as c:
            try:
                cur = c.execute('DELETE FROM alley_bans WHERE user_id=?', (uid,))
                c.commit()
                return cur.rowcount > 0
            except sqlite3.OperationalError:
                return False

    def set_resource(self, user_id: int, name: str, delta: int) -> tuple[int,int]:
        uid, delta = int(user_id), int(delta)
        name = str(name).strip()
        with self._c() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT quantity FROM resources WHERE user_id=? AND resource_name=?', (uid,name)).fetchone()
            old = int(row['quantity']) if row else 0
            new = max(0, old + delta)
            if new:
                c.execute('''INSERT INTO resources(user_id,resource_name,quantity) VALUES(?,?,?)
                             ON CONFLICT(user_id,resource_name) DO UPDATE SET quantity=excluded.quantity''', (uid,name,new))
            else:
                c.execute('DELETE FROM resources WHERE user_id=? AND resource_name=?', (uid,name))
            c.commit()
        return old,new

    def set_gear_owned(self, user_id: int, key: str, owned: bool):
        if key not in {'pickaxe','axe','spear','bag'}:
            raise ValueError('Équipement invalide')
        uid = int(user_id)
        with self._c() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT OR IGNORE INTO expedition_profiles(user_id) VALUES(?)', (uid,))
            c.execute('INSERT OR IGNORE INTO equipment_ownership(user_id) VALUES(?)', (uid,))
            c.execute(f'UPDATE equipment_ownership SET {key}_owned=? WHERE user_id=?', (1 if owned else 0, uid))
            if not owned:
                c.execute(f'UPDATE expedition_profiles SET {key}_level=1 WHERE user_id=?', (uid,))
            c.commit()

    def set_profile_stat(self, user_id: int, stat: str, value: int) -> tuple[int, int]:
        """V1.68 — édite les compteurs de profil administrables sans casser leurs tables métier."""
        uid, value = int(user_id), max(0, int(value))
        mapping = {
            'tavern_drinks': ('tavern_reputation', 'drinks'),
            'criminal_successes': ('criminal_reputation', 'successes'),
            'arena_rating': ('arena_progress', 'rating'),
            'arena_champion_wins': ('arena_progress', 'champion_wins'),
            'casino_wins': ('casino_loyalty_admin', 'wins'),
        }
        if stat not in mapping:
            raise ValueError(f'Statistique de profil inconnue: {stat}')
        table, column = mapping[stat]
        with self._c() as c:
            c.execute('BEGIN IMMEDIATE')
            if table == 'arena_progress':
                c.execute('INSERT OR IGNORE INTO arena_progress(user_id,rating,champion_wins) VALUES(?,0,0)', (uid,))
            elif table == 'casino_loyalty_admin':
                c.execute('CREATE TABLE IF NOT EXISTS casino_loyalty_admin(user_id INTEGER PRIMARY KEY,wins INTEGER NOT NULL CHECK(wins >= 0))')
                c.execute('INSERT OR IGNORE INTO casino_loyalty_admin(user_id,wins) VALUES(?,0)', (uid,))
            else:
                c.execute(f'INSERT OR IGNORE INTO {table}(user_id,{column}) VALUES(?,0)', (uid,))
            row=c.execute(f'SELECT {column} FROM {table} WHERE user_id=?',(uid,)).fetchone()
            old=int(row[column]) if row else 0
            c.execute(f'UPDATE {table} SET {column}=? WHERE user_id=?',(value,uid))
            c.commit()
        return old, value


def event_multiplier(db_path: str | Path, key: str) -> int:
    try:
        with sqlite3.connect(Path(db_path), timeout=5) as c:
            row = c.execute('SELECT enabled FROM bot_events WHERE event_key=?', (str(key),)).fetchone()
            return 2 if row and int(row[0]) else 1
    except sqlite3.Error:
        return 1


def cooldowns_enabled(db_path: str | Path) -> bool:
    """Retourne False uniquement quand un admin a désactivé globalement les cooldowns."""
    try:
        with sqlite3.connect(Path(db_path), timeout=5) as c:
            row = c.execute('SELECT enabled FROM bot_events WHERE event_key=?', ('cooldowns_disabled',)).fetchone()
            return not (row and int(row[0]))
    except sqlite3.Error:
        return True
