"""Independent Altherya watchdog. Run as a SECOND service/container."""
import asyncio, json, os, time
from pathlib import Path
import discord
from dotenv import load_dotenv
load_dotenv()
TOKEN=os.getenv('WATCHDOG_DISCORD_TOKEN','').strip()
ADMIN=os.getenv('SENTINEL_ADMIN_ID','').strip()
HEARTBEAT=Path(os.getenv('ALTHERYA_HEARTBEAT_PATH','data/sentinel_heartbeat.json'))
MAX_AGE=max(90,int(os.getenv('WATCHDOG_MAX_HEARTBEAT_AGE','180')))
CHECK=max(30,int(os.getenv('WATCHDOG_CHECK_INTERVAL','60')))
client=discord.Client(intents=discord.Intents.none())
last_state=None
async def monitor():
    global last_state
    await client.wait_until_ready(); admin=await client.fetch_user(int(ADMIN))
    while not client.is_closed():
        reason=None
        try:
            p=json.loads(HEARTBEAT.read_text(encoding='utf-8')); age=time.time()-float(p['ts'])
            if age>MAX_AGE: reason=f"heartbeat absent depuis {int(age)} s"
            elif not p.get('ready',False): reason='processus vivant mais Discord non prêt'
        except Exception as e: reason=f"heartbeat illisible/absent ({type(e).__name__})"
        state='down' if reason else 'ok'
        if state!=last_state:
            if state=='down': await admin.send(f"🛰️ **WATCHDOG ALTHÉRYA**\n🔴 Bot potentiellement indisponible : **{reason}**")
            elif last_state=='down': await admin.send("🛰️ **WATCHDOG ALTHÉRYA**\n🟢 Heartbeat rétabli, Altherya répond de nouveau.")
            last_state=state
        await asyncio.sleep(CHECK)
@client.event
async def on_ready():
    print('🛰️ Watchdog connecté'); asyncio.create_task(monitor())
if __name__=='__main__':
    if not TOKEN or not ADMIN: raise SystemExit('WATCHDOG_DISCORD_TOKEN et SENTINEL_ADMIN_ID requis')
    client.run(TOKEN)
