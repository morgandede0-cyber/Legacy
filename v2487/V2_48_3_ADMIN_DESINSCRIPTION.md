# V2.48.3 — Désinscription admin

- Nouvelle commande `/desinscrire membre:@joueur`.
- Réservée aux administrateurs Discord.
- Confirmation obligatoire avant suppression.
- Supprime la ligne du joueur dans `data/onboarding.sqlite3`.
- Réinitialise langue, identité OCR, règlement et statut d'inscription.
- Retire le rôle configuré par `MEMBER_ROLE_ID` si le bot en a la permission.
- Ne modifie pas le pseudo Discord actuel du joueur.
- Le joueur peut ensuite recommencer via `COMMENCER`.
