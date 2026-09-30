# V2.57 — Audit complet de la progression XP

## Objectif
Éviter qu'un nouveau joueur reste bloqué plusieurs jours au niveau 1 tout en empêchant
le farm de simples clics ou de fonctions sans risque.

## Courbe
XP nécessaire par niveau :
- Niveau 1 → 2 : 100 XP
- Niveau 2 → 3 : 175 XP
- Niveau 3 → 4 : 275 XP
- Niveau 4 → 5 : 400 XP
- Niveau 5 → 6 : 575 XP
- Niveau 6 → 7 : 800 XP
- À partir du niveau 7 : courbe longue historique.

La progression est donc rapide au début, puis ralentit.

## Fonctions vérifiées qui donnent de l'XP
- Tutoriel initial : 25 XP, une seule fois.
- Récompense journalière : 20 XP.
- Taverne : 5 XP par jeu.
- PvP Taverne : 4 XP participation/perte, 10 XP total victoire.
- Casino : 3 XP par partie lancée.
- Arène : 40 XP victoire, 10 XP défaite.
- Forge : 20 / 35 / 60 / 100 XP selon le palier amélioré.
- Petite Annonce : 12 / 16 / 22 / 32 / 50 XP selon rareté.
- Expédition mains nues : 15 XP.
- Expéditions normales : 25 / 40 / 60 / 85 / 125 XP selon profondeur.
- Tour d'Ashkar : XP par étage, boss mieux récompensé.
- Ruelle : larcin, vol PNJ, vol joueur, crime et braquage donnent déjà de l'XP.
- Quêtes journalières : récompense globale XP conservée.

## Fonctions volontairement SANS XP
Aucune XP n'est ajoutée à :
- navigation entre les menus ;
- consultation de profil ;
- banque / dépôts / retraits ;
- achat simple ;
- vente simple de ressources ;
- lecture d'histoire / Gazette ;
- boutons Retour / Actualiser.

Ces actions sont trop faciles à spammer et ne représentent pas une progression de gameplay.

## Exemple nouveau joueur
Sans casino ni Ruelle, un joueur peut déjà approcher/passer le niveau 2 dans une vraie
session de découverte :
- tutoriel : 25
- journalier : 20
- expédition mains nues : 15
- petite annonce commune : 12
- deux jeux de Taverne : 10
= 82 XP

Une seconde activité utile (arène, autre expédition, annonce plus rare, etc.) suffit alors
à franchir les 100 XP du niveau 1.

## Sécurité
Les sécurités existantes sont conservées :
- récompense tutoriel unique ;
- finalisation d'expédition unique ;
- cooldowns/limites des jeux ;
- XP x2 admin continue de fonctionner ;
- aucune modification de l'économie PostgreSQL commune Oddium/Althérya.
