# Altherya V1.67.2 — Fix /admin

- `/admin` accepte un administrateur Discord OU un joueur présent dans `admin_access`.
- Aucun `has_permissions(administrator=True)` n'est appliqué à `/admin`.
- L'interaction est acquittée immédiatement avec `defer()` avant les accès SQLite.
- Le panneau est ensuite envoyé via `followup`, ce qui évite les erreurs Discord 10062 et 40060 observées en production.
- La gestion Ajouter/Retirer des accès reste réservée aux vrais administrateurs Discord.
