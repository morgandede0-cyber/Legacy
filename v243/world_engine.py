from __future__ import annotations
import time

DESTINATION_NAMES = {
    'elarwyn_1': ('Lisière des Chênes', 'Les sentiers sûrs où commencent les nouveaux bûcherons et chasseurs.'),
    'elarwyn_2': ('Clairière d’Aelwen', 'Une clairière ancienne où les essences plus robustes apparaissent.'),
    'elarwyn_3': ('Bois des Murmures', 'Les arbres y sont plus vieux et les prédateurs plus audacieux.'),
    'elarwyn_4': ('Bois Maudit', 'Une partie d’Elarwyn que seuls les aventuriers aguerris traversent.'),
    'elarwyn_5': ('Cœur d’Elarwyn', 'Le sanctuaire végétal le plus profond et le plus dangereux de la forêt.'),
    'vorak_1': ('Pied de Vorak', 'Les premières veines de pierre affleurent au pied du massif.'),
    'vorak_2': ('Galeries de Khar', 'D’anciennes galeries où le fer devient plus fréquent.'),
    'vorak_3': ('Faille Rouge', 'Une fracture profonde riche en minerais et fréquentée par les bêtes.'),
    'vorak_4': ('Gouffre des Titans', 'Un réseau brutal où seuls les outils solides résistent.'),
    'vorak_5': ('Cime de Vorak', 'Les hauteurs interdites où reposent les ressources les plus rares.'),
}

WORLD_EVENTS = {
    'elarwyn': [
        ('🌧️', 'Pluie d’Elarwyn', 'La forêt est détrempée. Les pistes sont fraîches et les sous-bois agités.'),
        ('🌿', 'Sève montante', 'Une poussée de sève traverse les vieux arbres d’Elarwyn.'),
        ('🐺', 'Meute en mouvement', 'Des traces nombreuses traversent les chemins de chasse.'),
        ('✨', 'Murmures anciens', 'Une présence inhabituelle semble parcourir le cœur de la forêt.'),
    ],
    'vorak': [
        ('⛈️', 'Orage sur Vorak', 'Le tonnerre roule entre les pics et les galeries grondent.'),
        ('⛏️', 'Veines découvertes', 'Des mineurs signalent de nouvelles veines dans le massif.'),
        ('🦅', 'Prédateurs des cimes', 'Les créatures de Vorak descendent vers les passages rocheux.'),
        ('💎', 'Résonance cristalline', 'Une vibration étrange remonte des profondeurs du mont.'),
    ],
}

def destination_name(key: str) -> str:
    return DESTINATION_NAMES.get(key, (key, ''))[0]

def destination_description(key: str) -> str:
    return DESTINATION_NAMES.get(key, ('', ''))[1]

def current_event(location_key: str, now: int | None = None) -> dict:
    now = int(now or time.time())
    events = WORLD_EVENTS.get(location_key, [])
    if not events:
        return {'emoji':'🌍','name':'Calme','description':'Aucun phénomène notable.'}
    # Rotation stable toutes les 3 heures : monde vivant sans tâche de fond ni migration DB.
    slot = now // (3 * 3600)
    emoji, name, description = events[slot % len(events)]
    remaining = (3 * 3600) - (now % (3 * 3600))
    return {'emoji':emoji,'name':name,'description':description,'remaining':remaining}
