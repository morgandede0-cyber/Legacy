# V2.46.1 — Correctif Accueil

- Correction du crash au démarrage dans `accueil.py`.
- Suppression de `default_permissions=` du constructeur `app_commands.Command`, incompatible avec l'environnement déployé.
- `/setup_accueil` conserve sa restriction administrateur grâce à une vérification explicite de `interaction.permissions.administrator`.
- Aucun changement sur l'économie, le RPG ou PostgreSQL.
