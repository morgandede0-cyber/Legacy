# V2.50 — Gazette journal quotidien

- Date et numéro d'édition actualisés automatiquement chaque jour.
- Une publique volontairement courte, style journal.
- Article complet caché derrière `📰 LIRE L’ARTICLE` (réponse privée au lecteur).
- Joueur du jour calculé à partir des faits marquants enregistrés.
- Plus gros gagnant et plus gros perdant du casino sur la période, avec phrase moqueuse tournante pour le perdant.
- Maximum 4 faits marquants dans l'article pour éviter la surcharge.
- Petit chiffre du jour (parties de Taverne) quand disponible.
- Si aucune donnée : publication maintenue avec une brève « Rien à signaler ».
- Chaque édition est figée en base dans `gazette_editions`; le bouton continue donc à ouvrir le bon article après redémarrage.
- Aucun événement n'est inventé : les rubriques absentes sont simplement omises.
