# Audit V2.06 — Altherya

Audit structurel complet du code Python, de l'économie commune et des points d'accès au portefeuille Gold.

## Corrections
- `shared_economy.py` relit désormais `ECONOMY_DATABASE_URL` dynamiquement : les variables chargées par `.env` ne sont plus ratées à cause de l'ordre des imports.
- Le démarrage affiche un diagnostic PostgreSQL non secret : base, hôte, port, nombre de portefeuilles et empreinte SHA-256 tronquée de l'URL.
- `story_engine.py` utilisait encore `sqlite3.connect()` directement tout en débitant `wallet_gold`. Il passe désormais par `connect_shared()` ; les achats d'histoire modifient donc bien le portefeuille PostgreSQL partagé.
- L'ancien serveur HTTP Oddium (`integrations/oddium/bridge.py`) a été retiré : il était mort depuis le passage au PostgreSQL commun et n'était plus instancié par `main.py`.
- Les anciennes variables `ALTHERYA_BRIDGE_*` inutilisées ont été retirées de `main.py`.
- Les caches Python/Pytest ont été retirés de l'archive.
- Les anciennes notes de versions ont été déplacées dans `docs/history/` pour alléger la racine.

## Vérifications
- Compilation de tous les fichiers Python : OK.
- Tests Altherya : 6/6 OK dans l'environnement d'audit.
- Tous les modules qui modifient `players.wallet_gold` passent maintenant par `connect_shared()` ou par la couche d'économie commune.

## Diagnostic de déploiement
Altherya et Oddium affichent désormais une `empreinte=XXXXXXXXXXXX`. Les deux empreintes doivent être identiques. Si elles diffèrent, les deux conteneurs ne reçoivent pas exactement la même URL PostgreSQL.
