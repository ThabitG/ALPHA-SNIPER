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
MAX_SLIPPAGE = 1500      # 15% slippage kwa ajili ya volatility
PRIORITY_FEE = 100000    # MEV-style priority (Helius friendly)
MIN_LIQ_USD = 10000      # Filter: Usinunue token yenye liquidity chini ya $10k
MOONBAG_PCT = 0.15       # 15% ya tokens zinaachwa forever (Moonshot)

def tg(m):
    """Function ya kutuma ujumbe Telegram"""
    try: bot.send_message(CHAT_ID, m, parse_mode='Markdown')
    except: pass

# ---------- TELEGRAM COMMANDS ----------

@bot.message_handler(commands=['balance'])
def check_balance(m):
    async def get_bal():
        try:
            resp = await solana.get_balance(user.pubkey())
            tg(f"💰 **Wallet Balance:** `{resp.value / 1e9:.4f} SOL`")
        except: tg("❌ Error kupata salio la wallet.")
    asyncio.run_coroutine_threadsafe(get_bal(), asyncio.get_event_loop())

@bot.message_handler(commands=['status'])
def status(m):
    tg("🟢 **ALPHA-SNIPER Status:** Running\n🛰️ **Mode:** Autonomous Protection ON")

# ---------- FILTERS (Anti-Rug & Momentum) ----------

async def is_high_quality(mint):
    """
    Uchujaji wa AI: RugCheck, Honeypot, na Volume Check
    """
    async with aiohttp.ClientSession() as s:
        try:
            # 1. RugCheck Authority & Security Score
            async with s.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary") as r:
                data = await r.json()
                if data.get("score", 1000) > 400: return False # Block high risk
                if data.get("tokenMeta", {}).get("mutable", True): return False # Block mutable tokens

            # 2. DexScreener Scanner (Volume & Liquidity)
            async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}") as r:
                dex = await r.json()
                pairs = dex.get("pairs", [])
                if not pairs: return False
                
                pair = pairs[0]
                if pair.get("liquidity", {}).get("usd", 0) < MIN_LIQ_USD: return False
                if pair.get("volume", {}).get("h1", 0) < 5000: return False # Block zero volume
            return True
        except: return False

# ---------- TRADING ENGINE (Jupiter V6) ----------

async def swap(in_m, out_m, amt):
    """Inafanya Buy/Sell kupitia Jupiter API"""
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

# ---------- MONITORING & EXIT STRATEGY ----------

class SmartEngine:
    def __init__(self, mint, buy_p, total_tokens):
        self.mint = mint
        self.buy_p = buy_p
        self.rem = total_tokens
        self.high = buy_p
        self.moonbag_saved = False
        self.targets = [0.25, 0.50, 0.75, 1.00] # 4-Stage TP

    async def monitor(self):
        tg(f"🎯 **Target Locked:** `{self.mint[:6]}`\nStrategy: Scaled TP + Whale Radar")
        while self.rem > 0:
            try:
                async with aiohttp.ClientSession() as s:
                    d = await (await s.get(f"https://api.jup.ag/price/v2?ids={self.mint}")).json()
                    curr = float(d["data"][self.mint]["price"])
                
                profit = (curr - self.buy_p) / self.buy_p
                if curr > self.high: self.high = curr # Trailing High

                # WHALE DUMP RADAR: Ikishuka 15% kutoka kileleni, UZA!
                if curr < self.high * 0.85:
                    await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem)
                    tg(f"🐋 **Whale Dump Detected!** Emergency Exit on `{self.mint[:5]}`"); break

                # SCALED TAKE PROFIT & MOONBAG
                for t in self.targets[:]:
                    if profit >= t:
                        if not self.moonbag_saved:
                            keep = self.rem * MOONBAG_PCT
                            self.rem -= keep # Tenga moonbag
                            self.moonbag_saved = True
                            tg(f"💎 **Moonbag Secured (15%)** for `{self.mint[:5]}`")
                        
                        sell_qty = self.rem * 0.25 if t < 1.0 else self.rem
                        if await swap(self.mint, "So11111111111111111111111111111111111111112", sell_qty):
                            self.rem -= sell_qty
                            tg(f"💰 **TP {int(t*100)}% Hit!** Sold portion.")
                            self.targets.remove(t)
                
                # GLOBAL STOP LOSS
                if profit <= -0.20:
                    await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem)
                    tg(f"🛑 **Stop Loss Hit** on `{self.mint[:5]}`"); break
                
                await asyncio.sleep(4)
            except: await asyncio.sleep(10)

# ---------- MAIN LISTENER ----------

async def main_listener():
    RAYDIUM = "675kPX9MHTjS2zt1qf1NYzt2i64ZEv3M96GvLpSaVYn"
    async with websockets.connect(WSS_URL) as ws:
        await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"logsSubscribe","params":[{"mentions":[RAYDIUM]},{"commitment":"processed"}]}))
        tg("🚀 **ALPHA-SNIPER v3.0 ACTIVE**\nAutonomous Mode: ON")

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
                            
                            # Chuja rugpulls na fake volume
                            if await is_high_quality(mint):
                                buy_res = await swap("So11111111111111111111111111111111111111112", mint, AMOUNT_SOL*1e9)
                                if buy_res:
                                    # Anza kufuatilia faida mara moja
                                    async with aiohttp.ClientSession() as s:
                                        p_data = await (await s.get(f"https://api.jup.ag/price/v2?ids={mint}")).json()
                                        curr_p = float(p_data["data"][mint]["price"])
                                    asyncio.create_task(SmartEngine(mint, curr_p, buy_res["amt"]).monitor())
            except: continue

if __name__ == "__main__":
    # Anza Telegram Polling kwenye thread tofauti kuzuia Conflict 409
    Thread(target=lambda: bot.infinity_polling(non_stop=True, timeout=60), daemon=True).start()
    asyncio.run(main_listener())
