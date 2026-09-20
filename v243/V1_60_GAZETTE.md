# Legacy V1.60 — La Gazette

- Nouvelle commande admin `/gazette` dans le salon qui doit recevoir le journal.
- Publication automatique chaque jour à 09:00, heure locale du serveur.
- Aucun fuseau horaire externe / aucune dépendance tzdata.
- La période commence à la dernière Gazette publiée (ou au moment de la première configuration).
- Aucun événement inventé : la Gazette lit les événements réellement enregistrés dans `legacy.sqlite3`.
- Casino : meilleur et pire **bilan net** de la période (`payout - wager` sur toutes les parties terminées).
- Ivresse : anecdotes issues de `tavern_drunk_events`, donc uniquement si la scène s'est réellement produite.
- Une seule anecdote d'alcool par joueur et maximum 4 par édition pour éviter qu'un joueur monopolise le journal.
- Maximum 7 rubriques par édition.
- S'il n'y a rien à raconter, une édition calme est publiée au lieu d'inventer un fait.
