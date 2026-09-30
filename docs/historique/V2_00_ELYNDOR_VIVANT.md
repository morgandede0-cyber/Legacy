# Altherya V2.00 — Elyndor Vivant

Cette version pose le socle de la nouvelle identité d'Altherya sans réinitialiser la base existante.

## Monde vivant
- Elarwyn et Vorak possèdent désormais des phénomènes régionaux tournants toutes les 3 heures.
- L'état régional est visible dans l'interface de destination d'expédition.
- Le système est déterministe et ne nécessite ni tâche de fond ni nouvelle base, ce qui le rend sûr après redéploiement Coolify.

## Destinations nommées
Les anciennes Destination 1 à 5 ont reçu des noms et descriptions propres au lore, sans changer leurs clés internes : aucune migration des expéditions existantes n'est nécessaire.

Elarwyn : Lisière des Chênes, Clairière d’Aelwen, Bois des Murmures, Bois Maudit, Cœur d’Elarwyn.

Vorak : Pied de Vorak, Galeries de Khar, Faille Rouge, Gouffre des Titans, Cime de Vorak.

## /profil
Nouvelle commande publique `/profil [joueur]` : avatar Discord, niveau/XP, Gold poche/banque, combats, victoires, expéditions, succès, réputations Taverne/Ruelle/Casino/Arène, équipement et expédition active.

## Compatibilité
- Aucun fichier SQLite livré.
- Les clés d'expédition existantes sont conservées.
- Le pont Oddium et le centre de commandement `/admin` sont conservés.
