# Audit correctif — Arène sans classes

- Source : archive V2.64.3 Gazette Pseudos.
- Suppression du choix de classes du défi Champion et du duel amical (y compris ancienne surcouche tardive qui réintroduisait les boutons).
- Les joueurs de l'Arène utilisent le profil neutre `arena_fighter`, avec PV calculés uniquement à partir du niveau.
- Progression des techniques : niveau 1 (base), 3 (attaque rapide), 6 (attaque lourde), 9 (ultime), 12, 15 et 18.
- Classes des champions PNJ conservées pour préserver leur IA ; Tour d'Ashkar inchangée.
- Nettoyage des anciennes classes de sélection Discord et des alias associés dans main.py.
- Vérifications locales : compilation Python, tests de déblocage des techniques, simulation d'une attaque et d'un choix IA, contrôle statique des vues.
- Non vérifié : affichage et interaction en conditions réelles sur Discord PC/mobile, migration des combats en cours et base PostgreSQL Oddium. Redémarrer le bot et rouvrir l'Arène pour remplacer les anciens panneaux.
