# V2.47 — Identification OCR

- Suppression de la saisie manuelle du pseudo côté joueur.
- Screen Informations joueur obligatoire.
- OCR ciblé uniquement sur la zone fixe du pseudo.
- Confirmation du pseudo détecté avant renommage Discord.
- En cas d'OCR incertain ou d'échec de renommage, alerte dans `ADMIN_ONBOARDING_CHANNEL_ID`.
- Le joueur peut seulement renvoyer un screen ; aucune correction manuelle côté joueur.
- Dépendances : Tesseract OCR + pytesseract.
