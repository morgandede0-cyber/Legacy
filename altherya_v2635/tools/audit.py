"""Audit statique sans dépendances externes : python tools/audit.py."""
from __future__ import annotations
import ast
from collections import defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
# Extensions V2 volontairement redéfinies en fin de main.py, après sauvegarde
# de leur classe de base sous _<Nom>Base : ne pas supprimer sans refonte.
EXPECTED_EXTENSIONS = {
    'TavernDrinksView', 'TavernFriendSelectView', 'MarketSellView',
    'ArenaFriendSelectView', 'ChampionClassView', 'FriendLobbyView',
    'ThiefTargetView', 'NPCTargetView', 'AdminAchievementView',
    'AdminTargetView', 'AdminAccessPickView',
}
errors = []
for file in sorted(ROOT.glob('*.py')):
    try:
        src = file.read_text(encoding='utf-8-sig')
        compile(src, str(file), 'exec')
        tree = ast.parse(src, filename=str(file))
    except (SyntaxError, UnicodeError) as exc:
        errors.append(f'{file.name}: {exc}')
        continue
    definitions = defaultdict(list)
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            definitions[node.name].append(node.lineno)
    for name, lines in definitions.items():
        if len(lines) > 1 and not (file.name == 'main.py' and name in EXPECTED_EXTENSIONS):
            errors.append(f'{file.name}: définition multiple de {name} : {lines}')
    print(f'OK {file.name} ({len(src.splitlines())} lignes)')
print(f'\nAudit: {len(list(ROOT.glob("*.py")))} modules vérifiés; {len(errors)} anomalie(s).')
for error in errors:
    print('ERREUR:', error)
sys.exit(bool(errors))
