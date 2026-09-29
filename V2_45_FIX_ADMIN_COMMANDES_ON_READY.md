# Altherya V2.45 — Fix commandes Admin + on_ready

- `/admin`, `/admin_setup`, `/admin_move`, `/admin_refresh` contrôlées explicitement avant/après synchronisation Discord.
- Marqueur runtime `[V2.45] Panel Admin chargé...`.
- Correction du crash `on_ready` : `TavernDrinksView` active a `timeout=300` et n'est plus passée à `bot.add_view()`.
- Sentinelle indépendante, absente du panel Admin.
