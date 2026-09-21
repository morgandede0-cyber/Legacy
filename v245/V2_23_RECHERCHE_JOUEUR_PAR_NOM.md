# V2.23 — Recherche joueur par nom

- Administration des joueurs : `Ouvrir un profil par ID` devient `Rechercher un joueur`.
- La fenêtre demande désormais un pseudo (`Nom du joueur`) et non un ID Discord.
- Recherche par pseudo serveur (`display_name`), nom global Discord et username.
- Priorité : correspondance exacte, puis début du nom, puis correspondance partielle.
- En cas de plusieurs correspondances, Altherya affiche les joueurs possibles et demande de préciser la recherche.
- L'ID Discord reste utilisé uniquement en interne / compatibilité et n'est plus nécessaire pour l'administrateur.
- Le même confort a été appliqué aux autres écrans utilisant le sélecteur générique de membre (administration, ami, cible).
