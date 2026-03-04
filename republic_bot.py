import discord
from discord.ext import commands, tasks
import aiohttp
import ssl
import os
from datetime import datetime

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ALERT_CHANNEL_ID = 123456789
RPC_URL = "https://rpc.republicai.io"
REST_URL = "https://rest.republicai.io"

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

intents = discord.Intents.default()
intents.message_content = True

async def fetch(url):
    try:
        conn = aiohttp.TCPConnector(ssl=ssl_ctx)
        async with aiohttp.ClientSession(connector=conn) as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return await r.json()
    except:
        return None

def fmt(amount):
    try:
        return f"{int(amount)/1e18:,.2f} RAI"
    except:
        return str(amount)

class MyBot(commands.Bot):
    async def start(self, token, *, reconnect=True):
        self.http.connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        await super().start(token, reconnect=reconnect)

bot = MyBot(command_prefix="/", intents=intents)
validator_states = {}

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")
    jail_monitor.start()

@bot.command(name="validator", aliases=["val"])
async def val(ctx, *, query: str):
    await ctx.typing()
    data = await fetch(f"{REST_URL}/cosmos/staking/v1beta1/validators?pagination.limit=500")
    if not data:
        await ctx.send("Error fetching data.")
        return
    found = next((v for v in data.get("validators",[]) if query.lower() in v.get("description",{}).get("moniker","").lower() or query.lower() in v.get("operator_address","").lower()), None)
    if not found:
        await ctx.send(f"Validator not found: {query}")
        return
    desc = found.get("description",{})
    e = discord.Embed(title=f"Validator: {desc.get('moniker','?')}", color=0x6366f1)
    e.add_field(name="Status", value=found.get("status","?"), inline=True)
    e.add_field(name="Jailed", value="Yes" if found.get("jailed") else "No", inline=True)
    e.add_field(name="Tokens", value=fmt(found.get("tokens",0)), inline=True)
    e.add_field(name="Address", value=f"`{found.get('operator_address','')}`", inline=False)
    await ctx.send(embed=e)

@bot.command(name="rank", aliases=["top"])
async def rank(ctx, count: int = 10):
    await ctx.typing()
    data = await fetch(f"{REST_URL}/cosmos/staking/v1beta1/validators?status=BOND_STATUS_BONDED&pagination.limit=100")
    if not data:
        await ctx.send("Error fetching data.")
        return
    vals = sorted(data.get("validators",[]), key=lambda x: int(x.get("tokens",0)), reverse=True)
    e = discord.Embed(title=f"Top {min(count,25)} Validators", color=0x6366f1)
    lines = [f"#{i+1} **{v.get('description',{}).get('moniker','?')}** - {fmt(v.get('tokens',0))}" for i,v in enumerate(vals[:min(count,25)])]
    e.description = "\n".join(lines)
    await ctx.send(embed=e)

@bot.command(name="status")
async def status(ctx):
    await ctx.typing()
    block = await fetch(f"{RPC_URL}/status")
    pool = await fetch(f"{REST_URL}/cosmos/staking/v1beta1/pool")
    e = discord.Embed(title="Republic AI Network", color=0x00ff88)
    if block:
        e.add_field(name="Block", value=block.get("result",{}).get("sync_info",{}).get("latest_block_height","?"), inline=True)
    if pool:
        e.add_field(name="Bonded", value=fmt(pool.get("pool",{}).get("bonded_tokens",0)), inline=True)
    await ctx.send(embed=e)

@bot.command(name="jobs")
async def jobs(ctx, count: int = 10):
    await ctx.typing()
    data = await fetch(f"{REST_URL}/republic/computevalidation/job")
    if not data:
        await ctx.send("Error fetching data.")
        return
    js = sorted(data.get("jobs",[]), key=lambda x: int(x.get("id",0)), reverse=True)
    e = discord.Embed(title="Recent Compute Jobs", color=0x6366f1)
    lines = [f"Job #{j.get('id','?')} - {j.get('status','?')}" for j in js[:min(count,15)]]
    e.description = "\n".join(lines) if lines else "No jobs"
    await ctx.send(embed=e)

@tasks.loop(minutes=5)
async def jail_monitor():
    try:
        data = await fetch(f"{REST_URL}/cosmos/staking/v1beta1/validators?pagination.limit=200")
        if not data:
            return
        ch = bot.get_channel(ALERT_CHANNEL_ID)
        for v in data.get("validators",[]):
            addr = v.get("operator_address")
            moniker = v.get("description",{}).get("moniker","?")
            jailed = v.get("jailed", False)
            prev = validator_states.get(addr,{}).get("jailed", False)
            if jailed and not prev and ch:
                await ch.send(f"JAILED: {moniker} ({addr})")
            elif not jailed and prev and ch:
                await ch.send(f"UNJAILED: {moniker} ({addr})")
            validator_states[addr] = {"jailed": jailed}
    except Exception as ex:
        print(f"Monitor error: {ex}")

@jail_monitor.before_loop
async def before():
    await bot.wait_until_ready()

bot.run(BOT_TOKEN)
