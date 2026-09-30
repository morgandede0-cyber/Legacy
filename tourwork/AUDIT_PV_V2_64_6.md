# Audit PV V2.64.6

- Corrigé la source des 1000 PV : `main.py` (Arène), `tower_engine.py` (Tour) et `castle_engine.py` (annonces de progression).
- PV joueurs : 100 au niveau 1, +10 par niveau, sans bonus de classe dans l'Arène et la Tour.
- PV des champions et ennemis inchangés. Leurs dégâts n'ont pas été rééquilibrés dans cette mise à jour.
- Compilation Python et tests unitaires exécutés. Pas de test réel sur Discord, PostgreSQL ou Oddium.
- Les combats déjà commencés conservent potentiellement leurs PV jusqu'au prochain combat ; ouvrir un nouveau combat après redémarrage.
