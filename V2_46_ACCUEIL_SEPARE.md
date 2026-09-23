# Altherya V2.46 — Accueil séparé

Le RPG V2.45 reste dans `main.py`. Le nouvel onboarding est isolé dans `accueil.py` et tourne dans le même bot/processus.

## Commande
`/setup_accueil` dans le salon #bienvenue.

## Parcours
Langue → Pseudo (modale) → Règlement → Entrer dans le Royaume.

## Variables Coolify optionnelles
- `MEMBER_ROLE_ID` : ID du rôle attribué à la fin. Si absent/0, l'accueil fonctionne sans attribution de rôle.
- `RULES_CHANNEL_ID` : ID du salon règlement. Si absent/0, le bouton « Voir le règlement » est masqué.

Le bot doit avoir `Gérer les pseudos` pour appliquer le pseudo et `Gérer les rôles` si MEMBER_ROLE_ID est utilisé. Son rôle doit être placé assez haut dans la hiérarchie Discord.

L'état d'accueil est stocké séparément dans `data/onboarding.sqlite3`. L'économie RPG/PostgreSQL n'est pas modifiée.
