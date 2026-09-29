# V2.48.2 — Correctif OCR du préfixe IV

- Corrige la confusion OCR de la police du jeu sur le préfixe fixe `IV`.
- Les lectures `Iv`, `IY`, `W`, `Ww` ou `Wv` en tout début de pseudo sont normalisées en `IV`.
- La correction ne s'applique qu'au premier token suivi d'un espace : un `W` présent dans le vrai pseudo n'est pas modifié.
- Aucun changement de l'économie, du RPG, de PostgreSQL ou du flux d'upload Discord.
