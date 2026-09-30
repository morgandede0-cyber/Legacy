"""Remise à zéro du lancement officiel, automatique UNE SEULE FOIS au déploiement.

La base et les sauvegardes restent dans le volume persistant. Aucun fichier de données
n'est supprimé. Le portefeuille PostgreSQL est partagé : Oddium sera aussi affecté.
"""
from __future__ import annotations
import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Tables de configuration et d'administration à conserver. Le reste est une donnée
# de jeu ou une donnée dérivée, qui sera recréée au prochain démarrage.
PRESERVE = {
    'achievement_channels', 'log_channels', 'admin_access', 'admin_notes',
    'gazette_config', 'guild_config', 'server_config',
}


def _save_sqlite(db: Path, dest: Path):
    if not db.exists():
        return
    with sqlite3.connect(db) as src, sqlite3.connect(dest) as backup:
        src.backup(backup)
        assert backup.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


def _save_postgres(pg, dest: Path):
    """Snapshot JSON complet des trois tables économiques avant toute modification."""
    snapshot = {}
    for table in ('economy_wallets', 'economy_transactions', 'economy_events', 'economy_meta'):
        with pg.cursor() as cur:
            cur.execute(f'SELECT * FROM {table}')
            names = [d.name for d in cur.description]
            snapshot[table] = [dict(zip(names, [str(v) if not isinstance(v,(int,float,bool,type(None),dict,list)) else v for v in row])) for row in cur.fetchall()]
    dest.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    if not dest.stat().st_size:
        raise RuntimeError('Sauvegarde PostgreSQL vide')
    return {name:len(rows) for name,rows in snapshot.items()}


def _reset_sqlite(db: Path):
    if not db.exists(): return []
    with sqlite3.connect(db,timeout=30) as conn:
        conn.execute('PRAGMA busy_timeout=30000')
        conn.execute('BEGIN IMMEDIATE')
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        wiped=[]
        for table in tables:
            if table in PRESERVE or table.startswith(('admin_config_', 'server_config_')):
                continue
            escaped = '"' + table.replace('"','""') + '"'
            conn.execute(f'DELETE FROM {escaped}')
            wiped.append(table)
        conn.commit()
    return wiped


def run_if_requested(data_dir: Path) -> bool:
    data_dir=Path(data_dir)
    data_dir.mkdir(parents=True,exist_ok=True)
    marker=data_dir/'.official_launch_reset_v261_done'
    if marker.exists():
        print('[RESET OFFICIEL] Déjà effectué : aucune donnée modifiée.')
        return False
    url=os.getenv('ECONOMY_DATABASE_URL','').strip()
    if not url:
        raise RuntimeError('RESET ANNULÉ : ECONOMY_DATABASE_URL absente. Impossible de garantir le reset Gold.')
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError('RESET ANNULÉ : psycopg indisponible.') from exc
    # Créer la sauvegarde AVANT d'écrire quoi que ce soit.
    backup=data_dir/'official_reset_backups'/datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_UTC')
    backup.mkdir(parents=True,exist_ok=False)
    db=data_dir/'legacy.sqlite3'
    _save_sqlite(db,backup/'legacy.sqlite3')
    for name in ('onboarding.sqlite3','admin_roles.json','admin_panel.json','hub_message.json','display_modes.json'):
        path=data_dir/name
        if path.exists() and path.is_file(): shutil.copy2(path,backup/name)
    # PostgreSQL transaction : le snapshot et la remise à zéro sont protégés par le
    # même verrou de transaction. Oddium ne doit pas être actif pendant l'opération.
    with psycopg.connect(url,autocommit=False) as pg:
        with pg.cursor() as cur:
            cur.execute('LOCK TABLE economy_wallets, economy_transactions, economy_events, economy_meta IN ACCESS EXCLUSIVE MODE')
        counts=_save_postgres(pg,backup/'postgres_economy_before.json')
        # Réinitialiser SQLite avant de valider PG. Si PG échoue, restauration SQLite.
        try:
            wiped=_reset_sqlite(db)
            with pg.cursor() as cur:
                cur.execute('UPDATE economy_wallets SET balance=0, updated_at=NOW()')
                # Nouvelle saison : anciennes références et événements de la bêta
                # sont archivés dans le snapshot avant d'être réinitialisés.
                cur.execute("DELETE FROM economy_transactions")
                cur.execute("DELETE FROM economy_events")
                # Empêcher une réimportation de vieux soldes SQLite au démarrage.
                cur.execute("INSERT INTO economy_meta(key,value) VALUES('altherya_sqlite_wallet_migrated_v2','official-reset-v261') ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_at=NOW()")
            pg.commit()
        except BaseException:
            pg.rollback()
            if (backup/'legacy.sqlite3').exists(): shutil.copy2(backup/'legacy.sqlite3',db)
            raise
    # Préférences d'affichage : le choix PC/Mobile doit être proposé à nouveau.
    display=data_dir/'display_modes.json'
    if display.exists(): display.write_text('{}\n',encoding='utf-8')
    # L'inscription IV est conservée. Aucun effacement de onboarding.sqlite3.
    manifest={'date_utc':datetime.now(timezone.utc).isoformat(),
              'sqlite_tables_reset':wiped,'postgres_rows_backed_up':counts,
              'preserved_tables':sorted(PRESERVE),
              'backup_directory':str(backup)}
    (backup/'RESET_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    marker.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'[RESET OFFICIEL] Réussi : {len(wiped)} tables de jeu vidées. Sauvegardes : {backup}')
    print('[RESET OFFICIEL] Gold partagé = 0, tutoriel et annonces réinitialisés, inscriptions IV conservées.')
    return True
