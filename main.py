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
    # Ku-decode Solana Private Key kutoka Base58
    user = Keypair.from_bytes(base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY')))
    print(f"✅ Wallet Connected: {user.pubkey()}")
except Exception as e:
    print(f"❌ Wallet Error: {e}"); exit(1)

# ---------- SETTINGS ----------
# Hizi ndizo parameters za biashara yako
AMOUNT_SOL = 0.03
MAX_SLIPPAGE = 1500  # 15% Slippage kwa soko la kasi
PRIORITY_FEE = 150000 # Kwa ajili ya Helius Paid RPC
MIN_LIQ_USD = 10000  # Usinunue token yenye liquidity chini ya $10k

def tg(m):
    """Notification system ya Telegram"""
    try: bot.send_message(CHAT_ID, m, parse_mode='Markdown', disable_web_page_preview=False)
    except: pass

# ---------- TELEGRAM COMMANDS ----------

@bot.message_handler(commands=['balance'])
def check_balance(message):
    """Amri ya kuona salio la SOL"""
    async def get_bal():
        bal = await solana.get_balance(user.pubkey())
        amount = bal.value / 1e9
        bot.reply_to(message, f"💰 **Wallet Balance:** `{amount:.4f} SOL`")
    asyncio.run(get_bal())

@bot.message_handler(commands=['status'])
def status(message):
    bot.reply_to(message, "🚀 **ALPHA-SNIPER v4.5** is Active and Scanning...")

# ---------- SMART FILTERS (RugCheck & Momentum) ----------

async def is_high_quality(mint):
    """Inakata Rug Pulls na Low Volume tokens"""
    async with aiohttp.ClientSession() as s:
        try:
            # 1. RugCheck (Token Security)
            async with s.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary") as r:
                data = await r.json()
                if data.get("score", 1000) > 400: return False 
                if data.get("tokenMeta", {}).get("mutable", True): return False 

            # 2. DexScreener (Market Momentum)
            async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}") as r:
                dex = await r.json()
                pairs = dex.get("pairs", [])
                if not pairs: return False
                pair = pairs[0]
                if float(pair.get("liquidity", {}).get("usd", 0)) < MIN_LIQ_USD: return False
                
            return True
        except: return False

# ---------- TRADING ENGINE (Jupiter V6) ----------

async def swap(in_m, out_m, amt, action="Trade"):
    """Execution ya kununua na kuuza kupitia Jupiter"""
    async with aiohttp.ClientSession() as s:
        try:
            q_url = f"https://quote-api.jup.ag/v6/quote?inputMint={in_m}&outputMint={out_m}&amount={int(amt)}&slippageBps={MAX_SLIPPAGE}"
            async with s.get(q_url) as r: q = await r.json()
            
            p = {"quoteResponse": q, "userPublicKey": str(user.pubkey()), "wrapAndUnwrapSol": True, "prioritizationFeeLamports": PRIORITY_FEE}
            async with s.post("https://quote-api.jup.ag/v6/swap", json=p) as r: sw = await r.json()
            
            raw = base58.b58decode(sw["swapTransaction"])
            tx = VersionedTransaction.from_bytes(raw)
            signed = VersionedTransaction(tx.message, [user.sign_message(tx.message)])
            res = await solana.send_raw_transaction(bytes(signed))
            
            sig = str(res.value)
            link = f"https://solscan.io/tx/{sig}"
            tg(f"🔔 **{action} Executed!**\n\nToken: `{out_m if action=='BUY' else in_m}`\nTransaction: [View on Solscan]({link})")
            return {"sig": sig, "amt": float(q["outAmount"])}
        except Exception as e:
            print(f"Swap Error: {e}"); return None

# ---------- SCALED TAKE PROFIT & WHALE RADAR ----------

class SmartEngine:
    """Logic ya kulinda faida hatua kwa hatua"""
    def __init__(self, mint, buy_p, total_tokens):
        self.mint = mint
        self.buy_p = buy_p
        self.rem = total_tokens
        self.high = buy_p
        # Targets zako: 25%, 50%, 75%, 100%
        self.targets = [0.25, 0.50, 0.75, 1.00] 

    async def get_price(self):
        async with aiohttp.ClientSession() as s:
            try:
                async with s.get(f"https://api.jup.ag/price/v2?ids={self.mint}") as r:
                    d = await r.json()
                return float(d["data"][self.mint]["price"])
            except: return 0

    async def monitor(self):
        tg(f"🎯 **Target Locked!** Monitoring `{self.mint[:8]}...` for profits: 25%, 50%, 75%, 100%")
        while self.rem > 0:
            try:
                curr = await self.get_price()
                if curr == 0: await asyncio.sleep(5); continue
                
                profit = (curr - self.buy_p) / self.buy_p
                if curr > self.high: self.high = curr 

                # 1. WHALE DUMP PROTECTION (Trailing Stop 15%)
                # Kama bei ikishuka kwa 15% kutoka kilele (High), uza zote.
                if curr < self.high * 0.85:
                    await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem, "TRAILING EXIT")
                    break

                # 2. SCALED TAKE PROFIT LOGIC
                for t in self.targets[:]:
                    if profit >= t:
                        # Uza robo ya ulichonacho (25%) kwa kila target, isipokuwa ya mwisho
                        sell_pct = 0.25 if t < 1.00 else 1.0 
                        sell_amt = self.rem * sell_pct
                        
                        if await swap(self.mint, "So11111111111111111111111111111111111111112", sell_amt, f"TP {int(t*100)}% HIT"):
                            self.rem -= sell_amt
                            tg(f"💰 **TP {int(t*100)}% Hit!** Sold part of the bag.")
                        self.targets.remove(t)

                # 3. STOP LOSS (20%)
                if profit <= -0.20:
                    await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem, "STOP LOSS")
                    break

                await asyncio.sleep(5)
            except: await asyncio.sleep(10)

# ---------- MEV-STYLE LISTENER ----------

async def main_listener():
    RAYDIUM = "675kPX9MHTjS2zt1qf1NYzt2i64ZEv3M96GvLpSaVYn"
    async with websockets.connect(WSS_URL) as ws:
        # Subscribe kwenye Raydium logs
        await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"logsSubscribe","params":[{"mentions":[RAYDIUM]},{"commitment":"processed"}]}))
        print("🚀 Sniper is listening to Helius Stream..."); tg("🚀 **ALPHA-SNIPER v4.5 ACTIVE**\nUsing Helius Paid RPC")

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
                            
                            # Filter kabla ya kununua
                            if await is_high_quality(mint):
                                buy = await swap("So11111111111111111111111111111111111111112", mint, AMOUNT_SOL*1e9, "BUY")
                                if buy:
                                    price = await SmartEngine(mint, 0, 0).get_price()
                                    engine = SmartEngine(mint, price, buy["amt"])
                                    asyncio.create_task(engine.monitor())
            except: continue

# ---------- STARTUP ----------

if __name__ == "__main__":
    # Safisha webhook kuzuia Conflict 409
    try: bot.remove_webhook()
    except: pass
    
    # Washa Telegram Polling (Thread-safe)
    Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()
    
    try:
        asyncio.run(main_listener())
    except KeyboardInterrupt:
        print("🛑 Stopped.")
