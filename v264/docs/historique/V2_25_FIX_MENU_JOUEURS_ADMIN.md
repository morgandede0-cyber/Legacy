# V2.25 — Correctif menu joueurs /admin

- Correction de la route réelle **Administration des joueurs**.
- Suppression de la seconde définition concurrente de `AdminPlayersView`.
- L'écran affiche directement un `discord.ui.UserSelect` natif : **Sélectionner un joueur...**.
- Aucun bouton `Rechercher un joueur` et aucun modal `Nom du joueur` sur cet écran.
- L'ID Discord reste utilisé uniquement en interne après la sélection.
- Le menu déroulant reste l'unique exception demandée aux interfaces sans Select.
