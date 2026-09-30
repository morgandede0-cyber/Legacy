# V2.61 — lancement officiel, aucune variable à ajouter

Déploie simplement cette version dans Coolify en conservant le volume `/app/data`
et la base PostgreSQL `altherya_economy`.

**Au premier démarrage seulement**, le bot :
1. sauvegarde `legacy.sqlite3`, les paramètres essentiels et les tables
   économiques PostgreSQL dans `/app/data/official_reset_backups/<date_UTC>/` ;
2. réinitialise toutes les tables de progression de jeu ;
3. remet les portefeuilles Gold PostgreSQL à 0 et archive les transactions et
   événements économiques de bêta dans la sauvegarde JSON ;
4. réinitialise le tutoriel et les annonces de bienvenue ;
5. conserve les inscriptions IV (`onboarding.sqlite3`), rôles Discord, salons
   configurés et accès administrateurs ;
6. crée `/app/data/.official_launch_reset_v261_done` pour ne plus jamais
   recommencer lors des redémarrages.

**Aucune variable d'environnement à ajouter, aucune commande à lancer et
aucune base à supprimer.** La variable `ECONOMY_DATABASE_URL` existante doit
rester configurée comme avant. Si elle manque, le bot refusera le reset plutôt
que de laisser les joueurs avec des Gold incohérents.

Le portefeuille est commun à Althérya et Oddium : le Gold d'Oddium sera donc
aussi remis à zéro. Il est préférable de ne pas lancer Oddium pendant le
premier démarrage d'Althérya.

En cas d'échec, le bot arrête son démarrage ; il n'affiche pas un succès
fictif. Les sauvegardes restent dans le volume persistant.

Vérifications locales : compilation Python, intégrité ZIP, simulation de
réinitialisation et sauvegarde SQLite. PostgreSQL et Discord doivent être
validés lors du premier déploiement réel.
