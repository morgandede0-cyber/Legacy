"""Altherya Sentinel V1 — deterministic real-time error detection and Discord DM alerts."""
from __future__ import annotations
import asyncio, hashlib, json, os, sqlite3, sys, time, traceback
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass
class ErrorBucket:
    first: float
    last: float
    count: int = 0
    last_dm: float = 0.0

class AltheryaSentinel:
    def __init__(self, bot, base: Path, *, admin_id: int | None = None):
        self.bot=bot; self.base=Path(base); self.data=self.base/'data'; self.data.mkdir(exist_ok=True)
        raw=str(admin_id or os.getenv('SENTINEL_ADMIN_ID','')).strip()
        self.admin_id=int(raw) if raw.isdigit() else None
        self.enabled=os.getenv('SENTINEL_ENABLED','1').lower() not in {'0','false','no','off'}
        self.dm_cooldown=max(60,int(os.getenv('SENTINEL_DM_COOLDOWN','300')))
        self.health_interval=max(30,int(os.getenv('SENTINEL_HEALTH_INTERVAL','60')))
        self.heartbeat=self.data/'sentinel_heartbeat.json'
        self.logfile=self.data/'sentinel_errors.jsonl'
        self.buckets: dict[str,ErrorBucket]={}
        self.recent=deque(maxlen=100)
        self._health_task=None; self._old_loop_handler=None
        self._high_latency_streak=0
        self._reporting=False

    @staticmethod
    def fingerprint(exc: BaseException, context='') -> str:
        tb=traceback.extract_tb(exc.__traceback__)
        last=tb[-1] if tb else None
        seed=f'{type(exc).__name__}|{last.filename if last else ""}|{last.lineno if last else 0}|{context}'
        return 'ALT-'+hashlib.sha1(seed.encode()).hexdigest()[:8].upper()

    @staticmethod
    def severity(exc: BaseException) -> tuple[str,str]:
        name=type(exc).__name__.lower()
        if any(x in name for x in ('database','operational','interface','connection','runtime')): return '🔴','CRITIQUE'
        if any(x in name for x in ('timeout','http','forbidden','notfound')): return '🟠','IMPORTANTE'
        return '🟡','ERREUR'

    def _write(self, payload: dict):
        try:
            with self.logfile.open('a',encoding='utf-8') as f: f.write(json.dumps(payload,ensure_ascii=False,default=str)+'\n')
        except Exception: pass

    async def _admin(self):
        if not self.admin_id: return None
        u=self.bot.get_user(self.admin_id)
        if u: return u
        try: return await self.bot.fetch_user(self.admin_id)
        except Exception: return None

    async def report(self, exc: BaseException, *, source='Python', context='', user_id=None, extra=''):
        if not self.enabled or self._reporting: return
        now=time.time(); fid=self.fingerprint(exc,context); b=self.buckets.get(fid)
        if b is None: b=self.buckets[fid]=ErrorBucket(now,now)
        b.count+=1; b.last=now
        tb=''.join(traceback.format_exception(type(exc),exc,exc.__traceback__))
        frames=traceback.extract_tb(exc.__traceback__); last=frames[-1] if frames else None
        payload={'ts':datetime.now(timezone.utc).isoformat(),'id':fid,'source':source,'context':context,'type':type(exc).__name__,'message':str(exc),'file':Path(last.filename).name if last else None,'line':last.lineno if last else None,'count':b.count,'user_id':user_id,'traceback':tb}
        self._write(payload); self.recent.append(payload)
        # First occurrence immediately, then at most one reminder per cooldown.
        if b.count>1 and now-b.last_dm<self.dm_cooldown: return
        self._reporting=True
        try:
            admin=await self._admin()
            if not admin: return
            icon,level=self.severity(exc)
            where=f"`{Path(last.filename).name}:{last.lineno}`" if last else '`inconnu`'
            who=f"\n👤 Joueur : <@{int(user_id)}>" if user_id else ''
            repeat=f"\n🔁 Occurrences : **{b.count}**" if b.count>1 else ''
            msg=(f"🚨 **SENTINELLE ALTHÉRYA**\n{icon} **{level}** • `{fid}`\n\n"
                 f"📍 Système : **{source}**\n🧩 Contexte : {context or '—'}\n🐍 `{type(exc).__name__}: {str(exc)[:500]}`\n"
                 f"📄 {where}{who}{repeat}\n\n```py\n{tb[-1200:]}\n```")
            if extra: msg += f"\nℹ️ {extra[:500]}"
            await admin.send(msg[:1990]); b.last_dm=now
        except Exception as dm_exc:
            self._write({'ts':datetime.now(timezone.utc).isoformat(),'source':'Sentinel','type':'DMFailure','message':repr(dm_exc)})
        finally: self._reporting=False

    async def anomaly(self, title: str, detail: str, *, critical=False):
        exc=RuntimeError(f'{title}: {detail}')
        await self.report(exc,source='Health-check',context=title,extra=detail)

    def install_loop_handler(self):
        loop=asyncio.get_running_loop(); self._old_loop_handler=loop.get_exception_handler()
        def handler(lp, ctx):
            exc=ctx.get('exception') or RuntimeError(ctx.get('message','Erreur asyncio sans exception'))
            try: lp.create_task(self.report(exc,source='asyncio',context=ctx.get('message','tâche asynchrone')))
            except Exception: pass
            if self._old_loop_handler: self._old_loop_handler(lp,ctx)
            else: lp.default_exception_handler(ctx)
        loop.set_exception_handler(handler)

    async def health_once(self):
        # Heartbeat is consumed by the independent watchdog.
        try:
            self.heartbeat.write_text(json.dumps({'ts':time.time(),'ready':self.bot.is_ready(),'latency':getattr(self.bot,'latency',None)}),encoding='utf-8')
        except Exception as e: await self.report(e,source='Sentinel',context='écriture heartbeat')
        if not self.bot.is_ready(): return
        latency=float(getattr(self.bot,'latency',0) or 0)
        # Un heartbeat isolé >5 s peut venir de Discord/réseau et ne justifie pas une
        # alerte critique. On alerte uniquement si la dégradation persiste.
        if latency > 5:
            self._high_latency_streak += 1
        else:
            self._high_latency_streak = 0
        if self._high_latency_streak == 3:
            await self.anomaly('Discord durablement lent', f'Latence Gateway {latency:.2f}s sur 3 contrôles consécutifs')
        db=self.data/'legacy.sqlite3'
        try:
            con=sqlite3.connect(db,timeout=3); con.execute('SELECT 1').fetchone(); con.close()
        except Exception as e: await self.report(e,source='Base de données',context='health-check SQLite')

    async def _health_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try: await self.health_once()
            except asyncio.CancelledError: raise
            except Exception as e: await self.report(e,source='Sentinel',context='boucle health-check')
            await asyncio.sleep(self.health_interval)

    def start(self):
        if not self.enabled or self._health_task: return
        self.install_loop_handler(); self._health_task=asyncio.create_task(self._health_loop(),name='altherya-sentinel-health')
        print(f"🛡️ Sentinelle active • admin={'configuré' if self.admin_id else 'NON CONFIGURÉ'} • health={self.health_interval}s")
