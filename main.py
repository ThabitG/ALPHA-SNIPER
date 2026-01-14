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
MIN_LIQUIDITY_USD = 10000  # Bot itanunua tu kama pool ina zaidi ya $10,000
MAX_SLIPPAGE = 1500  
PRIORITY_FEE = 300000 

def tg(m):
    try: bot.send_message(CHAT_ID, m, parse_mode='Markdown')
    except: pass

# ---------- SMART FILTERS (Liquidity & RugCheck) ----------

async def passes_filters(mint):
    async with aiohttp.ClientSession() as s:
        try:
            # 1. RugCheck Summary
            async with s.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary", timeout=5) as r:
                rug_data = await r.json()
                if rug_data.get("score", 1000) > 600: return False

            # 2. Check Liquidity via Dexscreener
            async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=5) as r:
                dex_data = await r.json()
                pairs = dex_data.get("pairs", [])
                if not pairs: return False
                
                liq = float(pairs[0].get("liquidity", {}).get("usd", 0))
                if liq < MIN_LIQUIDITY_USD:
                    print(f"⚠️ Skip: Liquidity ${liq} is too low.")
                    return False
                return True
        except: return False

# ---------- MONITORING ENGINE (Trailing Block Ladder) ----------

class SmartEngine:
    def __init__(self, mint, buy_price, total_tokens):
        self.mint = mint
        self.buy_p = buy_price
        self.rem = total_tokens
        self.high = buy_price
        self.floor = buy_price * 0.80  # Stop Loss ya kuanzia (-20%)

    async def get_price(self):
        async with aiohttp.ClientSession() as s:
            try:
                async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{self.mint}") as r:
                    d = await r.json()
                    return float(d["pairs"][0]["priceUsd"])
            except: return 0

    async def monitor(self):
        tg(f"🛡️ **Dynamic Ladder Active!** Monitoring `{self.mint[:8]}`")
        while self.rem > 0:
            try:
                curr = await self.get_price()
                if curr <= 0: await asyncio.sleep(3); continue
                
                profit = (curr - self.buy_p) / self.buy_p
                if curr > self.high: self.high = curr 

                # --- MFUMO WA BLOCK (Your Idea) ---
                # Ikifika +40%, weka sakafu (block) ya +25%
                if profit >= 0.40 and self.floor < (self.buy_p * 1.25):
                    self.floor = self.buy_p * 1.25
                    tg(f"🔒 **Block Locked: +25%** (Current: +{int(profit*100)}%)")

                # Ikifika +70%, weka sakafu (block) ya +50%
                elif profit >= 0.70 and self.floor < (self.buy_p * 1.50):
                    self.floor = self.buy_p * 1.50
                    tg(f"🔒 **Block Locked: +50%** (Current: +{int(profit*100)}%)")

                # Ikifika +120%, weka sakafu (block) ya +75%
                elif profit >= 1.20 and self.floor < (self.buy_p * 1.75):
                    self.floor = self.buy_p * 1.75
                    tg(f"🔒 **Block Locked: +75%** - Moon mission! 🚀")

                # --- EMERGENCY EXIT ---
                # Ikishuka na kugusa block/sakafu yetu, uza kila kitu!
                if curr <= self.floor:
                    await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem, "BLOCK/SL HIT")
                    break
                
                # Trailing ya faida kubwa (Moonshot protection)
                if profit > 2.0 and curr < self.high * 0.80:
                    await swap(self.mint, "So11111111111111111111111111111111111111112", self.rem, "TRAILING MOON EXIT")
                    break

                await asyncio.sleep(5)
            except: await asyncio.sleep(5)

# ---------- TRADING & LISTENER (The Core) ----------
# [Code ya swap na main_listener inaendelea hapa kama kodi mama]
# Tumeongeza kigezo cha `if await passes_filters(mint):` kabla ya kununua.
