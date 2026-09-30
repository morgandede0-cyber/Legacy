# LegacyBot V1.31 — Duels amicaux à la Taverne

Les trois jeux de la Taverne peuvent maintenant être joués soit contre le tavernier, soit contre un autre membre du serveur.

## Défi amical
- Depuis la table de jeux, utiliser `Dés contre un ami`, `Pile/Face contre un ami` ou `PFC contre un ami`.
- Choisir le membre avec le sélecteur Discord.
- Définir une mise de 1 à 500 Gold par joueur.
- Le défi est publié dans le salon avec `Accepter` / `Refuser`.
- La mise du créateur est réservée au moment de l'envoi du défi.
- La mise de l'adversaire est débitée uniquement lorsqu'il accepte.
- Si le défi est refusé, expire ou si le bot redémarre avant la fin, les mises engagées sont remboursées.

## Règles PvP
- Dés : 2 dés par joueur, somme la plus élevée gagnante. En cas d'égalité, les quatre dés sont relancés.
- Pile ou Face : le créateur choisit Pile ou Face, l'adversaire reçoit automatiquement l'autre côté.
- Pierre / Feuille / Ciseaux : les deux joueurs choisissent secrètement, puis les choix sont révélés simultanément.
- Le gagnant récupère le pot de 2 mises, soit un bénéfice net égal à une mise.
- Une égalité au PFC rembourse les deux joueurs.
- Gold x2 ne s'applique pas aux duels entre joueurs : le bot ne crée pas de Gold lors d'un transfert PvP.

Les gains/pertes de ces duels restent visibles dans le journal public des jeux de la Taverne, et les actions sont également consignées dans `/logs`.
