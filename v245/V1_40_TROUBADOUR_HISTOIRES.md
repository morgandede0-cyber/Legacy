# LegacyBot V1.40 — Troubadour & Histoires

- Nouveau PNJ **Troubadour** dans la Taverne avec son image dédiée.
- Bouton **Voir le Troubadour** depuis la Taverne.
- Menu du Troubadour avec bouton **Histoire**.
- Livre graphique à **30 pages** pour la Saison 1, une page = un chapitre.
- Navigation **Page précédente / Page suivante**.
- Chapitre 1 gratuit et accessible immédiatement.
- Chapitres 2 à 30 verrouillés par les groupes d'objets [01] à [29].
- Les objets requis sont affichés directement sur la page du livre avec progression 0/1 ou 1/1.
- Déblocage séquentiel : un chapitre ne peut être débloqué qu'après le précédent.
- Au déblocage, les 4 objets requis sont consommés et le chapitre reste débloqué définitivement.
- Nouvelle catégorie **Histoire** chez le Marchand avec carrousel d'objets dédiés.
- Prix de base provisoire des objets d'Histoire : **100 Gold par objet**, centralisé dans `story_engine.py` pour modification facile.
- Le groupe [30] est conservé dans les données mais n'est pas vendu/utilisé dans la Saison 1 de 30 chapitres ; le Chapitre 30 utilise [29].
- Les 30 titres/textes sont volontairement en placeholders en attendant le contenu narratif fourni ultérieurement.
- Déblocages et achats sont persistants dans SQLite et journalisés dans `/logs`.
