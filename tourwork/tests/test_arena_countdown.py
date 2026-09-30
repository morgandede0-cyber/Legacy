import ast
import pathlib
import unittest

class ArenaCountdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(pathlib.Path(__file__).resolve().parents[1].joinpath('main.py').read_text(encoding='utf-8'))
        cls.functions = {n.name: n for n in cls.tree.body if isinstance(n, ast.AsyncFunctionDef)}

    def test_countdown_three_two_one(self):
        fn=self.functions['_arena_victory_countdown']
        loops=[n for n in ast.walk(fn) if isinstance(n, ast.For)]
        self.assertTrue(any(isinstance(n.iter,ast.Tuple) and [v.value for v in n.iter.elts]==[3,2,1] for n in loops))

    def test_both_arena_endings_schedule_countdown(self):
        for name in ('finish_battle_interaction','finish_battle_surface'):
            calls=[n for n in ast.walk(self.functions[name]) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='_arena_victory_countdown']
            self.assertEqual(len(calls),1,name)

    def test_closes_original_response(self):
        fn=self.functions['_arena_victory_countdown']
        self.assertTrue(any(isinstance(n,ast.Attribute) and n.attr=='delete_original_response' for n in ast.walk(fn)))

if __name__=='__main__': unittest.main()
