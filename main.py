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
    user = Keypair.from_bytes(base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY')))
    print(f"✅ Wallet Connected: {user.pubkey()}")
except Exception as e:
    print(f"❌ Wallet Error: {e}"); exit(1)

# ---------- SETTINGS ----------
AMOUNT_SOL = 0.03
MAX_SLIPPAGE = 1500  
PRIORITY_FEE = 150000 
MIN_LIQ_USD = 10000  

def tg(m):
    try: bot.send_message(CHAT_ID, m, parse_mode='Markdown', disable_web_page_preview=False)
    except: pass

@bot.message_handler(commands=['balance'])
def check_balance(message):
    async def get_bal():
        try:
            bal = await solana.get_balance(user.pubkey())
            amount = bal.value / 1e9
            bot.reply_to(message, f"💰 **Wallet Balance:** `{amount:.4f} SOL`")
        except: bot.reply_to(message, "❌ Connection Busy, jaribu tena.")
    asyncio.run(get_bal())

@bot.message_handler(commands=['status'])
def status(message):
    bot.reply_to(message, "🚀 **ALPHA-SNIPER v4.6** is Active and Scanning...")

# ---------- SMART FILTERS ----------

async def is_high_quality(mint):
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary", timeout=5) as r:
                data = await r.json()
                if data.get("score", 1000) > 400: return False 
                if data.get("tokenMeta", {}).get("mutable", True): return False 
            return True
        except: return False

# ---------- TRADING ENGINE ----------

async def swap(in_m, out_m, amt, action="Trade"):
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
            tg(f"🔔 **{action} Executed!**\nTransaction: [View on Solscan]({link})")
            return {"sig": sig, "amt": float(q["outAmount"])}
        except: return None

# ---------- MONITORING ENGINE ----------

class SmartEngine:
    def __init__(self, mint, buy_p, total_tokens):
        self.mint = mint
        self.buy_p = buy_p
        self.rem = total_tokens
        self.high = buy_p
        self.targets = [0.25, 0.50, 0.75, 1.00] 

    async def get_price(self):
        async with aiohttp.ClientSession() as s:
            try:
                async with s.get(f"https://api.jup.ag/price/v2?ids={self.mint}") as r:
                    d = await r.json()
                return float(d["data"][self.mint]["price"])
            except: return 0

    async def monitor(self):
        tg(f"🎯 **Target Locked!** Monitoring `{self.mint[:8]}`")
        while self.rem > 0:
            try:
                curr = await self.get_price()
                if curr == 0: await asyncio.sleep(10); continue
                
                profit = (curr - self.buy_p) / self.buy_p
                if curr > self.high: self.high = curr 

                # Whale Protection & Take Profit
                if curr < self.high * 0.85:
                    await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem, "TRAILING EXIT")
                    break

                for t in self.targets[:]:
                    if profit >= t:
                        sell_pct = 0.25 if t < 1.00 else 1.0 
                        if await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem * sell_pct, f"TP {int(t*100)}%"):
                            self.rem -= (self.rem * sell_pct)
                        self.targets.remove(t)

                if profit <= -0.20:
                    await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem, "STOP LOSS")
                    break
                await asyncio.sleep(10)
            except: await asyncio.sleep(20)

# ---------- SNIPER LISTENER ----------

async def main_listener():
    RAYDIUM = "675kPX9MHTjS2zt1qf1NYzt2i64ZEv3M96GvLpSaVYn"
    while True: # loop ya ku-reconnect ikikatika
        try:
            async with websockets.connect(WSS_URL, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"logsSubscribe","params":[{"mentions":[RAYDIUM]},{"commitment":"processed"}]}))
                print("🚀 Sniper Listening..."); tg("🚀 **SNIPER ACTIVE**")

                while True:
                    msg = json.loads(await ws.recv())
                    logs = msg.get("params", {}).get("result", {}).get("value", {}).get("logs", [])
                    for l in logs:
                        if "initialize2" in l.lower():
                            match = re.search(r'([1-9A-HJ-NP-Za-km-z]{32,44})', l)
                            if match:
                                mint = match.group(1)
                                if mint == RAYDIUM: continue
                                if await is_high_quality(mint):
                                    buy = await swap("So11111111111111111111111111111111111111112", mint, AMOUNT_SOL*1e9, "BUY")
                                    if buy:
                                        p = await SmartEngine(mint, 0, 0).get_price()
                                        asyncio.create_task(SmartEngine(mint, p, buy["amt"]).monitor())
        except Exception as e:
            print(f"Reconnect in 5s: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try: bot.remove_webhook()
    except: pass
    
    Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main_listener())
