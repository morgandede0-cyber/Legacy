# Altherya V2.20 — Correctifs rush final

- Marché : sécurisation du parcours Histoire sur le renderer Components V2 existant.
- Banque : remplacement du sélecteur -100/-10/+10/+100 par une saisie directe du montant via Modal Discord.
- Forge : accès direct aux 4 équipements (Pioche, Hache, Lance, Sac), disposés en deux rangées de deux boutons côté View avant conversion V2, avec action Améliorer par équipement.
- Petites annonces : l'acceptation lance désormais une mission d'1 heure. Aucun Gold n'est versé au départ. La récompense se réclame sur le panneau ; bouton rouge/verrouillé avant l'échéance, vert une fois disponible.
- Petit larcin : interaction acquittée immédiatement et cooldown dédié ramené à 30 minutes.
- Vigile : pass journalier conservé jusqu'à minuit. Après paiement/invitation/VIP, l'interface devient « Rentrer » au lieu de redemander le paiement.
- Roulette russe : mises à jour compatibles Components V2 + bouton Retour aux jeux avec remboursement de la mise si la partie est quittée.
- Résultats Casino : Rejouer et Menu des jeux conservés.
- Château : Podium et Récompense journalière migrés vers le renderer Components V2 pour éviter les edits content/embed incompatibles avec un message V2.
- Podium : aucun ID Discord brut en fallback ; « Joueur inconnu » est utilisé si le membre n'est pas résolu.
- Nettoyage : caches pytest/python exclus de l'archive finale.
