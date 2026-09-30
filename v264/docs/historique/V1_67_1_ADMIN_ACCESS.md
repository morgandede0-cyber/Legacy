# V1.67.1 — Accès /admin délégués

- Ajout d'une catégorie `👥 Accès /admin` au panneau d'administration.
- Un administrateur Discord peut ajouter, retirer et consulter les joueurs autorisés.
- Les joueurs autorisés peuvent lancer `/admin` sans permission Administrateur Discord.
- Seuls les vrais administrateurs Discord peuvent modifier la liste des accès.
- Les accès sont persistés dans `legacy.sqlite3` (`admin_access`) et journalisés dans `admin_audit`.
