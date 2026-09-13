# V1.64 — Expéditions : carrousels + suivi en direct

## Préparation simplifiée
La préparation d'une expédition se fait maintenant par une suite de 4 menus carrousel :
1. choix de l'outil ;
2. choix de la destination ;
3. choix de l'objet 1 ;
4. choix de l'objet 2 ;
puis un récapitulatif et le bouton **Lancer l'expédition**.

## Interface d'expédition en cours
Au lancement, le bot crée un vrai message Discord de suivi avec une **image d'expédition en cours générée directement dans le code**. Cette image reprend la destination sélectionnée, l'outil, le sac et les deux objets.

Le même message affiche :
- destination, danger et équipement ;
- timer restant ;
- barre de progression ;
- nombre d'items récoltés ;
- les 8 derniers logs de drops.

## Actualisation
- Le timer est actualisé au minimum toutes les 60 secondes.
- Chaque drop possède sa propre heure planifiée.
- Dès qu'un drop arrive, le compteur et les logs sont immédiatement actualisés sur le même message.
- Les drops restent enregistrés en base SQLite et le suivi reprend après un redémarrage du bot.
- À la fin, le bouton **Récupérer les loots** devient disponible.
