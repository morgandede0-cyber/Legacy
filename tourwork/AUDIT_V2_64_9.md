# Audit V2.64.9 — Petit larcin et notifications

- Base : V2.64.8 (tutoriel Château).
- Nouveau module `larceny_flavor.py` : 12 anecdotes aléatoires, uniquement après réussite.
- Nouveau module `temporary_popups.py` : suppression différée à 30 s des notifications éphémères de petit larcin (réussite et cooldown), sans édition chaque seconde.
- Tests : `tests/test_larceny_popups.py` ; compilation de tous les modules.
- Les fenêtres interactives ne sont pas supprimées. Les messages d'autres activités restent inchangés.
- À vérifier en conditions réelles : suppression des messages éphémères selon la version du client Discord ; rendu PC/mobile ; base PostgreSQL et économie Oddium (non testées en production).
