# ALTHERYA — Release Audit RC2

Date : 2026-09-19
Base : V2.17 RC1

## Passe effectuée
- Compilation de l'intégralité des sources Python.
- Exécution de la suite automatisée historique + nouveaux tests d'intégrité release.
- Audit des secrets Discord et de la configuration PostgreSQL partagée.
- Audit des assets principaux du Hub et des lieux.
- Audit des composants Select visibles et des adaptateurs legacy.
- Migration supplémentaire de la Tour d'Ashkar : lobby/combat/victoire/défaite/abandon utilisent désormais une surface Components V2 pour les parcours migrés.
- Nettoyage des caches Python/pytest et artefacts temporaires.

## Résultats
- `pytest` : 13/13 tests réussis.
- Compilation : OK.
- Token Discord en clair : non détecté.
- `ECONOMY_DATABASE_URL` : conservé comme variable externe.
- Assets principaux du Hub : présents.
- `ui_v2.py` : aucun Select/UserSelect.
- Tour d'Ashkar : renderer V2 ajouté aux parcours de combat principaux.

## Important avant ouverture publique
Les tests locaux ne peuvent pas simuler parfaitement l'API Discord réelle, les permissions du serveur, les interactions expirées, les limites côté Discord, ni la concurrence réelle de plusieurs joueurs. La build est donc une Release Candidate, pas une certification absolue de production.

Le code contient encore des classes Select historiques servant d'adaptateurs de logique. Les overrides V2 empêchent leur ajout dans les surfaces joueur prévues, mais elles n'ont pas été supprimées physiquement afin d'éviter une réécriture risquée de la logique métier juste avant lancement.

## Recommandation de lancement
Déployer cette RC sur le serveur de test, faire un smoke-test réel avec 2 à 4 comptes sur chaque lieu, puis ne corriger que les anomalies bloquantes avant de figer la release publique.
