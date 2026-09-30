# Audit de maintenance — Altherya V2.63

## Périmètre
Archive `IV_V2_63_CORRECTIFS_EXPEDITIONS_ARENE_MOBILE.zip` ; audit statique et rangement conservateur. **Aucun test réel Discord, PostgreSQL ou SQLite de production n'a été effectué.**

## Nettoyage effectué
- Déplacé l'historique des 110 notes de version et guides anciens vers `docs/historique/`. Les guides d'installation, de réinitialisation officielle et de pont Oddium restent à la racine.
- Supprimé les caches Python et pytest présents dans l'archive ; aucune donnée utilisateur n'a été supprimée.
- Supprimé la constante `DISPLAY_MODE_FILE` inutilisée de `main.py` (la gestion effective des préférences passe par `display_mode.py`).
- Ajouté `tools/audit.py` pour vérifier syntaxe et redéfinitions accidentelles des fonctions/classes à chaque mise à jour.

## Constats importants
1. `main.py` est monolithique (~8 000 lignes) et mélange navigation, commandes, UI, événements et règles. Découpage progressif conseillé **avec tests d'intégration** ; déplacement automatique risqué à cause des références croisées et de l'initialisation de l'économie au démarrage.
2. Onze classes de vues ont deux définitions dans `main.py` : la seconde est une **extension V2 volontaire** qui conserve la classe originale via `_NomBase`. Les supprimer en tant que « doublons » casserait des interfaces.
3. Le `README.md` décrit encore la version Legacy V1 et `/legacy` ; il n'est pas une documentation fiable des fonctionnalités V2.63.
4. La logique du Champion enchaîne `handle_battle_action -> run_bot_turn -> _edit_arena_surface`, et le combat peut commencer par un tour de bot. Cela ne garantit pas le bon fonctionnement réel du webhook éphémère : test Discord requis.
5. Les nouveaux boutons « Voir les butins », le gain d'XP du petit larcin et le libellé VIP sont présents dans `main.py`. Leur validation de bout en bout demande un serveur de test.
6. `pytest.ini` pointe vers `tests/`, absent de l'archive : aucune suite de régression automatisée n'est fournie.

## À vérifier avant mise en production
- Arène : Champion qui commence, Champion après action du joueur, fin de combat et timeout.
- Expéditions : affichage des butins pour chaque destination, sur PC et mobile.
- Petit larcin : gain de 5–10 XP uniquement après succès, gestion du délai de 30 min.
- Vigile : statut VIP et paiement normal, coût Gold débité une seule fois.
- Podium : rendu mobile sur plusieurs tailles d'écran.
- Migration PostgreSQL/SQLite : démarrage sur une copie de base, sans déclencher de reset.

**Règle de maintenance :** lancer `python tools/audit.py` à chaque mise à jour et ajouter des tests fonctionnels au fur et à mesure du découpage de `main.py`.
