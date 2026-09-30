# Altherya V2.16 — Full Components V2

Passe globale de migration visuelle.

- Monde d’Elyndor et hub Altherya en LayoutView V2.
- Altherya : Taverne, Marché, Banque, Forge, Arène, Petites annonces, Ruelle sombre et Château rendus via Container/TextDisplay/MediaGallery/Separator/ActionRow.
- Forêt d’Elarwyn et Mont Vorak intégrés à la navigation V2.
- KHAZ’GORAM : renderer principal et carrousels migrés en Components V2.
- Tour d’Ashkar conservée dans la navigation globale avec ses mécaniques de combat.
- Marché achat/histoire et Forge amélioration migrés vers le renderer V2, y compris leurs changements de page.
- Les interfaces de sélection visibles n’utilisent plus de Select : boissons, ressources à vendre, classes, joueurs/cibles, PNJ et administration passent par boutons, pagination ou Modal ID.
- Conservation des mécaniques, données, économie commune PostgreSQL et bank_gold propre à Altherya.
- Les composants sont paginés/compactés afin de rester sous les limites Discord.

Validation : `python -m compileall` OK.
