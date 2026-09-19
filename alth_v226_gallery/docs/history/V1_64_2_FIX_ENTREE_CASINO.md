# Legacy V1.64.2 — FIX ENTRÉE CASINO

## Correction
Le paiement du Vigile débitait correctement les 150 Gold et accordait le pass journalier, mais l'ouverture de la salle échouait ensuite dans `casino_home_content()` avec un `NameError` car `max_bet` n'était pas défini dans cette fonction.

## Fix
Ajout de :
```python
max_bet = VIP_MAX_BET if loyalty.get("vip") else MAX_BET
```

Le joueur est maintenant envoyé dans la salle clandestine immédiatement après paiement, invitation ou accès VIP.
