# V2.48.1 — Correctif réponse modale FileUpload Components V2

- Corrige l'erreur Discord `50035 Invalid Form Body` après l'envoi du screen.
- Cause : la modale `FileUpload` répondait avec `content=...` alors que l'interaction porte `IS_COMPONENTS_V2`.
- Toutes les réponses de `ScreenUploadModal.on_submit` utilisent désormais uniquement des `LayoutView`, sans champ `content`.
- Le succès ouvre directement `OCRConfirmView`.
- Les erreurs ouvrent `IdentityErrorView` avec possibilité de renvoyer un screen.
- Aucun changement à l'économie, au RPG ou à la base PostgreSQL.
