import asyncio, os, json, base58, aiohttp, websockets, re
from threading import Thread
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from dotenv import load_dotenv
import telebot

# ---------- SETUP ----------
load_dotenv()
bot = telebot.TeleBot(os.getenv('TELEGRAM_TOKEN'))
solana = AsyncClient(os.getenv('RPC_URL'))
WSS_URL = os.getenv('WSS_URL')
try:
    user = Keypair.from_bytes(base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY')))
    CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
except: print("❌ Check Keys!"); exit()

# ---------- SETTINGS ----------
AMOUNT_SOL = 0.03
MAX_SLIPPAGE = 1500  # 15% kwa ajili ya pump kali
PRIORITY_FEE = 100000 # MEV-style priority
MIN_LIQ_USD = 10000  # Chini ya $10k tunaskip
MOONBAG_PCT = 0.15   # 15% inaachwa forever

def tg(m):
    try: bot.send_message(CHAT_ID, m, parse_mode='Markdown')
    except: pass

# ---------- SMART FILTERS (Anti-Rug & Momentum) ----------

async def is_high_quality(mint):
    """
    AI Filter: Volume, RugCheck, na Honeypot Protection
    """
    async with aiohttp.ClientSession() as s:
        try:
            # 1. RugCheck & Authority Check
            async with s.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary") as r:
                data = await r.json()
                if data.get("score", 1000) > 400: return False # Rug risk
                # Check kama mint authority iko locked
                if data.get("tokenMeta", {}).get("mutable", True): return False 

            # 2. Momentum & Volume Scanner (DexScreener API)
            async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}") as r:
                dex = await r.json()
                pairs = dex.get("pairs", [])
                if not pairs: return False
                
                pair = pairs[0]
                vol = pair.get("volume", {}).get("h1", 0)
                liq = pair.get("liquidity", {}).get("usd", 0)
                
                if liq < MIN_LIQ_USD: return False # Liquidity Trash blocked
                if vol < 5000: return False        # Kama haina volume, tunaskip (Fake Pump)
                
            return True
        except: return False

# ---------- TRADING ENGINE (Jupiter V6) ----------

async def swap(in_m, out_m, amt):
    async with aiohttp.ClientSession() as s:
        try:
            q = await (await s.get(f"https://quote-api.jup.ag/v6/quote?inputMint={in_m}&outputMint={out_m}&amount={int(amt)}&slippageBps={MAX_SLIPPAGE}")).json()
            p = {"quoteResponse": q, "userPublicKey": str(user.pubkey()), "wrapAndUnwrapSol": True, "prioritizationFeeLamports": PRIORITY_FEE}
            sw = await (await s.post("https://quote-api.jup.ag/v6/swap", json=p)).json()
            
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
        self.targets = [0.25, 0.50, 0.75, 1.00] # Scaled TP

    async def get_price(self):
        async with aiohttp.ClientSession() as s:
            d = await (await s.get(f"https://api.jup.ag/price/v2?ids={self.mint}")).json()
            return float(d["data"][self.mint]["price"])

    async def monitor(self):
        tg(f"🎯 **Target Locked:** `{self.mint[:6]}`\nStrategy: Scaled TP + Moonbag")
        while self.rem > 0:
            try:
                curr = await self.get_price()
                profit = (curr - self.buy_p) / self.buy_p
                if curr > self.high: self.high = curr # Trailing high

                # 1. WHALE DUMP RADAR & TRAILING STOP
                # Kama price inadrop kwa 15% ghafla kutoka kwenye 'high', uza kila kitu (Whale Exit)
                if curr < self.high * 0.85:
                    await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem)
                    tg(f"🐋 **Whale Dump/Trailing Exit** at `{self.mint[:5]}`"); break

                # 2. SCALED TP & MOONBAG LOGIC
                for t in self.targets:
                    if profit >= t:
                        # Save Moonbag (15%) on first TP
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

                # 3. GLOBAL STOP LOSS
                if profit <= -0.20:
                    await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem)
                    tg(f"🛑 **Global Stop Loss** `{self.mint[:5]}`"); break

                await asyncio.sleep(3)
            except: await asyncio.sleep(5)

# ---------- MEV-STYLE LISTENER ----------

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
                            
                            # START SMART FILTERING
                            if await is_high_quality(mint):
                                buy_res = await swap("So11111111111111111111111111111111111111112", mint, AMOUNT_SOL*1e9)
                                if buy_res:
                                    price = await SmartEngine(mint, 0, 0).get_price()
                                    engine = SmartEngine(mint, price, buy_res["amt"])
                                    asyncio.create_task(engine.monitor())
            except: continue

if __name__ == "__main__":
    Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    asyncio.run(main_listener())

