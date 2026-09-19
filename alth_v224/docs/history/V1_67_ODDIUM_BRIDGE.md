# Altherya V1.67 — Pont Oddium

- Altherya devient l'autorité unique du Gold partagé avec Oddium.
- API privée authentifiée : solde, débit/crédit atomique et événements.
- `wallet_gold` est partagé ; `bank_gold` reste exclusivement Altherya.
- Transactions Oddium idempotentes dans `external_gold_transactions`.
- Événements Discord dédupliqués dans `external_bridge_events`.
- Les paris Oddium sont publiés dans le salon `/logs` configuré.
- Les tickets Oddium gagnés/perdus/remboursés sont publiés dans `/succes` avec le style Altherya.
- Code rangé sous `integrations/oddium/`.
