import asyncio, os, json, base58, aiohttp, websockets, re, time
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
solana_client = AsyncClient(RPC_URL)

try:
    user = Keypair.from_bytes(base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY')))
    print(f"✅ Wallet Connected: {user.pubkey()}")
except Exception as e:
    print(f"❌ Wallet Error: {e}"); exit(1)

# ---------- SETTINGS ----------
AMOUNT_SOL = 0.03
MIN_LIQUIDITY_USD = 5000  #
MAX_SLIPPAGE = 1500  
PRIORITY_FEE = 300000     # Higher priority for faster exits

def tg(m):
    try: bot.send_message(CHAT_ID, m, parse_mode='Markdown', disable_web_page_preview=True)
    except: pass

# ---------- UTILS & NOTIFICATIONS ----------

async def get_token_data(mint):
    """Inapata jina, symbol na liquidity ya coin"""
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=5) as r:
                data = await r.json()
                pair = data['pairs'][0]
                return {
                    "name": pair['baseToken']['name'],
                    "symbol": pair['baseToken']['symbol'],
                    "liq": float(pair['liquidity']['usd'])
                }
        except: return None

async def hourly_heartbeat():
    """Notification ya kila saa moja"""
    while True:
        await asyncio.sleep(3600)
        now = datetime.now().strftime("%H:%M")
        tg(f"⏰ **Hourly Status ({now})**\n🟢 Sniper is Active & Scanning. Systems Green.")

# ---------- SMART ENGINE (THE BLOCK SYSTEM) ----------

class SmartEngine:
    def __init__(self, mint, name, symbol, buy_p, total_tokens):
        self.mint = mint
        self.name = name
        self.symbol = symbol
        self.buy_p = buy_p
        self.rem = total_tokens
        self.floor = buy_p * 0.85 # Initial Stop Loss (-15%)

    async def get_price(self):
        async with aiohttp.ClientSession() as s:
            try:
                async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{self.mint}") as r:
                    d = await r.json()
                    return float(d["pairs"][0]["priceUsd"])
            except: return 0

    async def monitor(self):
        tg(f"🛡️ **Dynamic Ladder Active!** Monitoring {self.name} (${self.symbol})")
        while self.rem > 0:
            try:
                curr = await self.get_price()
                if curr <= 0: await asyncio.sleep(5); continue
                
                profit = (curr - self.buy_p) / self.buy_p
                
                # --- MFUMO WA BLOCK (Sakafu ya Kupanda) ---
                # 1. Faida 40% -> Lock Block 25%
                if profit >= 0.40 and self.floor < (self.buy_p * 1.25):
                    self.floor = self.buy_p * 1.25
                    tg(f"🔒 **Block Locked @ +25%** for {self.symbol}\n(Current: +{int(profit*100)}%)")
                
                # 2. Faida 70% -> Lock Block 50%
                elif profit >= 0.70 and self.floor < (self.buy_p * 1.50):
                    self.floor = self.buy_p * 1.50
                    tg(f"🔒 **Block Locked @ +50%** for {self.symbol}")

                # 3. Faida 120% -> Lock Block 75%
                elif profit >= 1.20 and self.floor < (self.buy_p * 1.75):
                    self.floor = self.buy_p * 1.75
                    tg(f"🔒 **Block Locked @ +75%** - Moonshot! 🚀")

                # 4. Moonshot Scaling (e.g. 1000% target)
                elif profit > 2.0:
                    # Sogeza floor iwe 20% chini ya bei ya sasa kila inapopanda zaidi
                    new_floor = curr * 0.80
                    if new_floor > self.floor:
                        self.floor = new_floor

                # --- EMERGENCY EXIT (Piga Sell ghafla) ---
                if curr <= self.floor:
                    await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem, f"SELL {self.symbol}")
                    tg(f"🔴 **EXIT EXECUTED!**\nCoin: {self.name}\nCaptured: ~{int(profit*100)}% profit.")
                    break

                await asyncio.sleep(5)
            except: await asyncio.sleep(10)

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
            res = await solana_client.send_raw_transaction(bytes(signed))
            
            sig = str(res.value)
            tg(f"📑 **{action} Success!**\n[View on Solscan](https://solscan.io/tx/{sig})")
            
            # Pata bei ya makadirio ya USD
            price = 0
            if "BUY" in action:
                async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{out_m}") as r:
                    d = await r.json()
                    price = float(d['pairs'][0]['priceUsd'])
            
            return {"sig": sig, "amt": float(q["outAmount"]), "price": price}
        except: return None

# ---------- SNIPER LISTENER ----------

async def main_listener():
    RAYDIUM = "675kPX9MHTjS2zt1qf1NYzt2i64ZEv3M96GvLpSaVYn"
    asyncio.create_task(hourly_heartbeat())
    
    while True:
        try:
            async with websockets.connect(WSS_URL, ping_interval=20) as ws:
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
                                
                                data = await get_token_data(mint)
                                if data and data['liq'] >= MIN_LIQUIDITY_USD:
                                    tg(f"🔍 **New Gem:** {data['name']} (${data['symbol']})\nLiq: ${data['liq']:.0f}")
                                    
                                    # RugCheck Score (Optional)
                                    buy = await swap("So11111111111111111111111111111111111111112", mint, AMOUNT_SOL*1e9, f"BUY {data['symbol']}")
                                    if buy:
                                        asyncio.create_task(SmartEngine(mint, data['name'], data['symbol'], buy["price"], buy["amt"]).monitor())
        except: await asyncio.sleep(2)

if __name__ == "__main__":
    # Start Telegram in Thread
    Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()
    # Start Sniper
    asyncio.run(main_listener())
