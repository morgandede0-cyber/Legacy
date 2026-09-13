# Docker / Coolify — LegacyBot V1.64.2 FIX ENTREE CASINO

Base : `LegacyBot_V1_64_2_FIX_ENTREE_CASINO`

Ajouts uniquement pour l'hébergement :
- Dockerfile
- .dockerignore
- docker-compose.yml
- COOLIFY.md

Aucune logique de jeu Legacy n'a été modifiée.
La base SQLite reste `data/legacy.sqlite3` et doit être persistée via `/app/data`.
