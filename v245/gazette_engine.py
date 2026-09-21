from __future__ import annotations
import sqlite3, time
from datetime import datetime
from pathlib import Path

# La Gazette ne fabrique jamais d'événement : toutes ses lignes viennent de la BDD Altherya.
ALCOHOL_COPY = {
    'floor_bed': ('🍺', 'Sous la table', '{name} a été retrouvé complètement torché sous une table. Le mobilier de la Taverne se porte bien.'),
    'why_chicken': ('🐔', 'Gérard fait encore parler de lui', '{name} a terminé sa soirée avec une poule répondant au nom de Gérard. Nous préférons ne pas poser de questions.'),
    'wrong_shoe': ('👞', 'Problème de chaussures', '{name} a terminé sa soirée avec deux chaussures qui ne semblent pas appartenir à la même personne.'),
    'short_career': ('🎤', 'Carrière musicale éclair', '{name} a improvisé un concert à la Taverne. Sa carrière aura duré environ quarante secondes.'),
    'ring_what': ('💍', 'Une bague et beaucoup de questions', '{name} s’est réveillé avec une bague inconnue au doigt et aucun souvenir permettant de l’expliquer.'),
    'arm_wrestle': ('💪', 'Mauvaise idée au comptoir', '{name} a provoqué un habitué au bras de fer. Son bras regrette encore cette décision.'),
    'horse_judges': ('🐴', 'Réveil difficile', '{name} s’est réveillé saoul dans une écurie. Le cheval présent sur place semblait profondément déçu.'),
    'alley_wakeup': ('🌑', 'Mauvais chemin', '{name} a repris ses esprits à l’entrée de la Ruelle Sombre après une soirée particulièrement confuse.'),
    'your_majesty': ('👑', 'Incident diplomatique', '{name} a tenu une conversation très sérieuse avec une statue… avant de la laisser gagner le débat.'),
    'technically_alive': ('⚰️', 'Techniquement vivant', '{name} s’est réveillé dans un cercueil vide derrière une échoppe. Oui, cela s’est réellement produit.'),
    'someone_pouch': ('👝', 'Une bourse de trop', '{name} a retrouvé dans sa veste une bourse qui ne lui appartenait clairement pas.'),
    'wolf_mark': ('🐺', 'Étrange marque', '{name} a découvert une marque de loup sur son poignet après une nuit dont les souvenirs restent flous.'),
    'barrel_passenger': ('🛢️', 'Transport de luxe', '{name} s’est réveillé assis dans un tonneau à plusieurs dizaines de mètres de la Taverne.'),
    'unknown_tab': ('🧾', 'Une addition mémorable', '{name} a découvert une addition à son nom dont la moitié des commandes lui était totalement inconnue.'),
    'no_memory_key': ('🗝️', 'Objet mystérieux', '{name} a repris conscience avec une étrange clé noire et absolument aucun souvenir de son origine.'),
    'never_again': ('💀', '« Plus jamais »', '{name} a juré « plus jamais » après une nuit catastrophique… devant une nouvelle chope.'),
    'roof_wakeup': ('🏠', 'Mais comment ?', '{name} s’est réveillé sur un toit, enlacé à une girouette. La Gazette n’a pas réussi à obtenir davantage d’explications.'),
    'chair_duel': ('🪑', 'Duel perdu', '{name} a livré un duel contre une chaise. La chaise a gagné.'),
}

class GazetteStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._init_db()

    def _connect(self):
        c = sqlite3.connect(self.db_path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self):
        with self._connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS gazette_config(
                guild_id INTEGER PRIMARY KEY, channel_id INTEGER NOT NULL,
                last_published_day TEXT, last_published_at INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1)''')
            c.execute('''CREATE TABLE IF NOT EXISTS gazette_events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                value INTEGER NOT NULL DEFAULT 0,
                detail TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            )''')
            c.commit()

    def configure(self, guild_id: int, channel_id: int):
        now = int(time.time())
        with self._connect() as c:
            # Au premier réglage, on démarre le relevé maintenant : aucun vieux fait divers n'est recyclé.
            row = c.execute('SELECT guild_id FROM gazette_config WHERE guild_id=?', (int(guild_id),)).fetchone()
            if row:
                c.execute('UPDATE gazette_config SET channel_id=?, enabled=1 WHERE guild_id=?', (int(channel_id), int(guild_id)))
            else:
                c.execute('INSERT INTO gazette_config(guild_id,channel_id,last_published_at,enabled) VALUES(?,?,?,1)', (int(guild_id), int(channel_id), now))
            c.commit()

    def configs(self):
        with self._connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM gazette_config WHERE enabled=1').fetchall()]

    def mark_published(self, guild_id: int, day: str, published_at: int):
        with self._connect() as c:
            c.execute('UPDATE gazette_config SET last_published_day=?,last_published_at=? WHERE guild_id=?', (str(day), int(published_at), int(guild_id)))
            c.commit()

    def casino_net(self, since_ts: int, until_ts: int):
        with self._connect() as c:
            rows = c.execute('''SELECT user_id, COUNT(*) games, SUM(payout-wager) net,
                               SUM(wager) wagered, SUM(payout) paid
                               FROM casino_sessions
                               WHERE status='finished' AND finished_at>? AND finished_at<=?
                               GROUP BY user_id''', (int(since_ts), int(until_ts))).fetchall()
        return [dict(r) for r in rows]

    def alcohol_events(self, since_ts: int, until_ts: int):
        with self._connect() as c:
            rows = c.execute('''SELECT user_id,event_id,drink_key,drunkenness,created_at
                                FROM tavern_drunk_events
                                WHERE created_at>? AND created_at<=?
                                ORDER BY created_at DESC''', (int(since_ts), int(until_ts))).fetchall()
        return [dict(r) for r in rows]

    def record_event(self, event_type: str, user_id: int, value: int = 0, detail: str = ''):
        with self._connect() as c:
            c.execute('INSERT INTO gazette_events(event_type,user_id,value,detail,created_at) VALUES(?,?,?,?,?)',
                      (str(event_type),int(user_id),int(value),str(detail),int(time.time())))
            c.commit()

    def world_events(self, since_ts: int, until_ts: int):
        with self._connect() as c:
            rows=c.execute('''SELECT event_type,user_id,value,detail,created_at FROM gazette_events
                              WHERE created_at>? AND created_at<=? ORDER BY created_at DESC''',
                           (int(since_ts),int(until_ts))).fetchall()
        return [dict(r) for r in rows]

    def build_items(self, since_ts: int, until_ts: int, name_for, max_alcohol: int = 4):
        items = []
        # V1.63 : les exploits du monde alimentent désormais automatiquement la Gazette.
        for e in self.world_events(since_ts, until_ts):
            name = name_for(int(e['user_id']))
            kind = e['event_type']; value = int(e['value'] or 0); detail = e['detail'] or ''
            if kind == 'ashkar_boss':
                items.append(('🗼 EXPLOIT À LA TOUR D’ASHKAR', f'**{name}** terrasse **Varkhaz** et franchit le **10e étage** de la Tour d’Ashkar.'))
            elif kind == 'ashkar_record':
                items.append(('📈 NOUVEAU RECORD D’ASHKAR', f'**{name}** porte le record de la Tour jusqu’à l’**étage {value}**.'))
            elif kind == 'legendary_forge':
                item = detail or 'une pièce d’équipement'
                items.append(('⚒️ CHEF-D’ŒUVRE DE KHAZ’GORAM', f'**{name}** vient de forger **{item}** de qualité **Légendaire** chez Thorgar.'))
            elif kind == 'champion_5':
                items.append(('🏟️ LE MUR DE L’ARÈNE EST TOMBÉ', f'**{name}** a vaincu le **Champion V** de Altherya.'))
            elif kind == 'champion_10':
                items.append(('👑 LE ROI DE L’ARÈNE EST VAINCU', f'**{name}** a terrassé le **Champion X** et termine le parcours des Champions.'))
            elif kind == 'level_milestone':
                items.append(('⭐ UNE LÉGENDE GRANDIT', f'**{name}** atteint le **niveau {value}**.'))

        # Evite qu'un même exploit soit répété plusieurs fois dans une édition.
        unique=[]; seen=set()
        for title,body in items:
            key=(title,body)
            if key not in seen:
                seen.add(key); unique.append((title,body))
        items=unique
        casino = self.casino_net(since_ts, until_ts)
        positives = [r for r in casino if int(r['net'] or 0) > 0]
        negatives = [r for r in casino if int(r['net'] or 0) < 0]
        if positives:
            r = max(positives, key=lambda x: int(x['net']))
            net = int(r['net']); name = name_for(int(r['user_id']))
            items.append(('🎰 ROI DU CASINO', f'Félicitations à **{name}**, meilleur bilan du Casino avec **+{net:,} Gold** nets sur la période.'.replace(',', ' ')))
        if negatives:
            r = min(negatives, key=lambda x: int(x['net']))
            net = abs(int(r['net'])); name = name_for(int(r['user_id']))
            items.append(('🤡 DONATEUR OFFICIEL DU CASINO', f'Une pensée pour **{name}**, qui a laissé **{net:,} Gold** nets au Casino. La maison le remercie chaleureusement.'.replace(',', ' ')))

        # Maximum une anecdote d'alcool par joueur pour éviter qu'une seule personne monopolise l'édition.
        used = set()
        chosen = []
        for e in self.alcohol_events(since_ts, until_ts):
            uid = int(e['user_id'])
            if uid in used or e['event_id'] not in ALCOHOL_COPY:
                continue
            used.add(uid); chosen.append(e)
            if len(chosen) >= max_alcohol:
                break
        for e in chosen:
            emoji, title, template = ALCOHOL_COPY[e['event_id']]
            items.append((f'{emoji} {title.upper()}', template.format(name=f"**{name_for(int(e['user_id']))}**")))
        return items
