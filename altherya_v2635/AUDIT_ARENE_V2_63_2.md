# Altherya V2.63.2 — Audit et correctifs de l'Arène

## Causes trouvées
- `_legacy_view_to_v2` ne convertissait que les boutons : les `Select` de choix de classe Champion, choix de classe duel et `UserSelect` de l'adversaire disparaissaient.
- `ChampionClassSelect.callback`, `FriendClassSelect.callback` et `FriendLobbyView.ready_cb` essayaient de modifier `content` d'un message Components V2 (HTTP 400 / 50035).
- `finish_battle_interaction` utilisait `edit_original_response(content=..., embeds=..., view=ArenaView())` sur le panneau Components V2, provoquant le même problème à la fin d'un combat.
- Les anciens boutons de tours pouvaient être réutilisés, et le délai de forfait pouvait se déclencher en concurrence avec une action.

## Correctifs
- Conservation des menus de sélection dans des ActionRow natives de LayoutView.
- Mise à jour des choix de classe, de l'attente du second joueur et du résultat via LayoutView/TextDisplay, sans `content`.
- Verrou par combat pour les actions et le forfait ; refus des boutons des anciens tours.
- Conservation du moteur de dégâts, de l'économie, des mises et des profils de Champion existants.

## Contrôles
- Compilation Python de l'ensemble des modules : OK.
- Vérifications statiques : conversion des Select, callbacks Components V2, résultat V2, verrouillage et invalidation des anciens boutons.
- Tests d'intégration Discord non exécutés : tester le Champion (premier tour humain et premier tour IA), duel amical (deux comptes), résultat et délai de forfait après déploiement.
