# V2.63.1 — Audit des journaux et correctifs

## Sources
Les deux fichiers de journaux fournis ont le même contenu. Ils contiennent deux occurrences de la même exception HTTP 400/50035 (02:55:45 et 02:55:53), lors des clics sur Forêt d'Elarwyn et Mont Vorak depuis WorldHubV2. Le code essayait d'éditer `content` et de passer à une `discord.ui.View` classique dans un message `IS_COMPONENTS_V2`.

## Correctifs
- Ajout de `_replace_v2_with_legacy` : acquittement de l'interaction, suppression de l'ancienne fenêtre privée V2, ouverture de la destination classique dans une nouvelle fenêtre privée. Le texte, le média et les boutons de destination restent inchangés.
- Correction du parcours Forêt d'Elarwyn / Mont Vorak, y compris le cas de destination inconnue.
- Correction préventive du même type de transition pour la forge de Khaz'Goram.
- Correction préventive du passage à la Tour d'Ashkar depuis WorldHubV2 : nouvelle fenêtre privée au lieu de modifier le message V2 avec un embed et une View classique.

## Autres messages dans les journaux
- `Privileged message content intent is missing` : avertissement de configuration, non responsable des erreurs d'exploration. Les commandes slash sont synchronisées dans ces journaux. Activer Message Content Intent dans le portail développeur uniquement si les fonctionnalités de lecture de messages du bot en ont besoin, et adapter les intents du code.
- `4 combat(s) interrompu(s) remboursé(s) au démarrage` : mécanisme de remboursement signalé ; aucun traceback lié dans les journaux. Ne pas désactiver cette protection sans diagnostic séparé.
- Économie PostgreSQL, synchronisation des 11 commandes, Sentinelle et connexion Gateway : démarrages signalés sans exception dans ces journaux.

## Contrôles
- Compilation de tous les modules Python.
- Vérification statique de l'absence de `edit_message(content=...)` dans `open_exploration_location`.
- Vérification statique des transitions du WorldHubV2 (exploration, forge, tour).
- Pas de test d'intégration sur Discord ni de simulation d'économie réelle : ces parcours doivent être validés après déploiement.

## Limites
Les journaux fournis ne contiennent pas d'erreur supplémentaire distincte. L'audit n'atteste pas que tous les autres parcours du bot sont exempts de bugs ; les autres usages de Components V2 nécessitent des tests interactifs pour confirmer leur contexte exact.
