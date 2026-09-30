# Altherya V2.63.5 — Arène sans classes, techniques par niveau

## Modifications
- Suppression du choix de classe dans le défi du Champion et le duel amical. La Tour d'Ashkar conserve volontairement son ancien système de classes : ses dépendances `CLASSES` et `class_line` restent dans `arena_engine.py` uniquement pour éviter une régression hors Arène.
- Chaque joueur dispose de Coup rapide, Coup puissant et Garde. Le bouton Techniques ouvre des pages de trois techniques maximum, sans menu déroulant, avec retour et recharge visible.
- Techniques apprises automatiquement aux niveaux 3, 6, 9, 12, 15, 18, 21 et 24. Déblocage et recharge vérifiés côté serveur, et pas uniquement dans l'interface.
- PV du joueur en Arène : 100 + 12 par niveau supplémentaire, sans plafond. Le niveau n'est pas un verrou d'accès.
- Rokhan est toujours le même Champion pour chaque joueur. Il commence à 100 PV, gagne 20 PV et +4 % de dégâts de base par victoire du joueur, avec défense/vitesse progressives. La progression est individuelle et ne change pas après une défaite.
- Le nombre de victoires Champion n'est plus plafonné à dix. Les anciens paliers de succès (1, 3, 5, 7, 10) sont conservés.
- Le moteur économique conserve la mise minimale 1 Gold, maximale 500 Gold, et le règlement idempotent.
- Ajout de « Mes techniques » dans le panneau Arène pour afficher les techniques apprises et les prochaines.

## Contrôles
- Compilation de tous les modules Python : OK.
- Simulation locale de 300 combats complets à différents niveaux de Rokhan : OK.
- Tests de déblocage des techniques, recharge, dégâts et progression des PV : OK.
- Vérification statique : aucun sélecteur de classe n'est utilisé dans l'Arène.

## Limites de validation
- Pas de connexion au serveur Discord : vérifier en conditions réelles les transitions Components V2, la publication dans /succes, les duels, les mises et le portefeuille partagé.
- Les anciennes définitions de classes restent dans le moteur parce que la Tour d'Ashkar les importe ; les supprimer casserait cette activité.
- Les statistiques sont une première proposition d'équilibrage, à affiner après retours de combats réels.
