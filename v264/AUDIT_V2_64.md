# Altherya V2.64 — Tableau de bord du Château et première extraction technique

## Modifications
- Nouveau module indépendant `castle_dashboard.py` pour composer le tableau de bord personnel : niveau/XP, Gold en poche/banque, récompense journalière, quêtes, expédition en cours, résultats d'arène.
- Nouveau bouton « Tableau de bord » dans le Château, avec retour au Château.
- Bouton « Récompense journalière » remplacé par « Déjà récupéré », désactivé dès la récupération, et lors de chaque nouvelle ouverture du Château le même jour. Réactivation lors d'une nouvelle ouverture après la remise à zéro quotidienne. La vérification atomique de `claim_daily` côté base reste en place.
- Première étape du chantier technique : extraction du formatage du tableau de bord hors de `main.py`, sans migration risquée des autres modules.

## Vérifications exécutées
- Compilation Python de l'arborescence : réussie.
- Audit statique `tools/audit.py` : 32 modules racine, aucune redéfinition inattendue ni erreur de syntaxe.
- Trois tests unitaires du tableau de bord (récompense disponible, déjà récupérée/expédition active, quêtes prêtes) : réussis.
- Conversion de vues : le bouton désactivé est transmis directement à la conversion Components V2 existante.

## Vérifications non exécutées
- Tests réels PC et mobile sur Discord : nécessitent un serveur et un bot connecté.
- Tests d'intégration sur une copie de la base de production et sur la connexion PostgreSQL Oddium : non exécutés ; aucun changement au schéma ou à l'économie partagée.
- Tests de régression exhaustifs des autres activités : non exécutés ; les tests unitaires ajoutés ne les couvrent pas.
- Analyse complète des imports inutilisés et du code mort : à poursuivre pendant le découpage progressif de `main.py`.

## Risque restant
- Une ancienne vue du Château déjà affichée avant la récupération peut conserver son ancien libellé jusqu'à son actualisation ; `claim_daily` refuse toutefois un second versement. Les nouveaux affichages sont à jour.
- Le tableau de bord indique seulement si une expédition est en cours ; l'heure exacte de fin n'est pas encore affichée.
