from __future__ import annotations

# Progression globale : chaque niveau devient progressivement plus long.
def xp_needed_for_level(level: int) -> int:
    level = max(1, int(level))
    # V2.57 : démarrage volontairement rapide.
    # L1→2 doit pouvoir se faire en une vraie session de découverte,
    # puis la courbe s'allonge progressivement.
    early = {1: 100, 2: 175, 3: 275, 4: 400, 5: 575, 6: 800}
    if level in early:
        return early[level]
    return int(round((250 + 75 * ((level - 1) ** 1.55)) / 25.0) * 25)


def level_from_xp(xp: int):
    level = 1
    remaining = max(0, int(xp))
    need = xp_needed_for_level(level)
    while remaining >= need:
        remaining -= need
        level += 1
        need = xp_needed_for_level(level)
    return level, remaining, need


# Niveau joueur minimum pour FORGER le palier cible.
FORGE_LEVEL_REQUIREMENTS = {2: 5, 3: 10, 4: 18, 5: 28}

# Coûts Gold : outils / sac. Les matériaux restent la ressource principale.
FORGE_GOLD_COSTS = {
    "tool": {2: 150, 3: 350, 4: 700, 5: 1400},
    "bag":  {2: 200, 3: 450, 4: 900, 5: 1800},
}

# XP mesurée, pensée pour éviter le farm rapide.
XP_REWARDS = {
    "arena_win": 40,
    "arena_loss": 10,
    "casino": 3,
    "tavern_game": 5,
    "tavern_pvp_win": 10,
    "tavern_pvp_loss": 4,
    "larceny_success": 5,
    "npc_theft_success": 7,
    "player_theft_success": 10,
    "crime_success": 12,
    "heist_win": 40,
    "forge_2": 20,
    "forge_3": 35,
    "forge_4": 60,
    "forge_5": 100,
}

EXPEDITION_XP = {
    "forest": 20,
    "hills": 30,
    "ruins": 45,
    "swamp": 70,
    "desert": 100,
    "mountains": 140,
}

# XP des systèmes longs : récompense proportionnelle au temps / risque.
EXPEDITION_TIER_XP = {1: 25, 2: 40, 3: 60, 4: 85, 5: 125}
ASHKAR_FLOOR_XP = {1: 15, 2: 18, 3: 21, 4: 24, 5: 28, 6: 32, 7: 36, 8: 40, 9: 45, 10: 75}
JOB_RARITY_XP = {"common": 12, "uncommon": 16, "rare": 22, "epic": 32, "legendary": 50}
