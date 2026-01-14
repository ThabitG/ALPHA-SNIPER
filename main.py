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

bot = telebot.TeleBot(TOKEN)
solana = AsyncClient(RPC_URL)

try:
    # Tunatumia from_bytes badala ya from_string kuepuka AttributeError
    user = Keypair.from_bytes(base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY')))
    print(f"✅ Wallet Connected: {user.pubkey()}")
except Exception as e:
    print(f"❌ Wallet Error: {e}"); exit(1)

# ---------- SETTINGS ----------
AMOUNT_SOL = 0.03
MIN_LIQUIDITY_USD = 5000  # Imeshushwa kwa ajili ya fursa zaidi
MAX_SLIPPAGE = 1500       # 15% Slippage
PRIORITY_FEE = 300000     # Optimized kwa Helius RPC

def tg(m):
    try: bot.send_message(CHAT_ID, m, parse_mode='Markdown')
    except: pass

# ---------- SMART FILTERS (Liquidity & RugCheck) ----------

async def passes_filters(mint):
    async with aiohttp.ClientSession() as s:
        try:
            # 1. Check Liquidity via Dexscreener kwanza
            async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=5) as r:
                dex_data = await r.json()
                pairs = dex_data.get("pairs", [])
                if not pairs: return False
                
                liq = float(pairs[0].get("liquidity", {}).get("usd", 0))
                if liq < MIN_LIQUIDITY_USD:
                    print(f"⚠️ Skip: Liquidity ${liq} is too low.")
                    return False
            
            # 2. RugCheck Summary (Chini ya 600 ni salama kiasi)
            async with s.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary", timeout=5) as r:
                rug_data = await r.json()
                if rug_data.get("score", 1000) > 600: return False
                
            return True
        except: return False

# ---------- MONITORING ENGINE (Trailing Block Ladder) ----------

class SmartEngine:
    def __init__(self, mint, buy_price, total_tokens):
        self.mint = mint
        self.buy_p = buy_price
        self.rem = total_tokens
        self.high = buy_price
        self.floor = buy_price * 0.80  # Initial Stop Loss ya -20%

    async def get_price(self):
        """Inasoma bei kwa haraka kupitia Dexscreener API"""
        async with aiohttp.ClientSession() as s:
            try:
                async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{self.mint}") as r:
                    d = await r.json()
                    return float(d["pairs"][0]["priceUsd"])
            except: return 0

    async def monitor(self):
        tg(f"🛡️ **Dynamic Ladder Active!** Monitoring `{self.mint[:8]}`\nFloor: -20%")
        while self.rem > 0:
            try:
                curr = await self.get_price()
                if curr <= 0: await asyncio.sleep(5); continue
                
                profit = (curr - self.buy_p) / self.buy_p if self.buy_p > 0 else 0
                if curr > self.high: self.high = curr 

                # --- MFUMO WA BLOCK LADDER ---
                # Kama faida ikifika +40%, lock block ya +25%
                if profit >= 0.40 and self.floor < (self.buy_p * 1.25):
                    self.floor = self.buy_p * 1.25
                    tg(f"🔒 **Block Locked: +25%**\nPrice is up +{int(profit*100)}%")

                # Kama faida ikifika +70%, lock block ya +50%
                elif profit >= 0.70 and self.floor < (self.buy_p * 1.50):
                    self.floor = self.buy_p * 1.50
                    tg(f"🔒 **Block Locked: +50%**")

                # Kama faida ikifika +120%, lock block ya +75%
                elif profit >= 1.20 and self.floor < (self.buy_p * 1.75):
                    self.floor = self.buy_p * 1.75
                    tg(f"🔒 **Block Locked: +75%** - Moon mission! 🚀")

                # --- EXIT LOGIC (Ikigusa Sakafu/Block) ---
                if curr <= self.floor:
                    success = await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem, "LADDER EXIT 🏃‍♂️")
                    if success:
                        tg(f"💰 **Profit Secured!**\nExit Price: {curr}\nApprox Profit: {int(profit*100)}%")
                        break
                
                await asyncio.sleep(5) # Monitor kila sekunde 5
            except: await asyncio.sleep(10)

# ---------- TRADING ENGINE (Jupiter V6) ----------

async def swap(in_m, out_m, amt, action="Trade"):
    async with aiohttp.ClientSession() as s:
        try:
            # Jupiter Quote
            q_url = f"https://quote-api.jup.ag/v6/quote?inputMint={in_m}&outputMint={out_m}&amount={int(amt)}&slippageBps={MAX_SLIPPAGE}"
            async with s.get(q_url) as r: q = await r.json()
            
            # Jupiter Swap
            p = {
                "quoteResponse": q, 
                "userPublicKey": str(user.pubkey()), 
                "wrapAndUnwrapSol": True, 
                "prioritizationFeeLamports": PRIORITY_FEE
            }
            async with s.post("https://quote-api.jup.ag/v6/swap", json=p) as r: sw = await r.json()
            
            # Serialize & Sign Transaction
            raw = base58.b58decode(sw["swapTransaction"])
            tx = VersionedTransaction.from_bytes(raw)
            signed = VersionedTransaction(tx.message, [user.sign_message(tx.message)])
            
            # Send Transaction
            res = await solana.send_raw_transaction(bytes(signed))
            sig = str(res.value)
            
            # Hesabu bei ya kununulia kwa makadirio (USD)
            buy_p = 0
            if action == "BUY":
                buy_p = (amt / 1e9) / (float(q["outAmount"]) / 1e10) # Simple calc
            
            tg(f"🔔 **{action} Executed!**\n[View on Solscan](https://solscan.io/tx/{sig})")
            return {"sig": sig, "amt": float(q["outAmount"]), "price": buy_p}
        except Exception as e:
            print(f"Swap Error: {e}")
            return None

# ---------- SNIPER LISTENER (Raydium Pools) ----------

async def main_listener():
    RAYDIUM = "675kPX9MHTjS2zt1qf1NYzt2i64ZEv3M96GvLpSaVYn"
    SOL_MINT = "So11111111111111111111111111111111111111112"
    
    while True:
        try:
            async with websockets.connect(WSS_URL) as ws:
                # Subscribe kwenye Raydium Logs
                sub_msg = {
                    "jsonrpc":"2.0",
                    "id":1,
                    "method":"logsSubscribe",
                    "params":[{"mentions":[RAYDIUM]},{"commitment":"processed"}]
                }
                await ws.send(json.dumps(sub_msg))
                print("🚀 Sniper Active..."); tg("🚀 **SNIPER ACTIVE & SCANNING**")
                
                while True:
                    msg = json.loads(await ws.recv())
                    logs = msg.get("params", {}).get("result", {}).get("value", {}).get("logs", [])
                    for l in logs:
                        if "initialize2" in l.lower():
                            # Tafuta Mint Address kwenye log
                            mints = re.findall(r'([1-9A-HJ-NP-Za-km-z]{32,44})', l)
                            for mint in mints:
                                if mint == RAYDIUM or len(mint) < 40: continue
                                
                                # Anza mchakato wa kuchuja na kununua
                                if await passes_filters(mint):
                                    buy = await swap(SOL_MINT, mint, AMOUNT_SOL*1e9, "BUY")
                                    if buy:
                                        # Anza Monitor kwa ajili ya TP/SL
                                        asyncio.create_task(SmartEngine(mint, buy["price"], buy["amt"]).monitor())
        except: 
            await asyncio.sleep(5) # Reconnect kama internet ikikata

if __name__ == "__main__":
    # Muhimu: Hii inawasha Telegram iweze kusikiliza commands zako
    Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()
    asyncio.run(main_listener())
