# V1.37 — Correctif fin de combat Arène

Correction du cas où l'Arène pouvait déjà considérer une bataille comme terminée alors que Discord affichait encore l'ancien tour et ses boutons.

Le résultat final est désormais affiché immédiatement après le règlement de la bataille, avant les écritures non critiques (journal, progression, logs). Une erreur dans un de ces systèmes secondaires ne peut donc plus laisser un ancien panneau de combat cliquable à l'écran.

Les boutons de l'ancien tour sont remplacés par le menu principal de l'Arène dès la fin réelle du combat.
