# LegacyBot V1 — Hub interactif

Reconstruction depuis zéro.

## Installation
1. Lance `INSTALLER.bat`.
2. Ouvre `.env` et renseigne `DISCORD_TOKEN`.
3. Optionnel : renseigne `GUILD_ID` pour voir `/legacy` immédiatement sur ton serveur de test.
4. Lance `DEMARRER.bat`.
5. Utilise `/legacy`.

## Hub
8 destinations : Marché, Taverne, Forge, Banque, Arène, Expéditions, Ruelle sombre et Château.
Chaque clic remplace le message par une animation de marche d'environ 2,8 s, puis affiche le décor du lieu.

## Animation
Les GIF sont pré-générés : zoom progressif + oscillation verticale/horizontale pour simuler des pas humains. Cela évite de générer des dizaines d'images en direct et rend la navigation instantanée pour le bot.

Le Château utilise provisoirement un cadrage du hub jusqu'à validation de son illustration dédiée.

## Stack de rendu Legacy
Le nouveau bot est préparé pour cinq moteurs, par ordre de priorité :
1. **resvg + SVG** — moteur principal pour les interfaces dynamiques précises.
2. **pyvips + Pango** — composition/texte haute performance côté Python.
3. **Skia** — dessin direct et rendu graphique avancé.
4. **HTML/CSS + Playwright** — écrans complexes lorsque CSS est plus pratique.
5. **Pillow** — opérations simples, GIFs, recadrage et traitements utilitaires.

`render_stack.py` centralise ces moteurs. Les imports sont paresseux afin qu'un moteur optionnel manquant ne bloque pas tout le bot.

### Windows / dépendances natives
`pyvips` nécessite aussi la bibliothèque native **libvips** installée sur Windows. Pango peut également nécessiter ses bibliothèques natives selon l'installation. `INSTALLER.bat` installe les paquets Python ; les moteurs non disponibles restent détectables sans empêcher le lancement du bot.

Pour Playwright, après l'installation Python, exécuter si nécessaire :
`python -m playwright install chromium`

## Banque (V1.5)

La Banque possède maintenant 4 actions : **Retirer**, **Dépôt**, **Solde**, **Revenir en ville**.

- Le premier retrait de chaque journée (heure de Paris) est gratuit.
- À partir du deuxième retrait du même jour, 10 % du montant retiré est conservé en frais.
- Les dépôts sont gratuits et illimités.
- L'interface de montant utilise `-100`, `-10`, `+10`, `+100`, `MAX`, `Valider`, `Annuler`.
- Les soldes sont persistés dans `data/legacy.sqlite3`.
- Les transactions utilisent SQLite avec `BEGIN IMMEDIATE` pour éviter les doubles dépenses lors de clics concurrents.

Les joueurs nouvellement créés commencent avec 0 Gold sur eux et 0 Gold en banque. L'économie globale pourra alimenter `wallet_gold` plus tard.

## V1.6 — Arène

L'Arène comprend maintenant :
- `Affronter le champion` (1 combat par heure et par joueur)
- `Affronter un ami` (3 combats par jour et par joueur)
- mise de 0 à 500 Gold par joueur
- choix de classe avant le combat : Ravageur / Gardien / Traqueur
- démarrage JcJ uniquement lorsque les deux joueurs sont prêts
- moteur tour par tour avec 4 actions propres à chaque classe
- attaque légère, lourde, ultime et défense avec bonus/malus spécifiques
- ultime avec 2 tours de recharge et 50 % de chance de critique
- 60 secondes maximum pour jouer son tour, sinon défaite par forfait
- fin immédiate au K.O. et retour au menu de l'Arène
- mise débitée de manière atomique au lancement et cagnotte versée une seule fois au gagnant
- combats actifs remboursés automatiquement si le bot redémarre au milieu d'un duel
- limites et combats enregistrés dans SQLite (`data/legacy.sqlite3`)

### Équilibrage de départ
- Ravageur (Tigre) : pression et dégâts
- Gardien (Ours) : résistance et contre-attaque
- Traqueur (Loup) : vitesse, esquive et opportunisme

Les valeurs sont centralisées dans `arena_engine.py` afin de pouvoir les ajuster facilement après les premiers tests joueurs.

## V1.7 — Expéditions + progression d'équipement

- 6 expéditions conservées : Forêt des Brumes, Collines Sauvages, Ruines Anciennes, Marais Putrides, Désert Aride, Montagnes Glaciales.
- Préparation avant départ : outil principal, sac, 2 emplacements accessoires réservés, destination.
- Pioche / Hache / Lance : 5 niveaux (Bois, Pierre, Fer, Or, Diamant).
- Sac : 5 niveaux (8, 14, 22, 32, 45 loots).
- Loot dépend à la fois de la destination ET du niveau/type d'outil.
- Une unité de ressource occupe une place de sac.
- Une expédition active maximum par joueur ; timer persistant en SQLite.
- Les loots sont tirés au lancement et ne peuvent pas être reroll en redémarrant le bot.
- Une fois terminée, le joueur récupère ses ressources depuis le tableau.
- Forge branchée sur les recettes définies pour améliorer Pioche/Hache/Lance/Sac.
- Inventaire de ressources persistant en SQLite.

### Note prototype
Tant que les prix du Marché ne sont pas définis, les profils d'expédition démarrent avec les 4 équipements de niveau 1 afin que toute la boucle puisse être testée. Quand les prix seront fixés, on pourra remplacer ce bootstrap par l'achat réel au marchand sans modifier les tables de loot ni la Forge.

## V1.8 — Nouveau parcours Expéditions
La préparation se déroule maintenant en 3 étapes :
1. Sélection séquentielle des 4 cases d'équipement avec Gauche / Sélectionner / Droite.
2. Validation de l'équipement puis navigation entre les 6 destinations avec Gauche / Sélectionner / Droite.
3. Validation de la destination, récapitulatif final et apparition du bouton Lancer l'expédition.

Le sac choisi est désormais réellement transmis au moteur d'expédition et sa capacité est figée au lancement. Les accessoires 1 et 2 restent volontairement vides en attendant leur futur système.

## V1.9 — Ruelle sombre

La Ruelle sombre possède désormais trois PNJ :

- **Le Voleur (loup)** : vol d'un joueur et crime, deux cooldowns indépendants de 1 h, avec trois issues équiprobables (1/3 chacune).
- **Le Braqueur (tigre balafré)** : mini-jeu persistant de code de coffre à 4 chiffres différents, 7 essais, feedback bien placé / mal placé / incorrect. Échec = amende + interdiction de la Ruelle sombre pendant 5 h.
- **Le Vigile (ours)** : accès par `Invitation clandestine` consommée ou paiement de 250 Gold. L'autorisation est enregistrée en base afin d'être réutilisée lorsque la Salle de jeux clandestine sera codée.

Les valeurs d'équilibrage se trouvent en haut de `dark_alley.py` et peuvent être modifiées facilement.


## V1.10 — Accès journalier à la Salle clandestine
- Une invitation ou le paiement du Vigile donne accès uniquement pour la journée civile en cours (Europe/Paris).
- L'accès expire strictement à 00h00, même si le joueur se trouve déjà dans la salle.
- Toute interaction après minuit doit revalider le pass ; sinon le joueur devra repasser par le Vigile.
- Un pass déjà valide pour la journée ne peut pas être payé/consommé une seconde fois par erreur.

## V1.11 — Salle de jeux clandestine

La salle clandestine est maintenant jouable après validation du Vigile. L'accès reste journalier et expire à 00h00 (Europe/Paris). Si minuit tombe pendant une partie, la partie est interrompue, la mise en cours est rendue et le joueur est renvoyé devant le Vigile.

Jeux disponibles :
- Black Jack interactif : Tirer / Rester.
- Roulette : Rouge, Noir, Pair, Impair, 1-18, 19-36 ou numéro exact.
- Roulette Russe : mini-jeu purement fictif Legacy face à un PNJ mafieux, représenté par un barillet abstrait de 6 cases.
- Machine à sous : rouleaux animés et multiplicateurs selon les triples.
- Courses de chevaux : 4 chevaux avancent en direct d'un point A à la ligne d'arrivée ; le premier arrivé termine la course et le bot revient automatiquement au menu de la salle.

Toutes les mises sont comprises entre 1 et 500 Gold. La mise est débitée atomiquement au lancement et les parties interrompues par un redémarrage du bot sont remboursées automatiquement.

Paiements actuels, centralisés dans `casino_engine.py` / `main.py` pour équilibrage futur :
- Black Jack : victoire x2 ; Black Jack naturel x2,5 ; égalité = mise rendue.
- Roulette : paris simples x2 ; numéro exact x36.
- Roulette Russe fictive : victoire x2.
- Machine à sous : triples x2 à x12 selon le symbole ; deux 7 rendent la mise.
- Course : cheval gagnant x4.
