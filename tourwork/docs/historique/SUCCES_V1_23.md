# Legacy V1.23 — Système de succès

## Configuration
Un administrateur lance `/succes` dans le salon qui doit recevoir les annonces.
Le salon est mémorisé en SQLite et reste configuré après redémarrage.

## Raretés
1. Commun — gris
2. Rare — vert
3. Épique — bleu
4. Mythique — violet
5. Légendaire — doré

## Branches V1.23
- Pioche
- Hache
- Lance
- Sac

Chaque branche possède 5 succès : achat du niveau 1, puis amélioration niveaux 2, 3, 4 et 5.
Les succès sont persistants et ne peuvent être annoncés qu'une seule fois par joueur.

## Annonce publique
Lorsqu'un succès est débloqué, le bot publie un Embed dans le salon configuré avec : joueur, avatar, nom du succès, branche, rareté et progression 1/5 à 5/5.
