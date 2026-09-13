# LegacyBot V1.27 — Jeux de la Taverne

Les trois jeux de la table de la Taverne sont maintenant réellement jouables :

- Lancer de dé
- Pile ou Face
- Pierre / Feuille / Ciseaux

## Fonctionnement

- Mise libre de 1 à 500 Gold, comme les jeux de la salle clandestine.
- La mise est retirée atomiquement avant le début de la partie.
- Si le bot redémarre pendant une partie active, la mise est remboursée au redémarrage.
- L'événement Gold x2 double uniquement le bénéfice d'une victoire, jamais un remboursement.
- Les gains et pertes nets sont publiés dans le salon public configuré avec `/succes`, conformément au journal public des jeux.
- Les actions sont également disponibles pour les logs administrateur.

## Lancer de dé

Le joueur et le tavernier lancent chacun un dé. Le plus grand résultat gagne. En cas d'égalité, les dés sont automatiquement relancés jusqu'à obtenir un vainqueur. Une victoire paie x2 au total.

## Pile ou Face

Après la mise, le joueur choisit Pile ou Face avec un bouton. La pièce est animée avant le résultat. Une victoire paie x2 au total.

## Pierre / Feuille / Ciseaux

Après la mise, le joueur choisit Pierre, Feuille ou Ciseaux. Le tavernier choisit aléatoirement. Une victoire paie x2 au total, une égalité rembourse la mise.

Chaque jeu possède désormais son rendu graphique dynamique et ses boutons Rejouer / Table de jeux.
