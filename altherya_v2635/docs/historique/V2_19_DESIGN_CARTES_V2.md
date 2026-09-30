# Altherya V2.19 — Design cartes interactives Components V2

- Tous les lieux et sous-écrans passant par le renderer commun utilisent maintenant le format RPG Components V2 : titre, illustration, contexte, puis cartes d'actions natives.
- Chaque action est une `Section` avec texte contextuel et un vrai bouton Discord en accessoire.
- Aucun faux bouton n'est intégré aux images.
- Les callbacks et mécaniques historiques sont conservés : cette passe modifie la présentation, pas les règles du jeu.
- Le Hub Altherya et le Monde d'Elyndor conservent leur navigation V2 dédiée.
- Correction du nom d'attachment du Hub au retour (`altherya_city.png`) afin qu'il corresponde au MediaGallery V2.
- Validation : compilation Python complète + 13/13 tests automatisés.
