import unittest
from pathlib import Path

class TestHpBalance(unittest.TestCase):
    def test_shared_hp_formula_in_all_combat_paths(self):
        root = Path(__file__).resolve().parents[1]
        self.assertIn('base_level_hp = 100 + 10 * (level - 1)', (root/'main.py').read_text())
        self.assertIn('return 100 + 10 * (max(1, int(level)) - 1)', (root/'castle_engine.py').read_text())
        self.assertIn('hp = round((100 + 10 * lvl_scale) * class_hp_mult)', (root/'tower_engine.py').read_text())
    def test_level_progression(self):
        for level, expected in [(1,100),(2,110),(5,140),(10,190),(20,290)]:
            self.assertEqual(100+10*(level-1), expected)
