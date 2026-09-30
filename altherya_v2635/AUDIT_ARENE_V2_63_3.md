# Altherya V2.63.3 — Équilibrage et résultats de l'Arène

## Modifications
- PV joueur en Arène : base 100 au niveau 1, +3 PV par niveau jusqu'à +60 (au lieu de 1 000 +35/niveau). Multiplicateurs de classe conservés. Aucun changement aux PV hors Arène ni aux PV des Champions.
- Exemple Ravageur niveau 1 contre Rokhan (Champion 1) : 100 PV chacun avant équipement.
- Mises Champion et duel : entier entre 1 et 500 Gold. Refus côté fenêtre ET dans ArenaStore pour empêcher le contournement.
- Publication des résultats des combats Champion et amicaux dans le salon configuré via /succes, victoires et défaites, après règlement unique en base. Les succès de palier restent publiés séparément.
- Correction d'un bug préexistant : `branch_total` était non défini dans `announce_achievement_for` et empêchait l'annonce des succès débloqués.

## Vérifications
- Tous les modules Python compilés et analysés syntaxiquement.
- Tests moteur : mises 0, négatives et >500 refusées pour Champion et duel.
- Vérification PV de départ : joueur Ravageur niveau 1 et Champion Rokhan niveau 1 = 100 PV.
- Vérification statique du branchement /succes et de la publication conditionnée au règlement.

## À tester sur Discord
- Champion avec compte niveau 1 et compte niveau élevé ; duel avec deux comptes.
- Vérifier le canal /succes après victoire ET défaite et le déblocage d'un succès de palier.
- Vérifier la synchronisation du portefeuille Gold partagé en production. Les tests Discord et PostgreSQL ne sont pas exécutés ici.
