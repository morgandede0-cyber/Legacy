# Altherya V2.30 — Correctif global Components V2

- Suppression globale des paramètres `embeds=[]` lors des éditions de messages.
- Discord refuse le champ `embeds` sur un message marqué `IS_COMPONENTS_V2`, même lorsqu'il est vide.
- Correctif appliqué à `main.py`, `legacy_world_forge.py` et `tower_engine.py`.
- Le Troubadour/Histoire reste rendu via `edit_v2_surface` et ouvre le chapitre 1.
- `HubView` n'est pas enregistré via `bot.add_view(HubView())` dans `on_ready`.
- Aucun changement de schéma PostgreSQL ni de logique d'économie.
