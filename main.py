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
solana = AsyncClient(RPC_URL)

try:
    # Tunatumia from_bytes kuepuka error ya 'from_string'
    user = Keypair.from_bytes(base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY')))
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

async def get_token_name(mint):
    """Inatafuta jina la meme coin kupitia Dexscreener"""
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}") as r:
                data = await r.json()
                return data['pairs'][0]['baseToken']['name'], data['pairs'][0]['baseToken']['symbol']
        except: return "Unknown", "MEME"

# ---------- HOURLY NOTIFICATION ----------

async def hourly_heartbeat():
    """Inatuma ujumbe kila baada ya saa moja kuhakikisha bot iko online"""
    while True:
        now = datetime.now().strftime("%H:%M")
        tg(f"⏰ **Hourly Update ({now})**\n🟢 Bot is active and scanning for new gems...")
        await asyncio.sleep(3600) # Subiri sekunde 3600 (Saa 1)

# ---------- SMART ENGINE (Trailing Ladder) ----------

class SmartEngine:
    def __init__(self, mint, name, symbol, buy_price, total_tokens):
        self.mint = mint
        self.name = name
        self.symbol = symbol
        self.buy_p = buy_price
        self.rem = total_tokens
        self.high = buy_price
        self.floor = buy_price * 0.80 

    async def get_price(self):
        async with aiohttp.ClientSession() as s:
            try:
                async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{self.mint}") as r:
                    d = await r.json()
                    return float(d["pairs"][0]["priceUsd"])
            except: return 0

    async def monitor(self):
        while self.rem > 0:
            try:
                curr = await self.get_price()
                if curr <= 0: await asyncio.sleep(5); continue
                
                profit = (curr - self.buy_p) / self.buy_p if self.buy_p > 0 else 0
                if curr > self.high: self.high = curr 

                # Ladder Blocks
                if profit >= 0.40 and self.floor < (self.buy_p * 1.25):
                    self.floor = self.buy_p * 1.25
                    tg(f"🔒 **{self.symbol} Block Locked: +25%**")
                elif profit >= 0.70 and self.floor < (self.buy_p * 1.50):
                    self.floor = self.buy_p * 1.50
                    tg(f"🔒 **{self.symbol} Block Locked: +50%**")

                if curr <= self.floor:
                    await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem, f"SELL {self.symbol}")
                    tg(f"🔴 **SOLD {self.name} (${self.symbol})**\nProfit: {int(profit*100)}%\nPrice: ${curr}")
                    break
                await asyncio.sleep(10)
            except: await asyncio.sleep(10)

# ---------- SWAP ENGINE ----------

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
            tg(f"📑 **{action} Succesful!**\nTx: [Solscan](https://solscan.io/tx/{sig})")
            return {"sig": sig, "out": float(q["outAmount"])}
        except: return None

# ---------- LISTENER ----------

async def main_listener():
    RAYDIUM = "675kPX9MHTjS2zt1qf1NYzt2i64ZEv3M96GvLpSaVYn"
    # Anza saa ya kila lisaa
    asyncio.create_task(hourly_heartbeat())
    
    while True:
        try:
            async with websockets.connect(WSS_URL) as ws:
                await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"logsSubscribe","params":[{"mentions":[RAYDIUM]},{"commitment":"processed"}]}))
                print("🚀 Sniper Live..."); tg("🚀 **SNIPER ACTIVE & SCANNING**")
                
                while True:
                    msg = json.loads(await ws.recv())
                    logs = msg.get("params", {}).get("result", {}).get("value", {}).get("logs", [])
                    for l in logs:
                        if "initialize2" in l.lower():
                            mints = re.findall(r'([1-9A-HJ-NP-Za-km-z]{32,44})', l)
                            for mint in mints:
                                if mint == RAYDIUM or len(mint) < 40: continue
                                name, symbol = await get_token_name(mint)
                                tg(f"🔍 **New Coin Detected:** {name} (${symbol})\n`{mint}`")
                                
                                # Hapa unaweza kuongeza `if await passes_filters(mint):`
                                buy = await swap("So11111111111111111111111111111111111111112", mint, AMOUNT_SOL*1e9, f"BUY {symbol}")
                                if buy:
                                    # Pata bei ya USD ya kununulia
                                    async with aiohttp.ClientSession() as s:
                                        async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}") as r:
                                            d = await r.json()
                                            price = float(d["pairs"][0]["priceUsd"])
                                    asyncio.create_task(SmartEngine(mint, name, symbol, price, buy["out"]).monitor())
        except: await asyncio.sleep(5)

if __name__ == "__main__":
    Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()
    asyncio.run(main_listener())
