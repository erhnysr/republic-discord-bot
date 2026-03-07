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
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
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
    print("Commands: /validator /rank /status /jobs /myjobs /leaderboard /stats /help")

# ── VALIDATOR ──────────────────────────────────────────────
@bot.command(name="validator", aliases=["val"])
async def val(ctx, *, query: str):
    await ctx.typing()
    data = await fetch(f"{REST_URL}/cosmos/staking/v1beta1/validators?pagination.limit=500")
    if not data:
        await ctx.send("❌ Error fetching data.")
        return
    found = next((v for v in data.get("validators",[]) if query.lower() in v.get("description",{}).get("moniker","").lower() or query.lower() in v.get("operator_address","").lower()), None)
    if not found:
        await ctx.send(f"❌ Validator not found: `{query}`")
        return
    desc = found.get("description",{})
    status = found.get("status","?")
    jailed = found.get("jailed", False)
    color = 0x00ff88 if not jailed else 0xff4444
    e = discord.Embed(title=f"🔍 {desc.get('moniker','?')}", color=color)
    e.add_field(name="Status", value="✅ Bonded" if "BONDED" in status else "⚠️ "+status, inline=True)
    e.add_field(name="Jailed", value="🔴 YES" if jailed else "🟢 NO", inline=True)
    e.add_field(name="Tokens", value=fmt(found.get("tokens",0)), inline=True)
    e.add_field(name="Commission", value=f"{float(found.get('commission',{}).get('commission_rates',{}).get('rate',0))*100:.1f}%", inline=True)
    e.add_field(name="Address", value=f"`{found.get('operator_address','')}`", inline=False)
    if desc.get("website"):
        e.add_field(name="Website", value=desc.get("website"), inline=True)
    await ctx.send(embed=e)

# ── RANK ───────────────────────────────────────────────────
@bot.command(name="rank", aliases=["top"])
async def rank(ctx, count: int = 10):
    await ctx.typing()
    data = await fetch(f"{REST_URL}/cosmos/staking/v1beta1/validators?status=BOND_STATUS_BONDED&pagination.limit=100")
    if not data:
        await ctx.send("❌ Error fetching data.")
        return
    vals = sorted(data.get("validators",[]), key=lambda x: int(x.get("tokens",0)), reverse=True)
    e = discord.Embed(title=f"🏆 Top {min(count,25)} Validators by Stake", color=0xffd700)
    medals = ["🥇","🥈","🥉"]
    lines = []
    for i, v in enumerate(vals[:min(count,25)]):
        medal = medals[i] if i < 3 else f"`#{i+1}`"
        moniker = v.get('description',{}).get('moniker','?')
        tokens = fmt(v.get('tokens',0))
        jailed = "🔴" if v.get("jailed") else ""
        lines.append(f"{medal} **{moniker}** {jailed} — {tokens}")
    e.description = "\n".join(lines)
    e.set_footer(text=f"Updated: {datetime.utcnow().strftime('%H:%M UTC')}")
    await ctx.send(embed=e)

# ── STATUS ─────────────────────────────────────────────────
@bot.command(name="status")
async def status(ctx):
    await ctx.typing()
    block = await fetch(f"{RPC_URL}/status")
    pool = await fetch(f"{REST_URL}/cosmos/staking/v1beta1/pool")
    vals = await fetch(f"{REST_URL}/cosmos/staking/v1beta1/validators?pagination.limit=500")
    e = discord.Embed(title="🌐 Republic AI Network Status", color=0x00ff88)
    if block:
        sync = block.get("result",{}).get("sync_info",{})
        e.add_field(name="📦 Block", value=sync.get("latest_block_height","?"), inline=True)
        e.add_field(name="🔄 Syncing", value="Yes" if sync.get("catching_up") else "No", inline=True)
    if pool:
        e.add_field(name="💎 Bonded", value=fmt(pool.get("pool",{}).get("bonded_tokens",0)), inline=True)
    if vals:
        all_vals = vals.get("validators",[])
        bonded = sum(1 for v in all_vals if "BONDED" in v.get("status",""))
        jailed = sum(1 for v in all_vals if v.get("jailed"))
        e.add_field(name="✅ Active Validators", value=str(bonded), inline=True)
        e.add_field(name="🔴 Jailed", value=str(jailed), inline=True)
    e.set_footer(text=f"Updated: {datetime.utcnow().strftime('%H:%M UTC')}")
    await ctx.send(embed=e)

# ── JOBS ───────────────────────────────────────────────────
@bot.command(name="jobs")
async def jobs(ctx, count: int = 10):
    await ctx.typing()
    data = await fetch(f"{REST_URL}/republic/computevalidation/v1/job")
    if not data:
        await ctx.send("❌ Error fetching jobs.")
        return
    js = sorted(data.get("jobs",[]), key=lambda x: int(x.get("id",0)), reverse=True)
    e = discord.Embed(title="⚙️ Recent Compute Jobs", color=0x6366f1)
    status_emoji = {"PendingValidation":"⏳","Completed":"✅","Failed":"❌","Processing":"🔄"}
    lines = []
    for j in js[:min(count,15)]:
        st = j.get('status','?')
        emoji = status_emoji.get(st, "❓")
        lines.append(f"{emoji} Job **#{j.get('id','?')}** — {st}")
    e.description = "\n".join(lines) if lines else "No jobs found"
    await ctx.send(embed=e)

# ── MYJOBS ─────────────────────────────────────────────────
@bot.command(name="myjobs")
async def myjobs(ctx, address: str = None):
    if not address:
        await ctx.send("Usage: `/myjobs <rai_address>`")
        return
    await ctx.typing()
    data = await fetch(f"{REST_URL}/republic/computevalidation/v1/job")
    if not data:
        await ctx.send("❌ Error fetching jobs.")
        return
    all_jobs = data.get("jobs", [])
    my = [j for j in all_jobs if address.lower() in str(j).lower()]
    total = len(my)
    completed = sum(1 for j in my if j.get("status") == "Completed")
    pending = sum(1 for j in my if j.get("status") == "PendingValidation")
    failed = sum(1 for j in my if j.get("status") == "Failed")
    e = discord.Embed(title=f"📊 Jobs for `{address[:20]}...`", color=0x6366f1)
    e.add_field(name="Total Jobs", value=str(total), inline=True)
    e.add_field(name="✅ Completed", value=str(completed), inline=True)
    e.add_field(name="⏳ Pending", value=str(pending), inline=True)
    e.add_field(name="❌ Failed", value=str(failed), inline=True)
    if my:
        latest = sorted(my, key=lambda x: int(x.get("id",0)), reverse=True)[:3]
        lines = [f"Job #{j.get('id')} — {j.get('status')}" for j in latest]
        e.add_field(name="Latest Jobs", value="\n".join(lines), inline=False)
    await ctx.send(embed=e)

# ── LEADERBOARD ────────────────────────────────────────────
@bot.command(name="leaderboard", aliases=["lb"])
async def leaderboard(ctx):
    await ctx.typing()
    data = await fetch(f"{REST_URL}/republic/computevalidation/v1/job")
    vals = await fetch(f"{REST_URL}/cosmos/staking/v1beta1/validators?pagination.limit=500")
    if not data:
        await ctx.send("❌ Error fetching data.")
        return
    all_jobs = data.get("jobs", [])
    val_map = {}
    if vals:
        for v in vals.get("validators", []):
            addr = v.get("operator_address","")
            moniker = v.get("description",{}).get("moniker","?")
            val_map[addr] = moniker
    job_counts = {}
    for j in all_jobs:
        validator = j.get("validator", j.get("target_validator", "unknown"))
        job_counts[validator] = job_counts.get(validator, 0) + 1
    sorted_vals = sorted(job_counts.items(), key=lambda x: x[1], reverse=True)
    e = discord.Embed(title="🏆 GPU Miner Leaderboard — Jobs Completed", color=0xffd700)
    medals = ["🥇","🥈","🥉"]
    lines = []
    for i, (addr, count) in enumerate(sorted_vals[:10]):
        medal = medals[i] if i < 3 else f"`#{i+1}`"
        name = val_map.get(addr, addr[:20]+"...")
        lines.append(f"{medal} **{name}** — {count} jobs")
    e.description = "\n".join(lines) if lines else "No data"
    e.set_footer(text=f"Total jobs on chain: {len(all_jobs)} | Updated: {datetime.utcnow().strftime('%H:%M UTC')}")
    await ctx.send(embed=e)

# ── STATS ──────────────────────────────────────────────────
@bot.command(name="stats")
async def stats(ctx, *, query: str = None):
    await ctx.typing()
    if not query:
        await ctx.send("Usage: `/stats <validator_name_or_address>`")
        return
    vals_data = await fetch(f"{REST_URL}/cosmos/staking/v1beta1/validators?pagination.limit=500")
    jobs_data = await fetch(f"{REST_URL}/republic/computevalidation/v1/job")
    if not vals_data:
        await ctx.send("❌ Error fetching data.")
        return
    found = next((v for v in vals_data.get("validators",[]) if query.lower() in v.get("description",{}).get("moniker","").lower() or query.lower() in v.get("operator_address","").lower()), None)
    if not found:
        await ctx.send(f"❌ Validator not found: `{query}`")
        return
    addr = found.get("operator_address","")
    moniker = found.get("description",{}).get("moniker","?")
    all_jobs = jobs_data.get("jobs",[]) if jobs_data else []
    my_jobs = [j for j in all_jobs if addr.lower() in str(j).lower()]
    completed = sum(1 for j in my_jobs if j.get("status") == "Completed")
    pending = sum(1 for j in my_jobs if j.get("status") == "PendingValidation")
    color = 0x00ff88 if not found.get("jailed") else 0xff4444
    e = discord.Embed(title=f"📈 Full Stats: {moniker}", color=color)
    e.add_field(name="Status", value="✅ Bonded" if "BONDED" in found.get("status","") else found.get("status","?"), inline=True)
    e.add_field(name="Jailed", value="🔴 YES" if found.get("jailed") else "🟢 NO", inline=True)
    e.add_field(name="Stake", value=fmt(found.get("tokens",0)), inline=True)
    e.add_field(name="Commission", value=f"{float(found.get('commission',{}).get('commission_rates',{}).get('rate',0))*100:.1f}%", inline=True)
    e.add_field(name="Total Jobs", value=str(len(my_jobs)), inline=True)
    e.add_field(name="✅ Completed", value=str(completed), inline=True)
    e.add_field(name="⏳ Pending", value=str(pending), inline=True)
    e.add_field(name="Address", value=f"`{addr}`", inline=False)
    await ctx.send(embed=e)

# ── HELP ───────────────────────────────────────────────────
@bot.command(name="help", aliases=["commands"])
async def help_cmd(ctx):
    e = discord.Embed(title="🤖 Republic AI Bot — Commands", color=0x6366f1)
    e.add_field(name="/validator <name>", value="Validator lookup by name or address", inline=False)
    e.add_field(name="/rank [count]", value="Top validators by stake", inline=False)
    e.add_field(name="/status", value="Network status & block height", inline=False)
    e.add_field(name="/jobs [count]", value="Recent compute jobs", inline=False)
    e.add_field(name="/myjobs <rai_address>", value="Job stats for any address", inline=False)
    e.add_field(name="/leaderboard", value="Top GPU miners by job count", inline=False)
    e.add_field(name="/stats <name>", value="Full validator + job stats combined", inline=False)
    e.set_footer(text="Republic AI Validator Bot by ERHANREPU | github.com/erhnysr")
    await ctx.send(embed=e)

# ── JAIL MONITOR ───────────────────────────────────────────
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
                await ch.send(f"🔴 **JAILED**: {moniker} (`{addr}`)")
            elif not jailed and prev and ch:
                await ch.send(f"🟢 **UNJAILED**: {moniker} (`{addr}`)")
            validator_states[addr] = {"jailed": jailed}
    except Exception as ex:
        print(f"Monitor error: {ex}")

@jail_monitor.before_loop
async def before():
    await bot.wait_until_ready()

bot.run(BOT_TOKEN)
