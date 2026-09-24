# V2.54 — Correctifs latence / interactions

- Les interactions lentes sont acquittées immédiatement avec `defer` avant le traitement des boissons de Taverne.
- Les réponses de la Taverne utilisent automatiquement `followup` après un defer, ce qui évite les `Unknown interaction` causés par une réponse tardive.
- `safe_defer` gère proprement une interaction déjà expirée au lieu de générer une cascade d'erreurs Sentinelle.
- Correction du Marché/Histoire : suppression des réponses `embed=` incompatibles avec Components V2 ; rendu via la surface V2.
- Sentinelle : une pointe isolée de latence Gateway > 5 s n'est plus classée immédiatement comme critique. Alerte seulement après 3 contrôles consécutifs dégradés.
- Aucun changement sur l'économie, le Gold partagé, les données joueurs ou le reset Bêta.
