"""Descriptions humoristiques du petit larcin, sans effet sur les gains."""
import random

LARCENY_SCENES = (
    "a volé la tétine d'un nouveau-né pour négocier une rançon de bonbons",
    "a poussé la charrette d'une mamie dans le canal (mamie saine et sauve, légumes perdus)",
    "a dérobé le dentier d'un ogre pendant sa sieste",
    "a remplacé la bière du tavernier par du jus de navet",
    "a subtilisé la couronne du roi… en carton",
    "a volé une chaussette à un chevalier et laissé l'autre par pitié",
    "a kidnappé le canard du garde pour en faire son conseiller",
    "a piqué les lacets du bourreau avant son service",
    "a revendu au marché une pierre en prétendant qu'il s'agissait d'un œuf de dragon",
    "a chapardé la dernière part de tarte du boulanger",
    "a échangé l'épée d'un garde contre une baguette de pain",
    "a dérobé le panneau « Ne pas voler » de la place du marché",
)


def random_larceny_scene(rng=None):
    """Retourne une anecdote; injectable pour les tests."""
    return (rng or random).choice(LARCENY_SCENES)
