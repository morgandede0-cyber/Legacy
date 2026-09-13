from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path
from progression import level_from_xp, XP_REWARDS
from admin_engine import event_multiplier

DAILY_REWARD = 200
DAILY_XP = 10

# Les 6 quêtes doivent TOUTES être terminées pour débloquer la récompense globale.
# V1.63 : les objectifs relient directement les grands systèmes de Altherya.
QUEST_GLOBAL_GOLD = 400
QUEST_GLOBAL_XP = 75
QUESTS = {
    'tower_clear': ('🗼 Valider des étages d’Ashkar', 2, 'tower_clear'),
    'forge_upgrade': ('⚒️ Améliorer un équipement', 1, 'forge_upgrade'),
    'arena_win': ('🏆 Gagner un combat d’arène', 1, 'arena_win'),
    'tavern_game': ('🍺 Participer à un jeu de Taverne', 1, 'tavern_game'),
    'expedition': ('🧭 Terminer une expédition', 1, 'expedition'),
    'gold_earned': ('💰 Gagner du Gold', 400, 'gold_earned'),
}

# La réputation criminelle continue d'augmenter légèrement la difficulté, sans jamais
# rendre Ashkar impossible : la Tour reste limitée à 3 nouvelles validations / jour.
QUEST_TIER_TARGETS = {
    0: {'tower_clear':2,'forge_upgrade':1,'arena_win':1,'tavern_game':1,'expedition':1,'gold_earned':400},
    1: {'tower_clear':2,'forge_upgrade':1,'arena_win':1,'tavern_game':1,'expedition':1,'gold_earned':500},
    2: {'tower_clear':2,'forge_upgrade':1,'arena_win':2,'tavern_game':1,'expedition':1,'gold_earned':650},
    3: {'tower_clear':3,'forge_upgrade':1,'arena_win':2,'tavern_game':2,'expedition':2,'gold_earned':850},
    4: {'tower_clear':3,'forge_upgrade':2,'arena_win':2,'tavern_game':2,'expedition':2,'gold_earned':1100},
    5: {'tower_clear':3,'forge_upgrade':2,'arena_win':2,'tavern_game':2,'expedition':2,'gold_earned':1100},
}
QUEST_TIER_REWARDS = {0:(400,75),1:(450,80),2:(525,90),3:(600,105),4:(700,125),5:(700,125)}



class CastleStore:
    def __init__(self, db_path: str|Path):
        self.db_path=Path(db_path); self.db_path.parent.mkdir(parents=True,exist_ok=True); self._init()
    def _c(self):
        c=sqlite3.connect(self.db_path,timeout=10); c.row_factory=sqlite3.Row; return c
    def _today(self): return datetime.now().date().isoformat()
    def _init(self):
        with self._c() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS castle_profiles(user_id INTEGER PRIMARY KEY, xp INTEGER NOT NULL DEFAULT 0, combats INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0, expeditions INTEGER NOT NULL DEFAULT 0, casino_games INTEGER NOT NULL DEFAULT 0, quests_completed INTEGER NOT NULL DEFAULT 0, member_since TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_daily TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS castle_daily_progress(user_id INTEGER NOT NULL, day TEXT NOT NULL, quest_key TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0, claimed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,day,quest_key))''')
            c.execute('''CREATE TABLE IF NOT EXISTS castle_levelups(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                old_level INTEGER NOT NULL,
                new_level INTEGER NOT NULL,
                old_hp INTEGER NOT NULL,
                new_hp INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                consumed INTEGER NOT NULL DEFAULT 0
            )''')
            c.commit()
    def ensure(self,user_id):
        with self._c() as c: c.execute('INSERT OR IGNORE INTO castle_profiles(user_id) VALUES(?)',(int(user_id),)); c.commit()
    def _sync_level(self,c,uid):
        row=c.execute('SELECT xp FROM castle_profiles WHERE user_id=?',(int(uid),)).fetchone()
        if not row: return
        level=level_from_xp(int(row['xp']))[0]
        c.execute('INSERT OR IGNORE INTO expedition_profiles(user_id) VALUES(?)',(int(uid),))
        c.execute('UPDATE expedition_profiles SET player_level=? WHERE user_id=?',(level,int(uid)))
    def current_level(self,user_id):
        p=self.profile(user_id)
        return level_from_xp(int(p['xp']))[0]
    def profile(self,user_id):
        self.ensure(user_id)
        with self._c() as c: return dict(c.execute('SELECT * FROM castle_profiles WHERE user_id=?',(int(user_id),)).fetchone())
    @staticmethod
    def _base_hp_for_level(level):
        return 1000 + 35 * (max(1, int(level)) - 1)

    def _queue_levelups(self,c,uid,before_xp,after_xp):
        old_level=level_from_xp(int(before_xp))[0]
        new_level=level_from_xp(int(after_xp))[0]
        if new_level <= old_level:
            return
        for lvl in range(old_level + 1, new_level + 1):
            prev=lvl-1
            c.execute('''INSERT INTO castle_levelups(user_id,old_level,new_level,old_hp,new_hp) VALUES(?,?,?,?,?)''',
                      (int(uid),prev,lvl,self._base_hp_for_level(prev),self._base_hp_for_level(lvl)))

    def pending_levelups(self,user_id,consume=True):
        uid=int(user_id)
        with self._c() as c:
            rows=c.execute('SELECT * FROM castle_levelups WHERE user_id=? AND consumed=0 ORDER BY id',(uid,)).fetchall()
            out=[dict(r) for r in rows]
            if consume and rows:
                c.execute('UPDATE castle_levelups SET consumed=1 WHERE user_id=? AND consumed=0',(uid,)); c.commit()
        return out

    def add_xp(self,user_id,amount):
        self.ensure(user_id); uid=int(user_id)
        with self._c() as c:
            before=int(c.execute('SELECT xp FROM castle_profiles WHERE user_id=?',(uid,)).fetchone()['xp'])
            amount=max(0,int(amount))*event_multiplier(self.db_path,'xp_x2')
            c.execute('UPDATE castle_profiles SET xp=xp+? WHERE user_id=?',(amount,uid))
            after=before+amount
            self._queue_levelups(c,uid,before,after)
            self._sync_level(c,uid); c.commit()
        return amount
    def _criminal_reputation(self,user_id):
        with self._c() as c:
            row=c.execute('SELECT successes FROM criminal_reputation WHERE user_id=?',(int(user_id),)).fetchone()
        successes=int(row['successes']) if row else 0
        tiers=[(5,'Inconnu'),(20,'Petite frappe'),(60,'Bandit'),(150,'Criminel'),(300,'Seigneur de la Ruelle')]
        tier=0; label='Inconnu'
        for i,(needed,name) in enumerate(tiers,1):
            if successes>=needed: tier,label=i,name
        difficulty={'Inconnu':0,'Petite frappe':1,'Bandit':2,'Criminel':3,'Seigneur de la Ruelle':4}.get(label,0)
        return difficulty,label,successes
    def quest_config(self,user_id):
        tier,label,successes=self._criminal_reputation(user_id)
        targets=QUEST_TIER_TARGETS[min(tier,5)]
        gold,xp=QUEST_TIER_REWARDS[min(tier,5)]
        out={}
        for key,(base_label,_,event) in QUESTS.items():
            target=targets[key]
            # labels précis avec quantité adaptée
            labels={
                'tower_clear':f'🗼 Valider {target} étage'+('s' if target>1 else '')+' d’Ashkar',
                'forge_upgrade':f'⚒️ Améliorer {target} équipement'+('s' if target>1 else ''),
                'arena_win':f'🏆 Gagner {target} combat'+('s' if target>1 else '')+' d’arène',
                'tavern_game':f'🍺 Participer à {target} jeu'+('x' if target>1 else '')+' de Taverne',
                'expedition':f'🧭 Terminer {target} expédition'+('s' if target>1 else ''),
                'gold_earned':f'💰 Gagner {target} Gold',
            }
            out[key]=(labels[key],target,event)
        return out, {'tier':tier,'label':label,'successes':successes,'gold':gold,'xp':xp}

    def record(self,user_id,event,amount=1):
        self.ensure(user_id); uid=int(user_id); amount=max(0,int(amount)); day=self._today(); quest_cfg,_=self.quest_config(uid)
        col={'combat':'combats','arena_win':'wins','arena_loss':'losses','expedition':'expeditions','casino':'casino_games'}.get(event)
        xp={'arena_win':XP_REWARDS['arena_win'],'arena_loss':XP_REWARDS['arena_loss'],'casino':XP_REWARDS['casino']}.get(event,0) * event_multiplier(self.db_path,'xp_x2')
        with self._c() as c:
            c.execute('BEGIN IMMEDIATE')
            before_xp=int(c.execute('SELECT xp FROM castle_profiles WHERE user_id=?',(uid,)).fetchone()['xp'])
            if col: c.execute(f'UPDATE castle_profiles SET {col}={col}+?, xp=xp+? WHERE user_id=?',(amount,xp*amount,uid))
            elif xp: c.execute('UPDATE castle_profiles SET xp=xp+? WHERE user_id=?',(xp*amount,uid))
            after_xp=before_xp + xp*amount
            self._queue_levelups(c,uid,before_xp,after_xp)

            # Progression des quêtes basée sur l'événement réel.
            for key,(label,target,quest_event) in quest_cfg.items():
                inc = amount if quest_event == event else 0
                if inc:
                    c.execute('INSERT OR IGNORE INTO castle_daily_progress(user_id,day,quest_key) VALUES(?,?,?)',(uid,day,key))
                    c.execute('UPDATE castle_daily_progress SET progress=progress+? WHERE user_id=? AND day=? AND quest_key=?',(inc,uid,day,key))

            self._sync_level(c,uid)
            c.commit()
    def quests(self,user_id):
        self.ensure(user_id); uid=int(user_id); day=self._today(); out=[]; quest_cfg,meta=self.quest_config(uid)
        with self._c() as c:
            for key,(label,target,event) in quest_cfg.items():
                c.execute('INSERT OR IGNORE INTO castle_daily_progress(user_id,day,quest_key) VALUES(?,?,?)',(uid,day,key))
            c.commit()
            rows={r['quest_key']:r for r in c.execute('SELECT * FROM castle_daily_progress WHERE user_id=? AND day=?',(uid,day))}
        for key,(label,target,event) in quest_cfg.items():
            r=rows[key]
            out.append({'key':key,'label':label,'target':target,'progress':min(int(r['progress']),target),'claimed':bool(r['claimed'])})
        return out,meta

    def claim_quests(self,user_id):
        """Récompense tout-ou-rien : les 6 quêtes doivent être terminées."""
        uid=int(user_id); day=self._today(); quest_cfg,meta=self.quest_config(uid)
        with self._c() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT OR IGNORE INTO castle_profiles(user_id) VALUES(?)',(uid,))
            rows=[]
            for key,(label,target,event) in quest_cfg.items():
                c.execute('INSERT OR IGNORE INTO castle_daily_progress(user_id,day,quest_key) VALUES(?,?,?)',(uid,day,key))
                r=c.execute('SELECT progress,claimed FROM castle_daily_progress WHERE user_id=? AND day=? AND quest_key=?',(uid,day,key)).fetchone()
                rows.append((key,target,int(r['progress']),bool(r['claimed'])))

            if all(claimed for _,_,_,claimed in rows):
                c.rollback(); return False,0,0,'claimed'
            if not all(progress >= target for _,target,progress,_ in rows):
                c.rollback(); return False,0,0,'incomplete'

            c.execute('UPDATE castle_daily_progress SET claimed=1 WHERE user_id=? AND day=?',(uid,day))
            c.execute('INSERT OR IGNORE INTO players(user_id) VALUES(?)',(uid,))
            gold_reward=int(meta['gold'])*event_multiplier(self.db_path,'gold_x2')
            xp_reward=int(meta['xp'])*event_multiplier(self.db_path,'xp_x2')
            c.execute('UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?',(gold_reward,uid))
            before_xp=int(c.execute('SELECT xp FROM castle_profiles WHERE user_id=?',(uid,)).fetchone()['xp'])
            c.execute('UPDATE castle_profiles SET xp=xp+?, quests_completed=quests_completed+? WHERE user_id=?',(xp_reward,len(quest_cfg),uid))
            self._queue_levelups(c,uid,before_xp,before_xp+xp_reward)
            self._sync_level(c,uid)
            c.commit()
        return True,gold_reward,xp_reward,'ok'

    def claim_daily(self,user_id):
        uid=int(user_id); day=self._today(); self.ensure(uid)
        with self._c() as c:
            c.execute('BEGIN IMMEDIATE'); r=c.execute('SELECT last_daily FROM castle_profiles WHERE user_id=?',(uid,)).fetchone()
            if r and r['last_daily']==day: c.rollback(); return False,0
            c.execute('INSERT OR IGNORE INTO players(user_id) VALUES(?)',(uid,))
            gold_reward=DAILY_REWARD*event_multiplier(self.db_path,'gold_x2')
            xp_reward=DAILY_XP*event_multiplier(self.db_path,'xp_x2')
            c.execute('UPDATE players SET wallet_gold=wallet_gold+? WHERE user_id=?',(gold_reward,uid))
            before_xp=int(c.execute('SELECT xp FROM castle_profiles WHERE user_id=?',(uid,)).fetchone()['xp'])
            c.execute('UPDATE castle_profiles SET last_daily=?, xp=xp+? WHERE user_id=?',(day,xp_reward,uid))
            self._queue_levelups(c,uid,before_xp,before_xp+xp_reward)
            self._sync_level(c,uid); c.commit()
        return True,gold_reward
    def daily_available(self,user_id): return self.profile(user_id)['last_daily'] != self._today()
    def leaderboard(self,limit=10):
        with self._c() as c:
            return [dict(r) for r in c.execute('SELECT user_id,wallet_gold,bank_gold,(wallet_gold+bank_gold) total FROM players ORDER BY total DESC,user_id ASC LIMIT ?',(int(limit),))]
