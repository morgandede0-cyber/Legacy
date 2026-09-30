# Audit — Tour d'Ashkar sans classes

Base : V2.64.4 Arène sans classes.

## Modifications
- Préparation sans sélection de classe : entrée directe dans l'étage.
- Techniques identiques à l'Arène et recalculées selon le niveau (1, 3, 6, 9, 12, 15, 18).
- Attaques et défense communes, sans effets propres aux anciennes classes.
- Après combat : enchaînement, nouvelle tentative et retour à la préparation sans choix de classe.
- Textes et HUD PC/mobile adaptés.
- Progression, ennemis, récompenses et limite quotidienne inchangés.

## Vérifications
- Compilation Python de l'ensemble du projet : OK.
- 8 tests unitaires/structurels : OK, dont 4 spécifiques à la Tour.
- Revue des références de sélection de classe : OK.
- Imports et code mort : suppression de l'ancien choix de classe et des effets de classe dans la Tour ; compatibilité `class_key` conservée dans les états et appels historiques.

## Limites
- Le paquet `discord` n'est pas installé dans cet environnement : imports à l'exécution, interactions Discord et rendu PC/mobile non testés en conditions réelles.
- Aucun accès à PostgreSQL de production ni à Oddium : intégration de la monnaie commune non vérifiée. Aucun changement à ces modules.
- Un avertissement ResourceWarning préexistant apparaît dans un test du tableau de bord.
