# LegacyBot V1.22 — Hub fixe multijoueur

## Changements

- Suppression de l’animation de déplacement depuis le Hub central.
- Le Hub devient un message public permanent dans un salon Discord.
- `/legacy` sert désormais à installer ou déplacer ce Hub et nécessite la permission **Gérer le serveur**.
- Un seul Hub est conservé : réutiliser `/legacy` supprime l’ancien avant d’en publier un nouveau.
- Chaque clic sur une destination ouvre une **session éphémère privée** au joueur.
- Les actions d’un joueur ne modifient plus le Hub public et ne changent pas l’interface des autres joueurs.
- `Retour en ville` ferme la session personnelle : le joueur retrouve naturellement le Hub fixe dans le salon.
- L’identifiant du salon et du message Hub est conservé dans `data/hub_message.json`.
- Au redémarrage, le bot rattache automatiquement les boutons persistants au Hub existant.

## Installation

1. Démarrer le bot.
2. Aller dans le salon qui doit accueillir la Place centrale.
3. Lancer `/legacy` avec un compte ayant **Gérer le serveur**.
4. Le Hub est publié une seule fois dans ce salon.
5. Les joueurs utilisent directement ses boutons ; leurs écrans de jeu sont privés.
