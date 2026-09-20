# Altherya V2.02 — Correctif arbre de commandes Discord

- `/altherya` reste la commande officielle du Hub.
- Synchronisation déplacée de `on_ready()` vers `setup_hook()`, avant le traitement normal des interactions Gateway.
- Vérification bloquante que `/altherya` existe bien dans l'arbre local avant synchronisation.
- Vérification que Discord retourne bien `/altherya` dans la liste synchronisée.
- Logs de démarrage détaillés : commandes locales, commandes synchronisées et confirmation explicite de `/altherya`.
- Suppression de la resynchronisation dans `on_ready()` pour éviter les états incohérents lors des reconnexions.
- `/altherya` conserve son acquittement immédiat (`defer`) et ses protections contre les interactions expirées.
- L'ancien `/setup` n'est pas réintroduit. Une synchronisation réussie nettoie les anciennes commandes globales absentes de l'arbre local.
