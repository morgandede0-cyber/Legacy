from __future__ import annotations
import os
from pathlib import Path


def run_once(data_dir: Path) -> bool:
    """One-shot reset for the Altherya public beta.

    The marker is stored in the persistent /app/data volume, so a normal bot
    restart will never wipe players a second time.
    """
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    marker = data_dir / ".beta_v1_reset_done"
    if marker.exists():
        return False

    print("[BETA] Premier démarrage : remise à zéro des données de jeu…")

    # Local RPG database: contains progression, inventory, equipment, cooldowns,
    # reputations, arena/tower/casino/job-board/story/gazette player state, etc.
    for name in ("legacy.sqlite3", "legacy.sqlite3-wal", "legacy.sqlite3-shm"):
        p = data_dir / name
        if p.exists():
            p.unlink()

    # Runtime/player preferences and generated transient state.
    for name in ("display_modes.json", "sentinel_heartbeat.json", "sentinel_errors.jsonl"):
        p = data_dir / name
        if p.exists():
            p.unlink()

    live = data_dir / "expedition_live"
    if live.exists() and live.is_dir():
        for p in live.iterdir():
            if p.is_file():
                p.unlink()

    # Shared Gold wallet (Altherya <-> Oddium): beta starts at 0 Gold.
    # We keep transaction history/audit tables intact; only current balances reset.
    url = os.getenv("ECONOMY_DATABASE_URL", "").strip()
    if url:
        try:
            import psycopg
            with psycopg.connect(url) as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE economy_wallets SET balance=0, updated_at=NOW()")
                conn.commit()
            print("[BETA] Wallet Gold partagé remis à 0.")
        except Exception as exc:
            # Do NOT mark reset complete if the shared wallet could not be reset.
            raise RuntimeError(f"Reset Gold PostgreSQL impossible: {exc}") from exc
    else:
        print("[BETA] ECONOMY_DATABASE_URL absente : aucun wallet PostgreSQL à remettre à zéro.")

    # Deliberately preserved: onboarding.sqlite3, admin_roles.json,
    # admin_panel.json and hub_message.json (server configuration / registration).
    marker.write_text("Altherya beta v1 reset completed\n", encoding="utf-8")
    print("[BETA] Remise à zéro terminée. Ce wipe ne sera pas rejoué aux prochains redémarrages.")
    return True
