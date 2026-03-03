import discord
from discord.ext import commands, tasks
import aiohttp
from datetime import datetime

BOT_TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"
ALERT_CHANNEL_ID = 123456789

RPC_URL = "https://rpc.republicai.io"
REST_URL = "https://rest.republicai.io"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)
validator_states = {}

async def fetch(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 200:
                    return await r.json()
    except:
        return None

def format_tokens(amount):
    try:
        return f"{int(amount) / 1e18:,.2f} RAI"
    except:
        return str(amount)

def status_emoji(status):
    return {"BOND_STATUS_BONDED": "🟢 Active", "BOND_STATUS_UNBONDING": "🟡 Unbonding", "BOND_STATUS_UNBONDED": "🔴 Inactive"}.get(status, "⚪ Unknown")

@bot.event
async def on_ready():
    print(f"✅ Republic AI Bot online: {bot.user}")
    jail_monitor.start()

@bot.command(name="validator", aliases=["val"])
async def validator_info(ctx, *, query: str):
    await ctx.typing()
    data = await fetch(f"{REST_URL}/cosmos/staking/v1beta1/validators?pagination.limit=500")
    if not data:
        await ctx.send("❌ Could not fetch validator data.")
        return
    found = next((v for v in data.get("validators", []) if query.lower() in v.get("description", {}).get("moniker", "").lower() or query.lower() in v.get("operator_address", "").lower()), None)
    if not found:
        await ctx.send(f"❌ Validator not found.")
        return
    desc = found.get("description", {})
    embed = discord.Embed(title=f"🤖 {desc.get('moniker', 'Unknown')}", color=0x6366f1)
    embed.add_field(name="Status", value=status_emoji(found.get("status", "")), inline=True)
    embed.add_field(name="Jailed", value="⚠️ Yes" if found.get("jailed") else "✅ No", inline=True)
    embed.add_field(name="Tokens", value=format_tokens(found.get("tokens", 0)), inline=True)
    embed.add_field(name="Commission", value=f"{float(found.get('commission', {}).get('commission_rates', {}).get('rate', 0)) * 100:.1f}%", inline=True)
    embed.add_field(name="Address", value=f"`{found.get('operator_address', 'N/A')}`", inline=False)
    embed.set_footer(text="Republic AI Testnet • raitestnet_77701-1")
    await ctx.send(embed=embed)

@bot.command(name="rank", aliases=["top"])
async def top_validators(ctx, count: int = 10):
    await ctx.typing()
    data = await fetch(f"{REST_URL}/cosmos/staking/v1beta1/validators?status=BOND_STATUS_BONDED&pagination.limit=100")
    if not data:
        await ctx.send("❌ Could not fetch validator data.")
        return
    validators = sorted(data.get("validators", []), key=lambda x: int(x.get("tokens", 0)), reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    embed = discord.Embed(title=f"🏆 Top {min(count,25)} Republic AI Validators", color=0x6366f1)
    lines = []
    for i, v in enumerate(validators[:min(count,25)]):
        medal = medals[i] if i < 3 else f"#{i+1}"
        moniker = v.get("description", {}).get("moniker", "Unknown")
        jailed = "⚠️" if v.get("jailed") else ""
        tokens = format_tokens(v.get("tokens", 0))
        lines.append(f"{medal} **{moniker}** {jailed}\n┗ {tokens}")
    embed.description = "\n".join(lines)
    embed.set_footer(text=f"Republic AI Testnet • {datetime.utcnow().strftime('%H:%M UTC')}")
    await ctx.send(embed=embed)

@bot.command(name="status", aliases=["network"])
async def network_status(ctx):
    await ctx.typing()
    block_data = await fetch(f"{RPC_URL}/status")
    staking_data = await fetch(f"{REST_URL}/cosmos/staking/v1beta1/pool")
    embed = discord.Embed(title="🌐 Republic AI Network Status", color=0x00ff88)
    if block_data:
        sync_info = block_data.get("result", {}).get("sync_info", {})
        embed.add_field(name="Latest Block", value=f"`{sync_info.get('latest_block_height', 'N/A')}`", inline=True)
    if staking_data:
        embed.add_field(name="Total Bonded", value=format_tokens(staking_data.get("pool", {}).get("bonded_tokens", 0)), inline=True)
    embed.add_field(name="Chain ID", value="`raitestnet_77701-1`", inline=True)
    embed.set_footer(text=f"Updated: {datetime.utcnow().strftime('%H:%M UTC')}")
    await ctx.send(embed=embed)

@bot.command(name="jobs")
async def compute_jobs(ctx, count: int = 10):
    await ctx.typing()
    data = await fetch(f"{REST_URL}/republic/computevalidation/job")
    if not data:
        await ctx.send("❌ Could not fetch job data.")
        return
    jobs = sorted(data.get("jobs", []), key=lambda x: int(x.get("id", 0)), reverse=True)
    status_emojis = {"PendingExecution": "⏳", "PendingValidation": "🔄", "Completed": "✅", "Failed": "❌"}
    embed = discord.Embed(title="⚡ Recent Compute Jobs", color=0x6366f1)
    lines = []
    for j in jobs[:min(count,15)]:
        emoji = status_emojis.get(j.get("status",""), "⚪")
        creator = j.get("creator","")[:25]
        lines.append(f"{emoji} **Job #{j.get('id','?')}** — {j.get('status','Unknown')}\n┗ `{creator}...`")
    embed.description = "\n".join(lines) if lines else "No jobs found"
    embed.set_footer(text=f"Republic AI Testnet • {datetime.utcnow().strftime('%H:%M UTC')}")
    await ctx.send(embed=embed)

@tasks.loop(minutes=5)
async def jail_monitor():
    try:
        data = await fetch(f"{REST_URL}/cosmos/staking/v1beta1/validators?pagination.limit=200")
        if not data:
            return
        channel = bot.get_channel(ALERT_CHANNEL_ID)
        if not channel:
            return
        for v in data.get("validators", []):
            addr = v.get("operator_address")
            moniker = v.get("description", {}).get("moniker", "Unknown")
            jailed = v.get("jailed", False)
            prev_jailed = validator_states.get(addr, {}).get("jailed", False)
            if jailed and not prev_jailed:
                embed = discord.Embed(title="⚠️ Validator Jailed!", description=f"**{moniker}** has been jailed", color=0xff4444)
                embed.add_field(name="Address", value=f"`{addr}`")
                await channel.send(embed=embed)
            elif not jailed and prev_jailed:
                embed = discord.Embed(title="✅ Validator Unjailed!", description=f"**{moniker}** is back online", color=0x00ff88)
                embed.add_field(name="Address", value=f"`{addr}`")
                await channel.send(embed=embed)
            validator_states[addr] = {"jailed": jailed}
    except Exception as e:
        print(f"Jail monitor error: {e}")

@jail_monitor.before_loop
async def before_jail_monitor():
    await bot.wait_until_ready()

bot.run(BOT_TOKEN)
