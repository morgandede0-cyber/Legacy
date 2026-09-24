# V2.43 — Sentinelle temps réel

- Capture des exceptions asyncio non gérées.
- Capture des erreurs d'événements Discord.
- Capture des erreurs de commandes texte et slash commands.
- Capture des erreurs des boutons / Components V2 via `View.on_error`.
- MP administrateur avec Trace ID, type, fichier, ligne, traceback et compteur.
- Anti-spam par empreinte d'erreur (rappel toutes les 5 minutes par défaut).
- Journal persistant `data/sentinel_errors.jsonl`.
- Health-check périodique Discord + SQLite.
- Heartbeat `data/sentinel_heartbeat.json` pour supervision externe.
- `watchdog.py` indépendant fourni pour détecter un bot complètement arrêté.

## Variables d'environnement

Obligatoire pour recevoir les MP internes :
`SENTINEL_ADMIN_ID=<id Discord administrateur>`

Optionnelles :
`SENTINEL_ENABLED=1`
`SENTINEL_DM_COOLDOWN=300`
`SENTINEL_HEALTH_INTERVAL=60`

## Watchdog indépendant (second service Coolify)

Le watchdog doit être exécuté séparément du bot principal, sinon il s'arrête en même temps que lui.
Il nécessite :
`WATCHDOG_DISCORD_TOKEN=<token d'un bot watchdog séparé>`
`SENTINEL_ADMIN_ID=<id Discord administrateur>`
`ALTHERYA_HEARTBEAT_PATH=data/sentinel_heartbeat.json`
`WATCHDOG_MAX_HEARTBEAT_AGE=180`
`WATCHDOG_CHECK_INTERVAL=60`

Le fichier heartbeat doit être visible par les deux services (volume partagé ou autre stockage partagé).
