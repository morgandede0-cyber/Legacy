# V2.48.4 — Désinscription dans le panel Admin

- Ajout du bouton **🗑️ Désinscrire** dans la fiche joueur du panel Admin.
- Parcours : Panel Admin → Joueurs → sélectionner un joueur → Désinscrire.
- Confirmation obligatoire avant suppression.
- Réinitialise uniquement l'inscription d'accueil (langue, OCR, règlement, completed) et tente de retirer MEMBER_ROLE_ID.
- Ne réinitialise pas l'économie, la progression RPG, l'inventaire ou le pseudo Discord actuel.
- La commande /desinscrire reste disponible mais le panel Admin devient le parcours principal.
