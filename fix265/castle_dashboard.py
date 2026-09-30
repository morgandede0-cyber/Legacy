"""Tableau de bord du Château. Données injectées pour éviter les imports circulaires."""
from progression import level_from_xp

def dashboard_text(uid, castle_store, economy, expedition_store=None):
    profile = castle_store.profile(uid)
    level, current, needed = level_from_xp(profile['xp'])
    balance = economy.get_balance(uid)
    quests, _ = castle_store.quests(uid)
    completed = sum(q['progress'] >= q['target'] for q in quests)
    claimed = bool(quests) and all(q['claimed'] for q in quests)
    status = ('Déjà récupéré' if claimed else 'Disponible' if quests and completed == len(quests) else 'En cours')
    expedition = 'Aucune expédition en cours'
    if expedition_store is not None and expedition_store.active_run(uid) is not None:
        expedition = 'Expédition en cours'
    return (f'🏰 **TABLEAU DE BORD PERSONNEL**\n\n'
            f'⭐ Niveau **{level}** • XP **{current}/{needed}**\n'
            f'💰 **{balance.wallet:,} Gold** en poche • **{balance.bank:,} Gold** en banque\n\n'
            f'📋 Quêtes quotidiennes : **{completed}/{len(quests)}**\n'
            f'🎁 Récompense des quêtes : **{status}**\n'
            f'🧭 {expedition}\n'
            f'⚔️ Combats : **{profile["wins"]}** victoire(s) • **{profile["losses"]}** défaite(s)').replace(',', ' ')
