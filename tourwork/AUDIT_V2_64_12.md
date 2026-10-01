# Altherya V2.64.12 — Correctif lieux

- Corrigé l’ouverture Forêt d’Elarwyn / Mont Vorak depuis WorldHubV2.
- Suppression de `content=` sur les éditions de messages Components V2.
- Conversion des interfaces d’exploration via `_legacy_view_to_v2`.
- Rafraîchissement d’une zone corrigé avec le même renderer.
- Retour Monde nettoyé pour ne plus transmettre `content=None`.
- `main.py` compilé avec succès.

Cause confirmée par les logs : erreur Discord 50035 `The 'content' field cannot be used when using MessageFlags.IS_COMPONENTS_V2` dans `open_exploration_location`.
