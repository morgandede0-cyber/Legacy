# LegacyBot V1.64.3 — FIX COMMANDE /legacy

Base : **V1.64.2 FIX_ENTREE_CASINO**.

Correction ciblée de `/legacy` :

- timeout de 8 s pour retrouver/supprimer l'ancien Hub ;
- un ancien Hub introuvable ou inaccessible n'empêche plus la création du nouveau ;
- timeout de 20 s pour publier le nouveau Hub ;
- timeout de 10 s pour terminer la réponse Discord ;
- message d'erreur visible au lieu d'un « réfléchit… » infini ;
- diagnostic détaillé écrit dans les logs du conteneur ;
- aucune autre mécanique de Legacy modifiée.

Le paquet conserve la configuration Docker/Coolify de la V1.64.2.
