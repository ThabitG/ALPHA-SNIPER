import asyncio, os, json, base58, aiohttp, websockets, re
from threading import Thread
from datetime import datetime
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from dotenv import load_dotenv
import telebot

# ---------- SETUP & CONFIG ----------
load_dotenv()

TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
RPC_URL = os.getenv('RPC_URL')
WSS_URL = os.getenv('WSS_URL')

bot = telebot.TeleBot(TOKEN)
# Tunaanzisha client mara moja ili iweze kutumika kote
solana_client = AsyncClient(RPC_URL)

try:
    # Kutumia from_bytes kuzuia AttributeError
    raw_key = base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY'))
    user = Keypair.from_bytes(raw_key)
    print(f"✅ Wallet Connected: {user.pubkey()}")
except Exception as e:
    print(f"❌ Wallet Error: {e}"); exit(1)

# ---------- SETTINGS ----------
AMOUNT_SOL = 0.03
MIN_LIQUIDITY_USD = 5000  
MAX_SLIPPAGE = 1500  
PRIORITY_FEE = 300000

def tg(m):
    try: bot.send_message(CHAT_ID, m, parse_mode='Markdown', disable_web_page_preview=True)
    except: pass

# ---------- TELEGRAM COMMANDS (FOR TESTING) ----------

@bot.message_handler(commands=['balance'])
def check_balance(message):
    """Amri ya kuangalia kama wallet imeunganishwa kweli"""
    async def get_bal():
        try:
            res = await solana_client.get_balance(user.pubkey())
            bal = res.value / 1e9
            tg(f"💰 **Wallet Connection OK!**\nAddress: `{user.pubkey()}`\nBalance: `{bal} SOL`")
        except Exception as e:
            tg(f"❌ Connection Error: {str(e)}")
    
    # Tunatumia loop iliyopo kuzuia mgongano
    asyncio.run_coroutine_threadsafe(get_bal(), bot_loop)

@bot.message_handler(commands=['status'])
def check_status(message):
    tg("🟢 **Sniper Status:** Online & Scanning Raydium...")

# ---------- NOTIFICATIONS & ENGINE ----------

async def hourly_heartbeat():
    """Notification ya kila saa moja"""
    while True:
        await asyncio.sleep(3600)
        now = datetime.now().strftime("%H:%M")
        tg(f"⏰ **Hourly Update ({now})**\nBot bado inapiga kazi...")

async def get_token_info(mint):
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}") as r:
                data = await r.json()
                pair = data['pairs'][0]
                return pair['baseToken']['name'], pair['baseToken']['symbol'], float(pair['liquidity']['usd'])
        except: return "Unknown", "MEME", 0

# ---------- MAIN LISTENER ----------

async def main_listener():
    RAYDIUM = "675kPX9MHTjS2zt1qf1NYzt2i64ZEv3M96GvLpSaVYn"
    SOL_MINT = "So11111111111111111111111111111111111111112"
    
    asyncio.create_task(hourly_heartbeat())
    
    while True:
        try:
            async with websockets.connect(WSS_URL) as ws:
                await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"logsSubscribe","params":[{"mentions":[RAYDIUM]},{"commitment":"processed"}]}))
                print("🚀 Sniper Scanning..."); tg("🚀 **SNIPER ACTIVE & SCANNING**")
                
                while True:
                    msg = json.loads(await ws.recv())
                    logs = msg.get("params", {}).get("result", {}).get("value", {}).get("logs", [])
                    for l in logs:
                        if "initialize2" in l.lower():
                            mints = re.findall(r'([1-9A-HJ-NP-Za-km-z]{32,44})', l)
                            for mint in mints:
                                if mint == RAYDIUM or len(mint) < 40: continue
                                
                                name, symbol, liq = await get_token_info(mint)
                                if liq >= MIN_LIQUIDITY_USD:
                                    tg(f"🎯 **Target Spotted!**\nName: {name} ({symbol})\nLiq: ${liq}\n`{mint}`")
                                    # Hapa unaweza kuweka kodi ya 'swap' kununua
        except: await asyncio.sleep(5)

# ---------- EXECUTION ----------

bot_loop = asyncio.new_event_loop()

def start_bot():
    asyncio.set_event_loop(bot_loop)
    # Hii inahakikisha bot inasikiliza meseji za Telegram bila kukwama
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    # Start Telegram in a separate thread
    Thread(target=start_bot, daemon=True).start()
    # Start Sniper
    asyncio.run(main_listener())
