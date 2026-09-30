# V2.63.4 — Progression des Champions

- Niveau requis par Champion I→X : 1, 2, 4, 6, 8, 10, 12, 15, 18, 22.
- Le verrou est visible dans le menu, vérifié à l'entrée, puis revérifié transactionnellement par ArenaStore avant tout prélèvement de Gold.
- La progression existante (`champion_wins`) est conservée ; aucune migration ni remise à zéro.
- Champion : PV +6,5 % par rang après le premier ; dégâts +3,5 %, défense +1,4 point et vitesse +2,5 % par rang. La classe et le comportement stratégique restent propres à chaque Champion.
- Les PV hors Arène et les duels amicaux ne changent pas. Le niveau du joueur continue d'influencer ses PV d'Arène avec le plafond existant.
- Compilation de tous les modules Python : OK.
- Tests d'intégration Discord et de combat en production : non exécutés.
