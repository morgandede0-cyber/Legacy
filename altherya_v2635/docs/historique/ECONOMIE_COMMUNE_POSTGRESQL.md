# Altherya — économie commune PostgreSQL

Cette version utilise `ECONOMY_DATABASE_URL` comme source commune du Gold avec Oddium.

- `wallet_gold` est migré une seule fois depuis `data/legacy.sqlite3` vers PostgreSQL.
- `bank_gold` reste privé à Altherya dans SQLite.
- Les moteurs historiques Altherya continuent à utiliser leur schéma SQLite, mais leurs variations de `wallet_gold` sont appliquées transactionnellement au portefeuille PostgreSQL commun.
- Les événements Oddium (pari, résultat, remboursement) passent par la table `economy_events`; aucun token HTTP n'est nécessaire.
- L'ancien bridge HTTP n'est plus démarré par `main.py`.

Déploiement : définir `ECONOMY_DATABASE_URL` avec la **Postgres URL (internal)** de la base Coolify, puis déployer Altherya avant Oddium lors de la première migration.
