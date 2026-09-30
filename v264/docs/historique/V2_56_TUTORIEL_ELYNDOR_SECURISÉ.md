# V2.56 — Tutoriel d'Elyndor sécurisé

Ajouté entre le choix PC/Mobile et l'ouverture d'Elyndor pour les nouveaux joueurs.

Parcours :
1. Aux portes d'Elyndor
2. Se déplacer vers le Marché
3. Interagir avec un PNJ
4. Comprendre PV / XP / Gold / Réputations / Inventaire
5. Récompense et ouverture d'Elyndor

Récompense de bienvenue :
- 100 Gold
- 15 XP
- une seule fois par Discord ID

Sécurités :
- `completed` séparé de `reward_claimed`;
- Gold idempotent avec référence économique unique par joueur;
- XP et drapeau XP dans une transaction SQLite unique;
- retry après erreur/crash sans double récompense;
- spam/double clic sans duplication;
- Refaire le tutoriel ne réinitialise jamais la récompense;
- les vues privées sont verrouillées au propriétaire;
- aucune modification de `ECONOMY_DATABASE_URL`;
- le Gold continue d'utiliser l'économie PostgreSQL commune Althérya/Oddium.

Le bouton `📖 Refaire le tutoriel` est disponible dans Elyndor PC et dans la cité mobile.
