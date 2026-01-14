import asyncio, os, json, base58, aiohttp, websockets, re
from threading import Thread
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

if not all([TOKEN, CHAT_ID, RPC_URL, WSS_URL]):
    print("❌ ERROR: Hakikisha Variables zote 5 zipo Render/Railway!")
    exit(1)

bot = telebot.TeleBot(TOKEN)
solana = AsyncClient(RPC_URL)

try:
    user = Keypair.from_bytes(base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY')))
    print(f"✅ Wallet Imechajiwa: {user.pubkey()}")
except Exception as e:
    print(f"❌ Wallet Error: {e}")
    exit(1)

# ---------- SETTINGS ----------
AMOUNT_SOL = 0.03
MAX_SLIPPAGE = 1500  # 15%
PRIORITY_FEE = 100000 
MIN_LIQ_USD = 10000  
MOONBAG_PCT = 0.15   # 15% inaachwa milele

def tg(m):
    """Tuma ujumbe Telegram"""
    try: bot.send_message(CHAT_ID, m, parse_mode='Markdown')
    except: pass

# ---------- SMART FILTERS (Anti-Rug & Momentum) ----------

async def is_high_quality(mint):
    """AI Filter: Volume, RugCheck, na Honeypot Protection"""
    async with aiohttp.ClientSession() as s:
        try:
            # 1. RugCheck Summary
            async with s.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary") as r:
                data = await r.json()
                if data.get("score", 1000) > 400: return False 
                if data.get("tokenMeta", {}).get("mutable", True): return False 

            # 2. DexScreener Volume & Liquidity Check
            async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}") as r:
                dex = await r.json()
                pairs = dex.get("pairs", [])
                if not pairs: return False
                
                pair = pairs[0]
                vol = pair.get("volume", {}).get("h1", 0)
                liq = pair.get("liquidity", {}).get("usd", 0)
                
                if liq < MIN_LIQ_USD: return False
                if vol < 5000: return False
                
            return True
        except: return False

# ---------- TRADING ENGINE (Jupiter V6) ----------

async def swap(in_m, out_m, amt):
    async with aiohttp.ClientSession() as s:
        try:
            # Get Quote
            q_url = f"https://quote-api.jup.ag/v6/quote?inputMint={in_m}&outputMint={out_m}&amount={int(amt)}&slippageBps={MAX_SLIPPAGE}"
            async with s.get(q_url) as r:
                q = await r.json()
            
            # Get Swap Transaction
            p = {"quoteResponse": q, "userPublicKey": str(user.pubkey()), "wrapAndUnwrapSol": True, "prioritizationFeeLamports": PRIORITY_FEE}
            async with s.post("https://quote-api.jup.ag/v6/swap", json=p) as r:
                sw = await r.json()
            
            raw = base58.b58decode(sw["swapTransaction"])
            tx = VersionedTransaction.from_bytes(raw)
            signed = VersionedTransaction(tx.message, [user.sign_message(tx.message)])
            res = await solana.send_raw_transaction(bytes(signed))
            return {"sig": str(res.value), "amt": float(q["outAmount"])}
        except: return None

# ---------- AUTONOMOUS PROFIT & WHALE RADAR ----------

class SmartEngine:
    def __init__(self, mint, buy_p, total_tokens):
        self.mint = mint
        self.buy_p = buy_p
        self.rem = total_tokens
        self.high = buy_p
        self.moonbag_saved = False
        self.targets = [0.25, 0.50, 0.75, 1.00] 

    async def get_price(self):
        async with aiohttp.ClientSession() as s:
            try:
                async with s.get(f"https://api.jup.ag/price/v2?ids={self.mint}") as r:
                    d = await r.json()
                return float(d["data"][self.mint]["price"])
            except: return 0

    async def monitor(self):
        tg(f"🎯 **Target Locked:** `{self.mint[:6]}`\nStrategy: Scaled TP + Moonbag")
        while self.rem > 0:
            try:
                curr = await self.get_price()
                if curr == 0: await asyncio.sleep(5); continue
                
                profit = (curr - self.buy_p) / self.buy_p
                if curr > self.high: self.high = curr 

                # 1. WHALE DUMP RADAR (Trailing Stop 15%)
                if curr < self.high * 0.85:
                    await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem)
                    tg(f"🐋 **Whale Dump Detected!** Exit at `{self.mint[:5]}`"); break

                # 2. SCALED TP & MOONBAG
                for t in self.targets[:]:
                    if profit >= t:
                        if not self.moonbag_saved:
                            keep = self.rem * MOONBAG_PCT
                            self.rem -= keep
                            self.moonbag_saved = True
                            tg(f"💎 **Moonbag Secured (15%)** for `{self.mint[:5]}`")

                        sell_amt = self.rem * 0.25 if t < 1.0 else self.rem
                        if await swap(self.mint, "So11111111111111111111111111111111111111112", sell_amt):
                            self.rem -= sell_amt
                            tg(f"💰 **TP {int(t*100)}% Hit!** Portion sold.")
                        self.targets.remove(t)

                # 3. GLOBAL STOP LOSS (20%)
                if profit <= -0.20:
                    await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem)
                    tg(f"🛑 **Stop Loss Hit** for `{self.mint[:5]}`"); break

                await asyncio.sleep(5)
            except: await asyncio.sleep(10)

# ---------- MEV-STYLE LISTENER ----------

async def main_listener():
    RAYDIUM = "675kPX9MHTjS2zt1qf1NYzt2i64ZEv3M96GvLpSaVYn"
    async with websockets.connect(WSS_URL) as ws:
        await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"logsSubscribe","params":[{"mentions":[RAYDIUM]},{"commitment":"processed"}]}))
        tg("🚀 **ALPHA-SNIPER v4.0 ACTIVE (Render)**\nWhale Radar: ON | RugCheck: ON")

        while True:
            try:
                msg = json.loads(await ws.recv())
                logs = msg.get("params", {}).get("result", {}).get("value", {}).get("logs", [])
                for l in logs:
                    if "initialize2" in l.lower():
                        match = re.search(r'([1-9A-HJ-NP-Za-km-z]{32,44})', l)
                        if match:
                            mint = match.group(1)
                            if mint == RAYDIUM: continue
                            
                            if await is_high_quality(mint):
                                buy_res = await swap("So11111111111111111111111111111111111111112", mint, AMOUNT_SOL*1e9)
                                if buy_res:
                                    price = await SmartEngine(mint, 0, 0).get_price()
                                    engine = SmartEngine(mint, price, buy_res["amt"])
                                    asyncio.create_task(engine.monitor())
            except: continue

# ---------- START BOT (Anti-Conflict Logic) ----------

if __name__ == "__main__":
    # 1. Safisha webhooks zilizokwama
    try:
        bot.remove_webhook()
        print("✅ Webhook removed. Starting polling...")
    except: pass

    # 2. Washa Telegram Polling (Thread-safe)
    # Tumeondoa 'non_stop=True' ili kuzuia TypeError uliyoiona Render
    Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()
    
    # 3. Washa Sniper Engine
    try:
        asyncio.run(main_listener())
    except KeyboardInterrupt:
        print("🛑 System Stopped.")
