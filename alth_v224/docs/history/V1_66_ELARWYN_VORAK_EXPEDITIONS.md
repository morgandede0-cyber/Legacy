# Altherya V1.66 — Forêt d'Elarwyn & Mont Vorak

## Nouveau système d'expédition

- Deux nouveaux lieux sur la carte d'Elyndor : **Forêt d'Elarwyn** et **Mont Vorak**.
- Chaque lieu possède **5 destinations** (noms provisoires), débloquées aux niveaux **1 / 5 / 10 / 20 / 30**.
- Durées : **1 h / 2 h / 4 h / 6 h / 8 h**.
- Forêt d'Elarwyn : **Couper du bois** ou **Chasser**.
- Mont Vorak : **Miner** ou **Chasser**.
- Une seule activité par expédition : impossible de chasser et récolter/miner en même temps.
- Menu de préparation interactif avec :
  - carrousel de l'outil débloqué ;
  - carrousel de la sacoche débloquée ;
  - validation stricte : outil adapté + sacoche obligatoires.
- Une seule expédition active par joueur.
- Une fois lancée, retour au début du lieu avec timer et logs.
- Message de suivi serveur mis à jour pendant 1 à 8 heures.
- Drops révélés progressivement dans les logs.
- À la fin du timer, le butin est **automatiquement transféré dans l'inventaire**.
- Le transfert est atomique et résiste aux redémarrages Coolify : aucun double crédit.
- Les ressources existantes sont conservées : bois, minerais et ressources de chasse restent les mêmes.
- L'ancien panneau d'expédition reste le **Panneau des petites annonces d'Altherya** de la V1.65.

## Compatibilité serveur

- Docker / Coolify conservés.
- Données persistantes dans `/app/data`.
- Les anciennes tables SQLite sont migrées sans effacer les données joueurs.
