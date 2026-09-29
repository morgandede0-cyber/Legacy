# V1.38 — Correctif Arène éphémère

- Correction de `discord.errors.NotFound: 404 Not Found (10008): Unknown Message` pendant les tours du Champion.
- Les panneaux d'Arène ouverts depuis le Hub sont des réponses Discord éphémères.
- Les tours automatiques du Champion, les timeouts de 60 secondes et les fins de combat utilisent désormais `Interaction.edit_original_response()` au lieu de `Message.edit()`.
- Les boutons et le journal restent mis à jour sur le même panneau privé.
- Aucun changement d'équilibrage.
