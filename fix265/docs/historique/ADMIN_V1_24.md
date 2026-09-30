# Legacy V1.24 — Panneau Admin

Commande `/admin` réservée aux administrateurs.

Fonctions :
- ajouter / retirer du Gold à un membre ;
- ajouter / retirer 1 niveau tout en gardant une progression XP cohérente ;
- activer / désactiver Gold x2 et XP x2 ;
- kick / ban ;
- mute temporaire jusqu'à 28 jours via timeout Discord ;
- mute permanent via rôle `Legacy Muted` ;
- unmute ;
- débloquer / supprimer un succès ;
- ajouter / supprimer Pioche, Hache, Lance ou Sac ;
- ajouter / retirer une ressource ou Invitation clandestine ;
- journalisation des actions admin dans `admin_audit`.

Les événements sont persistants dans SQLite. XP x2 s'applique aux gains XP du système Legacy. Gold x2 s'applique aux récompenses générées par Legacy (quotidiennes, quêtes, Champion, casino sur le bénéfice, crimes et braquages) sans doubler les remboursements de mises ni les transferts PvP.
