# Correctif Château et quêtes quotidiennes

Base : V2.63 audit/rangement. La V2.64.1 Banque est écartée.

- Château : nouveau bouton « Mon tableau de bord » dans CastleView ; vue dédiée avec actualisation et retour au Château.
- Tableau de bord : niveau, XP, Gold poche/banque, progression des six quêtes, statut de leur récompense, expédition en cours et victoires/défaites.
- Quêtes quotidiennes : le bouton de récompense globale 6/6 devient exactement « Déjà récupéré », gris et désactivé après réclamation. La vue est reconstruite immédiatement à partir du statut stocké.
- Banque : aucune modification.

## Limites
Tests unitaires hors réseau et compilation effectués ; pas de connexion au serveur Discord réel, pas de validation d'interface mobile/PC en conditions réelles ni de connexion à la base PostgreSQL partagée avec Oddium. Aucun fichier de données existant n'est modifié.
