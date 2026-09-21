# V1.16 — Correction détection équipement des expéditions

- La sélection d'outil ne parcourt plus Pioche/Hache/Lance par défaut.
- Seuls les outils réellement achetés au Marché (`equipment_ownership`) sont affichés.
- Le Sac n'est plus considéré comme possédé simplement parce que `bag_level` vaut 1 par défaut.
- Sans outil acheté, la sélection est verrouillée et le joueur est renvoyé vers le Marché.
- Sans Sac de fortune acheté, la sélection du sac est verrouillée.
- Les niveaux d'équipement restent séparés de la propriété : niveau 1 ne signifie jamais « possédé ».
- `ExpeditionStore.start()` conserve sa vérification serveur au lancement pour empêcher tout contournement de l'interface.
