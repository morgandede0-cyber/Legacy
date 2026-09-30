import ast
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class TowerAccessV2Tests(unittest.TestCase):
    def test_lobby_uses_v2_only(self):
        tree=ast.parse((ROOT/'tower_engine.py').read_text(encoding='utf8'))
        fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='show_lobby')
        src=ast.unparse(fn)
        self.assertIn('_edit_v2',src)
        self.assertIn('_send_v2',src)
        self.assertNotIn('discord.Embed',src)
        self.assertIn('lvl < 5',src)
    def test_v2_edit_omits_content(self):
        tree=ast.parse((ROOT/'tower_engine.py').read_text(encoding='utf8'))
        fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='_edit_v2')
        self.assertNotIn('content=',ast.unparse(fn))
if __name__=='__main__': unittest.main()
