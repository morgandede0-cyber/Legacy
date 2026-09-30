"""Présentation du tableau de bord du Château, sans dépendance à Discord.

Les magasins de données sont injectés pour faciliter les tests et éviter
les imports circulaires avec main.py.
"""
from progression import level_from_xp


def dashboard_text(user_id, castle_store, economy, expedition_store=None):
    profile = castle_store.profile(user_id)
    level, current, needed = level_from_xp(profile['xp'])
    balance = economy.get_balance(user_id)
    available = castle_store.daily_available(user_id)
    quests, _ = castle_store.quests(user_id)
    done = sum(q['progress'] >= q['target'] for q in quests)
    claimed = bool(quests) and all(q['claimed'] for q in quests)
    quest_status = ('🎁 Récompense des quêtes disponible' if done == len(quests) and not claimed
                    else '✅ Récompense des quêtes récupérée' if claimed
                    else f'📋 Quêtes : {done}/{len(quests)} terminées')
    expedition_status = '🧭 Expéditions : consulter les Petites Annonces'
    if expedition_store is not None:
        run = expedition_store.active_run(user_id)
        if run is not None:
            expedition_status = '🧭 Une expédition est en cours'
    return ('🏰 **TABLEAU DE BORD PERSONNEL**\n\n'
            f'👤 **Niveau {level}** • XP : **{current}/{needed}**\n'
            f'💰 **Gold : {balance.wallet:,}** en poche • **{balance.bank:,}** en banque\n\n'
            f"🎁 Récompense journalière : **{'Disponible' if available else 'Déjà récupérée'}**\n"
            f'{quest_status}\n{expedition_status}\n\n'
            f"⚔️ Arène : **{profile['wins']}** victoire(s) • **{profile['losses']}** défaite(s)\n"
            'Les récompenses et activités se consultent dans leurs lieux respectifs.').replace(',', ' ')
