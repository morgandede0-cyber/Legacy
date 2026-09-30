import unittest
from types import SimpleNamespace
from castle_dashboard import dashboard_text

class Store:
    def profile(self, uid): return {'xp': 0, 'wins': 2, 'losses': 1}
    def quests(self, uid): return ([{'progress': 1, 'target': 1, 'claimed': self.claimed}] * 6, {})

class Economy:
    def get_balance(self, uid): return SimpleNamespace(wallet=100, bank=200)

class Expeditions:
    def active_run(self, uid): return None

class DashboardTests(unittest.TestCase):
    def test_quest_claimed(self):
        store=Store(); store.claimed=True
        text=dashboard_text(1,store,Economy(),Expeditions())
        self.assertIn('Déjà récupéré',text)
        self.assertIn('6/6',text)
    def test_quest_available(self):
        store=Store(); store.claimed=False
        self.assertIn('Disponible',dashboard_text(1,store,Economy(),Expeditions()))
    def test_dashboard_gold(self):
        store=Store(); store.claimed=False
        text=dashboard_text(1,store,Economy(),Expeditions())
        self.assertIn('100 Gold',text)
        self.assertIn('200 Gold',text)
    def test_ui_contract(self):
        source=open('main.py',encoding='utf8').read()
        self.assertIn("('Mon tableau de bord','📊','dashboard')",source)
        self.assertIn("label='Déjà récupéré' if claimed",source)
        self.assertIn('await show_castle_quests(i,msg)',source)
if __name__ == '__main__': unittest.main()
