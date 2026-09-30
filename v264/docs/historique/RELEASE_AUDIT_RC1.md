# ALTHERYA — Audit Release RC1

Date : 2026-09-19
Base auditée : V2.16 Full Components V2

## Tests exécutés
- Compilation Python complète : OK.
- Suite pytest : 6/6 tests OK.
- Références littérales aux assets principaux : 0 fichier manquant détecté.
- Recherche de token Discord en clair : aucun token réel détecté.
- Configuration économie : ECONOMY_DATABASE_URL reste externe via variable d'environnement.
- Nettoyage : suppression des __pycache__, .pyc et déplacement des notes de migration V2 historiques dans docs/history.
- Ajout de pytest.ini pour que `pytest` fonctionne directement depuis la racine.

## Points validés statiquement
- Le projet compile intégralement.
- Les tests existants couvrant notamment accès admin et économie partagée passent.
- Aucun asset référencé littéralement via PLACES/EVENTS/ASSETS n'est absent.
- Aucun secret Discord réel n'est empaqueté dans les sources contrôlées par l'audit.

## Blocages / risques restant avant ouverture publique
### 1. Migration Components V2 pas réellement totale
L'audit statique retrouve encore des `discord.Embed` et des anciennes classes `discord.ui.Select`/`UserSelect` dans le code. Certaines anciennes classes servent seulement d'adaptateurs internes et ne sont plus rendues, mais des embeds restent utilisés dans plusieurs parcours (notamment Tour d'Ashkar/combat, notifications et certaines surfaces d'administration/progression).

Conclusion : la V2.16 ne peut pas être certifiée « 100 % V2 » sur la seule base du code actuel.

### 2. Couverture de tests automatisés trop faible
La suite actuelle ne contient que 6 tests. Elle ne couvre pas automatiquement l'ensemble des interactions Discord : Marché, Taverne, Banque, Forge, Arène, Petites annonces, Ruelle sombre, Château, Elarwyn, Vorak, KHAZ'GORAM, Ashkar, combats, double-clics, timeouts et redémarrages.

### 3. Tests réels Discord/Coolify indispensables
Les limites de composants, les interactions expirées, les permissions, les pièces jointes et les modifications de messages ne peuvent pas être certifiés par compilation seule. Une bêta fermée sur le vrai serveur reste nécessaire.

## Décision RC1
Le code est proprement compilable et les tests existants passent, mais l'audit ne recommande pas de qualifier cette build de version finale publique tant que les surfaces legacy restantes et les parcours Discord réels n'ont pas été validés.
