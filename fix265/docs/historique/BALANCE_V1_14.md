# LegacyBot V1.14 — Forge / Marché / Progression

## Marché
- Équipements de départ : 100 Gold chacun.
- Un équipement de départ acheté disparaît de la boutique pour ce joueur.
- Aucun doublon possible.
- Les équipements de départ ne sont pas revendables.
- Les ressources d'expédition sont revendables selon un barème modéré dans `RESOURCE_SELL_PRICES`.
- Une ressource vendue est immédiatement retirée de la table `resources`; la Forge lit donc le nouveau stock réel.

## Forge
- Entrée : seulement `Améliorer équipement` et `Rentrer en ville`.
- Sous-menu : Pioche, Hache, Lance, Sac.
- La fiche lit en direct : niveau joueur, Gold du portefeuille et quantités de chaque ressource (`possédé/requis`).
- Une seconde validation atomique est faite au clic sur `Améliorer`.
- Paliers joueur requis : N2=5, N3=10, N4=18, N5=28.
- Gold outils : 150 / 350 / 700 / 1400.
- Gold sac : 200 / 450 / 900 / 1800.

## Progression XP
- Courbe non linéaire dans `progression.py` : chaque niveau demande davantage d'XP.
- Arène : victoire +35 XP, défaite +8 XP.
- Casino : +1 XP par partie.
- Expédition : XP uniquement à la récupération du butin, pas au lancement.
- Quêtes et daily réduites afin d'éviter le sur-leveling.
- Daily : 200 Gold + 10 XP.

## Économie
- Frais de retrait après le premier retrait gratuit : 5 % au lieu de 10 %.
- Ruelle sombre rééquilibrée :
  - crime : 80–160 Gold / amende 75,
  - vol plafonné à 100 Gold,
  - braquage : 450–900 Gold / amende 250,
  - entrée clandestine : 150 Gold.
- Casino et Arène conservent leur mise maximale de 500 Gold.
