# V1.36 — Outils cooldowns dans /admin

Ajouts au panneau `/admin` :

- **Cooldowns ON/OFF** : active ou désactive globalement les cooldowns temporisés Legacy.
- **Reset cooldown joueur** : remet immédiatement à zéro les cooldowns temporisés d'un membre (Ruelle sombre : vol/crime, Champion d'Arène).
- **Annuler ban Ruelle** : supprime le bannissement temporaire de 5 h appliqué après un braquage raté.

Les limites journalières (par exemple les 3 combats amicaux par jour) restent des limites journalières et ne sont pas supprimées par le bouton de reset cooldown.

Toutes les actions sont enregistrées dans les logs administrateur.
