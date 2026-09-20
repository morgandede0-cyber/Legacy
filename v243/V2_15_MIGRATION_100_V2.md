# Altherya V2.15 — migration globale Components V2

Cette version installe un adaptateur V2 global sur les surfaces de lieux historiques :
- Monde d'Elyndor
- Altherya
- Forêt d'Elarwyn
- Mont Vorak
- KHAZ'GORAM
- Tour d'Ashkar
- Marché
- Taverne
- Banque
- Forge
- Arène
- Petites annonces
- Ruelle sombre
- Château

Les écrans image + texte + boutons traversant `edit_with_asset` sont désormais composés en `LayoutView`, `Container`, `TextDisplay`, `MediaGallery`, `Separator` et `ActionRow`.
Les Select ne sont jamais rendus par l'adaptateur V2.

La migration est volontairement centralisée afin de conserver les callbacks et règles métier existants sans toucher à l'économie partagée avec Oddium.
