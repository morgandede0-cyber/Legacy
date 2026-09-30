# LegacyBot V1.61 — Monde & Forge de KHAZ'GORAM

Cette version se greffe sur **LegacyBot V1.60 Gazette**.

## Monde
- `/legacy` installe désormais la carte du **Monde d'Elyndor**.
- Deux destinations accessibles : **Legacy** et **La Forge de KHAZ'GORAM**.
- Les futures régions restent sous le brouillard.
- Legacy ouvre la ville V1.60 existante dans une session privée.
- Un bouton **Monde** a été ajouté au hub de Legacy.

## KHAZ'GORAM
- Nouvelle région séparée de Legacy.
- Forge géante + PNJ **Thorgar**.
- Achat du premier équipement Commun en **Gold**.
- Améliorations Rare → Épique → Mythique → Légendaire en **Pouciel**.
- Le Pouciel est stocké mais sa méthode normale d'obtention sera ajoutée plus tard.
- Une commande admin de test `/legacy_dev_wallet` permet de créditer du Pouciel pendant le développement.

## Équipement
- 3 branches : Attaque, Défense, Vitesse.
- 5 raretés : Commun, Rare, Épique, Mythique, Légendaire.
- Menu 3×3, équipement automatique.
- Une amélioration remplace la pièce précédente.
- 6 emplacements disponibles aux premiers paliers ; Casque/Gantelets/Bottes apparaissent à partir du Mythique selon les assets fournis.
- Tous les équipements donnent des PV.
- Set complet : +5/+10/+15/+20/+25 % PV selon la rareté.
- Spécialisation : +2/+4/+6/+8/+10 % selon la rareté.
- `/equipement` affiche le 3×3 et les statistiques.

## Arène / JcJ
- Les bonus d'équipement sont injectés dans le moteur de combat V1.60 existant.
- ATK augmente les dégâts ; DEF réduit les dégâts ; Vitesse agit sur initiative/esquive ; tous les sets augmentent les PV.
- Esquive plafonnée à 15 %.
- Champions I → X recalibrés : progression fixe, sans scaling caché sur le joueur.
- Champion X vise environ le niveau d'un joueur équipé en Légendaire complet.
- Les combats contre amis utilisent les mêmes bonus d'équipement.

## Compatibilité
- Base économique V1.60 conservée : le Gold de la forge utilise `players.wallet_gold` dans `data/legacy.sqlite3`.
- Le Pouciel et l'équipement ajoutent leurs propres tables dans la même base SQLite.
- Gazette et systèmes V1.60 conservés.
