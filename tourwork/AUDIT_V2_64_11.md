# Audit correctif Altherya — V2.64.11

Base : Altherya_V2_64_10_CORRECTIF_ACCES_TOUR

## Corrections issues des logs du 30/09/2026 → 01/10/2026

### 1. Ruelle sombre — Voler un joueur
- Suppression de la redéfinition tardive de `ThiefTargetView` qui remplaçait le `UserSelect` par une modale « Rechercher une cible ».
- Le parcours actif utilise désormais le vrai `discord.ui.UserSelect`.
- Le convertisseur Components V2 conserve les Select/UserSelect dans des ActionRows ; le menu n'est donc plus perdu lors de la conversion en LayoutView.
- Impossible de cibler un bot ou soi-même.
- Le callback acquitte l'interaction immédiatement avant le calcul du vol.
- La réponse finale passe par `interaction_reply` après defer.

### 2. Ruelle sombre — Voler un PNJ
- Le callback du PNJ acquitte maintenant l'interaction avant `DARK_STORE.steal_npc()`.
- Les réponses cooldown, succès, échec et prise sur le fait utilisent `interaction_reply`.
- Suppression de l'ancienne redéfinition tardive de `NPCTargetView` qui déclenchait manuellement un ancien callback sans defer.
- Le résultat du vol reste affiché même lorsque le calcul, la réputation ou les journaux prennent du temps.

### 3. Petit larcin — Unknown Webhook
- `temporary_popups.send_temporary_followup()` ignore proprement les webhooks d'interaction expirés (10015/10062) au lieu de faire remonter une exception dans `discord.ui.view`.
- Les anciens composants ne font donc plus planter le callback lorsqu'ils sont cliqués après expiration du webhook.

### 4. Components V2 — content/embed incompatibles
- Les écrans Components V2 n'envoient plus `content`/`embed` dans les modifications de message concernées.
- `WorldHubV2 → KHAZ'GORAM` passe maintenant par le renderer Components V2 de la Forge.
- Les helpers V2 évitent également `content=None` sur les endpoints Components V2.
- La gestion de la Tour utilise le renderer V2 et accepte aussi une interaction déjà deferée.

### 5. Arène — fin de combat
- Le code actuel de l'archive utilise `_edit_arena_surface()` pour la fin de combat, qui construit un écran Components V2 au lieu d'envoyer `content=` directement.
- Cela corrige le défaut 50035 observé dans les logs sur `finish_battle_interaction`.
- Le correctif est conservé pour les fins de combat et le compte à rebours de victoire.

### 6. Blackjack — KeyError sur une partie terminée
- Ajout d'un verrou de finalisation par session pour empêcher deux clics/timeout simultanés de régler la même partie.
- L'état est marqué `finished` avant les opérations asynchrones.
- L'état n'est supprimé qu'après l'affichage du résultat.
- `show_blackjack()` tolère désormais une session déjà disparue.
- Le timeout ne rembourse plus une partie déjà en cours de finalisation.

### 7. Interactions expirées
- `edit_with_asset()`, `edit_v2_surface()`, le renderer de la Tour et le renderer de la Forge absorbent proprement les `10015 Unknown Webhook` / `10062 Unknown Interaction` lorsqu'un ancien panneau ne peut plus être édité.
- Le mode PC/Mobile initial acquitte désormais immédiatement les interactions avant de charger les écrans.

## Avertissement restant
Le log signale :
`Privileged message content intent is missing, commands may not work as expected.`

C'est un réglage Discord Developer Portal, pas une exception Python. Il faut activer **Message Content Intent** dans le portail uniquement si des commandes/préfixes ou fonctionnalités qui lisent le contenu des messages en ont besoin. Je n'ai pas forcé cet intent dans le code afin de ne pas provoquer un refus de connexion si le privilège n'est pas activé côté portail.

## Vérifications locales
- Compilation Python de tous les modules : OK.
- Contrôle AST des classes : OK pour les classes de cibles de la Ruelle ; les redéfinitions restantes concernent d'autres vues de compatibilité historiques et ne sont pas impliquées dans les traces étudiées.
- Tests Discord réels non exécutables dans cet environnement : le paquet `discord.py` n'est pas installé ici. La validation finale doit donc être faite après déploiement sur Coolify.

## Tests à effectuer après déploiement
1. Ruelle → Le Voleur → Voler un joueur → vérifier que le menu déroulant liste les membres.
2. Sélectionner un joueur → vérifier Gold, résultat et cooldown.
3. Ruelle → Le Voleur → Voler un PNJ → tester succès, échec et prise sur le fait.
4. Petit larcin → tester réussite et cooldown.
5. Arène → terminer un combat → vérifier le panneau de victoire et le compte à rebours.
6. Tour d'Ashkar → Entrer → vérifier l'ouverture sans erreur Components V2.
7. Monde → KHAZ'GORAM → vérifier l'écran Forge.
8. Blackjack → cliquer rapidement sur Rester deux fois pour vérifier qu'une seule finalisation est effectuée.
