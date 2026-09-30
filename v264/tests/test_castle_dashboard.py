"""Tests sans réseau du tableau de bord personnel."""
import unittest
from types import SimpleNamespace
from castle_dashboard import dashboard_text


class FakeCastle:
    def __init__(self, available=True, claimed=False):
        self.available, self.claimed = available, claimed

    def profile(self, user_id):
        return {'xp': 0, 'wins': 2, 'losses': 1}

    def daily_available(self, user_id):
        return self.available

    def quests(self, user_id):
        return ([{'progress': 1, 'target': 1, 'claimed': self.claimed},
                 {'progress': 0, 'target': 1, 'claimed': self.claimed}], {})


class FakeEconomy:
    def get_balance(self, user_id):
        return SimpleNamespace(wallet=250, bank=400)


class FakeExpedition:
    def __init__(self, active):
        self.active = active

    def active_run(self, user_id):
        return object() if self.active else None


class DashboardTests(unittest.TestCase):
    def test_daily_available(self):
        result = dashboard_text(12, FakeCastle(), FakeEconomy())
        self.assertIn('Disponible', result)
        self.assertIn('1/2 terminées', result)
        self.assertIn('250', result)

    def test_daily_claimed_and_active_expedition(self):
        result = dashboard_text(12, FakeCastle(False, True), FakeEconomy(), FakeExpedition(True))
        self.assertIn('Déjà récupérée', result)
        self.assertIn('expédition est en cours', result)

    def test_quest_reward_ready(self):
        castle = FakeCastle()
        castle.quests = lambda uid: ([{'progress': 1, 'target': 1, 'claimed': False}], {})
        self.assertIn('Récompense des quêtes disponible', dashboard_text(12, castle, FakeEconomy()))


if __name__ == '__main__':
    unittest.main()
