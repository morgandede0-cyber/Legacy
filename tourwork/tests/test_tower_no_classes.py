import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TowerNoClassesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'tower_engine.py').read_text(encoding='utf-8')
        cls.tree = ast.parse(cls.source)

    def test_lobby_has_no_class_selection(self):
        view = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == 'TowerClassView')
        constructor = next(n for n in view.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'ready_cb')
        self.assertIn('arena_fighter', ast.unparse(constructor))
        self.assertNotIn('Choisis d’abord une classe', ast.unparse(view))

    def test_skills_use_player_level(self):
        state = next(n for n in self.tree.body if isinstance(n, ast.ClassDef) and n.name == 'BattleState')
        prop = next(n for n in state.body if isinstance(n, ast.FunctionDef) and n.name == 'class_cfg')
        self.assertIn('arena_player_skills(self.player_level)', ast.unparse(prop))

    def test_no_class_change_button(self):
        self.assertNotIn('label="Changer de classe"', self.source)
        self.assertNotIn('choisis ta classe', self.source.lower())

    def test_progression_shared_with_arena(self):
        tree = ast.parse((ROOT / 'arena_engine.py').read_text(encoding='utf-8'))
        data = next(n.value for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t,ast.Name) and t.id=='ARENA_PLAYER_SKILLS' for t in n.targets))
        levels = [k.value for k in data.keys]
        self.assertEqual(levels, [1,3,6,9,12,15,18])

if __name__ == '__main__': unittest.main()
