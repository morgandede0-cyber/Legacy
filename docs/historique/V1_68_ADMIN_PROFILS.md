# Altherya V1.68 — Administration Serveur / Joueurs

- `/admin` séparé en deux catégories : **Serveur** et **Joueurs**.
- **Serveur** : événements, cooldowns globaux, accès délégués `/admin`.
- **Joueurs** : sélecteur Discord unique puis fiche administrative complète du membre.
- Fiche : nom/photo Discord, ID, niveau/XP, poche/banque/total Gold, activité, succès, Taverne, Ruelle, Casino, Arène et Champion.
- Actions depuis la fiche : Gold, niveau, réputations/progression, items/équipements, succès, modération.
- Réputations administrables : consommations Taverne, méfaits Ruelle, cote Arène, victoires Champion et fidélité Casino.
- La fidélité Casino dispose d'un override administratif persistant ; sans override, elle continue d'être calculée depuis les victoires réelles.
- Toutes les modifications utilisent les garde-fous `/admin` existants et sont journalisées.
