# Altherya V1.65 — Panneau des petites annonces

Cette mise à jour transforme l'ancien tableau des expéditions en panneau de petites annonces d'Altherya.

## Fonctionnement
- 5 annonces sont proposées simultanément à chaque joueur.
- Chaque annonce tire sa rareté indépendamment : Commun, Peu commun, Rare, Épique ou Légendaire.
- Il n'existe aucun quota de rareté : plusieurs annonces légendaires peuvent apparaître sur le même panneau, comme un panneau entièrement commun.
- Chaque rareté possède sa propre fourchette de récompense en Gold.
- Lorsqu'un joueur accepte une annonce, le Gold est crédité immédiatement dans son portefeuille.
- Les 4 autres annonces sont supprimées immédiatement.
- Le panneau entre ensuite en renouvellement pendant 1 heure.
- À la fin du délai, 5 nouvelles annonces sont générées automatiquement au prochain affichage/actualisation.
- Le délai est persistant en SQLite et résiste aux redémarrages du bot.
- Les gains sont enregistrés dans les logs administrateur économiques.

## Récompenses actuelles
- Commun : 8 à 25 Gold
- Peu commun : 25 à 60 Gold
- Rare : 60 à 120 Gold
- Épique : 120 à 240 Gold
- Légendaire : 250 à 500 Gold

## Technique
- Nouveau module : `job_board_engine.py`
- Nouvelle table SQLite : `job_board_state`
- La destination interne `expeditions` est conservée pour ne pas casser les assets/transitions existants, mais son nom visible devient `Petites annonces`.
- L'ancien moteur d'expédition reste présent pour conserver les ressources, équipements, Forge et données existantes. Il sera remplacé progressivement par le nouveau système Forêt d'Elarwyn / Mont Vorak.
