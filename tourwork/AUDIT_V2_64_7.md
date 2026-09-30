# V2.64.7 — Fin de combat avec compte à rebours

- Arène : victoire et défaite affichent un message de fin personnalisé, avec récompense éventuelle, et un décompte 3 → 2 → 1 avant suppression du panneau éphémère.
- Les deux chemins de fin (action du joueur et tour automatique du Champion / forfait) utilisent le même compte à rebours.
- Aucun bouton actif n'est conservé pendant le décompte ; les résultats économiques sont enregistrés une seule fois avant l'affichage.
- Tests : compilation des modules Python et tests unitaires (dont tests statiques du compte à rebours).
- Limites : rendu réel Discord PC/mobile et connexion PostgreSQL Oddium non testés ici. La Tour d'Ashkar n'est pas modifiée par ce correctif.
