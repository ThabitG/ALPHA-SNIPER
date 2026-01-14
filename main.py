import asyncio, os, json, base58, aiohttp, websockets, re
from threading import Thread
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from dotenv import load_dotenv
import telebot

# ---------- SETUP & KEYS ----------
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
bot = telebot.TeleBot(TELEGRAM_TOKEN)
solana = AsyncClient(os.getenv('RPC_URL'))
WSS_URL = os.getenv('WSS_URL')

try:
    user = Keypair.from_bytes(base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY')))
    print(f"✅ Wallet Loaded: {user.pubkey()}")
except Exception as e:
    print(f"❌ Wallet Error: {e}")
    exit()

# ---------- SETTINGS ----------
AMOUNT_SOL = 0.03
MAX_SLIPPAGE = 1500      # 15%
PRIORITY_FEE = 100000    # MEV-style
MIN_LIQ_USD = 10000      # Filter $10k
MOONBAG_PCT = 0.15       # 15% Hold forever

def tg(m):
    """Tuma taarifa Telegram"""
    try: bot.send_message(CHAT_ID, m, parse_mode='Markdown')
    except: pass

# ---------- TRADING ENGINE (Jupiter) ----------

async def swap(in_m, out_m, amt):
    async with aiohttp.ClientSession() as s:
        try:
            q_url = f"https://quote-api.jup.ag/v6/quote?inputMint={in_m}&outputMint={out_m}&amount={int(amt)}&slippageBps={MAX_SLIPPAGE}"
            async with s.get(q_url) as r:
                q = await r.json()
            
            p = {"quoteResponse": q, "userPublicKey": str(user.pubkey()), "wrapAndUnwrapSol": True, "prioritizationFeeLamports": PRIORITY_FEE}
            async with s.post("https://quote-api.jup.ag/v6/swap", json=p) as r:
                sw = await r.json()
            
            raw = base58.b58decode(sw["swapTransaction"])
            tx = VersionedTransaction.from_bytes(raw)
            signed = VersionedTransaction(tx.message, [user.sign_message(tx.message)])
            res = await solana.send_raw_transaction(bytes(signed))
            return {"sig": str(res.value), "amt": float(q["outAmount"])}
        except: return None

# ---------- MAIN LISTENER ----------

async def main_listener():
    RAYDIUM = "675kPX9MHTjS2zt1qf1NYzt2i64ZEv3M96GvLpSaVYn"
    async with websockets.connect(WSS_URL) as ws:
        await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"logsSubscribe","params":[{"mentions":[RAYDIUM]},{"commitment":"processed"}]}))
        tg("🚀 **ALPHA-SNIPER v3.0 ACTIVE**\nAutonomous Mode: ON")

        while True:
            try:
                msg = json.loads(await ws.recv())
                # ... (Trading logic inaendelea hapa)
                pass
            except: continue

# ---------- START BOT ----------

if __name__ == "__main__":
    # 1. Hapa tunafuta session zote za zamani kuzuia Conflict 409
    try:
        bot.remove_webhook()
        print("✅ Webhook removed. Starting fresh...")
    except:
        pass

    # 2. skip_pending=True inazuia bot kusoma meseji za zamani ambazo zingevuruga amri
    Thread(target=lambda: bot.infinity_polling(non_stop=True, skip_pending=True), daemon=True).start()
    
    # 3. Anza engine ya Solana
    asyncio.run(main_listener())
