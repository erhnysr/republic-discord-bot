import discord
from discord.ext import commands, tasks
import aiohttp
from datetime import datetime
import asyncio

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Buraya bot token'ınızı yazın
ALERT_CHANNEL_ID = 123456789

RPC_URL = "https://rpc.republicai.io"
REST_URL = "https://rest.republicai.io"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)
validator_states = {}

async def fetch(url):
    try:
        # Timeout ve SSL ayarları
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        connector = aiohttp.TCPConnector(ssl=False, ttl_dns_cache=300)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(url) as r:
                if r.status == 200:
                    return await r.json()
    except asyncio.TimeoutError:
        print(f"Timeout: {url}")
    except Exception as e:
        print(f"Error: {e}")
    return None

# ... (geri kalan kod aynı)
