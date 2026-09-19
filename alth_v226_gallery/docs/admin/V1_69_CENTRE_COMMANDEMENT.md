# Altherya V1.69 — Centre de commandement

- `/admin` devient un tableau de bord avec économie globale et activité administrative.
- Séparation conservée entre Serveur et Joueurs.
- Fiche joueur enrichie avec notes staff privées.
- Historique administratif consultable depuis la fiche.
- Boutons réorganisés : Économie, Progression, Réputations, Inventaire, Succès, Historique, Note staff, Modération.
- Nouvelle table `admin_notes`, migration automatique et non destructive.
- `admin_access.access_role` préparé pour les futurs niveaux de permissions staff.
- Toutes les nouvelles actions sont enregistrées dans `admin_audit`.
