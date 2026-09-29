# Altherya V2.11 — Refonte sans menus déroulants

- Navigation joueur par boutons, pagination et fenêtres modales.
- Tour d'Ashkar : choix de classe par boutons.
- Arène Legacy World Forge : Champions I–X paginés par boutons.
- Taverne : boissons par boutons et défi d'ami par ID Discord.
- Marché : ressources vendables paginées, bouton direct par ressource.
- Arène principale : adversaire par fenêtre ID et classes par boutons.
- Ruelle sombre : cibles joueur par fenêtre ID et PNJ par boutons.
- Administration : joueurs par fenêtre ID, succès paginés par boutons, accès admin sans UserSelect.
- Le socle Components V2 de V2.10 est conservé.
- L'économie PostgreSQL commune Oddium/Altherya et bank_gold Altherya ne sont pas modifiés.

Les anciennes classes Select sont conservées en interne uniquement comme adaptateurs de logique pour éviter de dupliquer les règles métier ; les nouvelles vues visibles ne les montent plus dans l'interface.
