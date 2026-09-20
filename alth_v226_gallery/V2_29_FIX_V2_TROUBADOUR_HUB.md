# V2.29 — Correctif Components V2 Troubadour + Hub

- `edit_v2_surface()` n'envoie plus le champ `embeds` lors de l'édition d'un message Components V2. Même `embeds=[]` est refusé par Discord sur un message marqué IS_COMPONENTS_V2.
- `edit_with_asset()` suit la même règle.
- Le Hub Components V2 n'est plus enregistré avec `bot.add_view(HubView())` au démarrage : il est construit à la demande, ce qui supprime l'exception de persistance dans `on_ready`.
- Le Troubadour ouvre toujours le chapitre 1 et utilise le renderer V2.
