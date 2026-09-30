# LegacyBot V1.64.2 — déploiement Coolify

Cette archive est prête à être déployée comme **Application Dockerfile** dans Coolify.
Aucun port public ni domaine n'est nécessaire : Legacy est un bot Discord.

## 1. Dépôt Git

Place tous les fichiers de ce dossier à la racine du dépôt GitHub utilisé par Coolify.
Le fichier `.env` réel ne doit jamais être envoyé sur GitHub.

## 2. Application Coolify

- Build strategy : **Dockerfile**
- Base directory : `/`
- Dockerfile location : `/Dockerfile`
- Exposed ports : **aucun**
- Domaine : **aucun nécessaire**

## 3. Variables d'environnement Coolify

Variables obligatoires :

- `DISCORD_TOKEN` : token du bot Discord
- `TZ` : `Europe/Paris`

Variable facultative :

- `GUILD_ID` : ID du serveur Discord de test/production si tu veux la synchronisation locale prévue par Legacy.

Les secrets doivent être renseignés dans Coolify, jamais dans le Dockerfile ou le dépôt Git.

## 4. Stockage persistant

Créer un **Volume mount** :

- Name : `legacy-data`
- Source Path : laisser vide
- Destination Path : `/app/data`

C'est indispensable. Legacy stocke notamment dans ce dossier :

- `legacy.sqlite3` : économie, casino, arène, expéditions, progression, etc.
- `hub_message.json` : état du panneau principal
- `expedition_live/` : rendus temporaires/persistants liés aux expéditions

Ne monte PAS `/app` en entier : cela masquerait le code et les assets inclus dans l'image Docker.

## 5. Déploiement automatique GitHub

Dans Coolify :

- Auto deploy : `Deploy on push (webhooks)`
- Branche de production recommandée : `main`

Après cela :

```bash
git add .
git commit -m "Mise à jour Legacy"
git push origin main
```

Coolify reconstruira et redéploiera Legacy automatiquement. Le volume `/app/data` restera conservé.

## 6. Vérification

Après le déploiement :

- Container : `Running`
- Le bot doit apparaître connecté sur Discord.
- Utilise `/legacy` pour ouvrir le hub.

Les messages Python sont envoyés directement vers les logs du conteneur grâce à `python -u`.

## Remarque Playwright

Le paquet Python Playwright est conservé car il fait partie de la stack Legacy, mais la version V1.64.2 n'utilise actuellement pas Chromium pour les interfaces actives. Le navigateur n'est donc pas installé dans l'image, ce qui évite plusieurs centaines de Mo inutiles. Si une future fonction Legacy utilise réellement `playwright.chromium.launch()`, il faudra alors ajouter l'installation du navigateur au Dockerfile.
