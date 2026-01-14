import asyncio, os, json, base58, aiohttp, websockets, re
from threading import Thread
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from dotenv import load_dotenv
import telebot

# ---------- SETUP ----------
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
bot = telebot.TeleBot(TELEGRAM_TOKEN)
solana = AsyncClient(os.getenv('RPC_URL'))
WSS_URL = os.getenv('WSS_URL')

try:
    user = Keypair.from_bytes(base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY')))
    print(f"✅ Wallet Loaded: {user.pubkey()}")
except: print("❌ Check Keys!"); exit()

# ---------- SETTINGS ----------
AMOUNT_SOL = 0.03
MAX_SLIPPAGE = 1500
PRIORITY_FEE = 100000
MIN_LIQ_USD = 10000

def tg(m):
    try: bot.send_message(CHAT_ID, m, parse_mode='Markdown')
    except: pass

# --- (Hapa katikati weka zile function za swap na SmartEngine kama mwanzo) ---

async def main_listener():
    RAYDIUM = "675kPX9MHTjS2zt1qf1NYzt2i64ZEv3M96GvLpSaVYn"
    async with websockets.connect(WSS_URL) as ws:
        await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"logsSubscribe","params":[{"mentions":[RAYDIUM]},{"commitment":"processed"}]}))
        tg("🚀 **ALPHA-SNIPER v3.0 ACTIVE**\nAutonomous Mode: ON")
        while True:
            try:
                # Listener logic hapa
                pass 
            except: continue

if __name__ == "__main__":
    # skip_pending=True ni MUHIMU kuzuia kosa la 409 Conflict
    Thread(target=lambda: bot.infinity_polling(non_stop=True, skip_pending=True), daemon=True).start()
    asyncio.run(main_listener())
