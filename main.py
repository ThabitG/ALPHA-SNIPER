import asyncio, os, json, base58, aiohttp, websockets, re
from datetime import datetime
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from dotenv import load_dotenv
import telebot

load_dotenv()

# --- CONFIG ---
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
RPC_URL = os.getenv('RPC_URL')
WSS_URL = os.getenv('WSS_URL')
bot = telebot.TeleBot(TOKEN)
solana = AsyncClient(RPC_URL)
user = Keypair.from_bytes(base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY')))

# --- SETTINGS ---
BUY_AMOUNT_SOL = 0.03
MIN_LIQ = 5000
PRIORITY_FEE = 400000 

def tg(m):
    try: bot.send_message(CHAT_ID, m, parse_mode='Markdown')
    except: pass

async def get_dex_data(mint):
    """Inapata Jina, Symbol, Liquidity na Bei kwa mpigo mmoja"""
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=5) as r:
                data = await r.json()
                pair = data['pairs'][0]
                return {
                    "name": pair['baseToken']['name'],
                    "symbol": pair['baseToken']['symbol'],
                    "liq": float(pair['liquidity']['usd']),
                    "price": float(pair['priceUsd'])
                }
        except: return None

async def swap(mint, action="BUY", amount=0):
    """Jupiter V6 Swap Engine - Professional Speed"""
    in_m = "So11111111111111111111111111111111111111112" if action == "BUY" else mint
    out_m = mint if action == "BUY" else "So11111111111111111111111111111111111111112"
    amt_lamports = int(BUY_AMOUNT_SOL * 1e9) if action == "BUY" else int(amount)

    async with aiohttp.ClientSession() as s:
        try:
            q_url = f"https://quote-api.jup.ag/v6/quote?inputMint={in_m}&outputMint={out_m}&amount={amt_lamports}&slippageBps=1500"
            async with s.get(q_url) as r: q = await r.json()
            p = {"quoteResponse": q, "userPublicKey": str(user.pubkey()), "prioritizationFeeLamports": PRIORITY_FEE}
            async with s.post("https://quote-api.jup.ag/v6/swap", json=p) as r: sw = await r.json()
            tx = VersionedTransaction.from_bytes(base58.b58decode(sw["swapTransaction"]))
            signed = VersionedTransaction(tx.message, [user.sign_message(tx.message)])
            res = await solana.send_raw_transaction(bytes(signed))
            return {"sig": str(res.value), "tokens": q["outAmount"]}
        except: return None

async def monitor_blocks(mint, buy_price, tokens, symbol):
    """Kipengere cha Dynamic Block System (40%->25%, 70%->50%, n.k.)"""
    # Block ya kwanza ni Stop Loss ya -15%
    floor = buy_price * 0.85 
    tg(f"🛡️ **Monitoring {symbol}**\nInitial Stop-Loss: -15%")
    
    while True:
        try:
            data = await get_dex_data(mint)
            if not data: await asyncio.sleep(10); continue
            
            curr_p = data['price']
            profit = (curr_p - buy_price) / buy_price
            
            # --- Logic ya Kufunga "Blocks" ---
            new_floor = floor
            if profit >= 1.20: new_floor = buy_price * 1.75 # Lock faida ya 75%
            elif profit >= 0.70: new_floor = buy_price * 1.50 # Lock faida ya 50%
            elif profit >= 0.40: new_floor = buy_price * 1.25 # Lock faida ya 25%
            
            if new_floor > floor:
                floor = new_floor
                tg(f"🔒 **Block Locked!** {symbol} sasa iko salama kwenye block ya +{int((floor/buy_price - 1)*100)}%")

            # --- EXIT: Ikishuka na kugusa Floor ---
            if curr_p <= floor:
                tg(f"🚨 **Block Hit!** Bei imegusa block ya {symbol}. Inauza sasa...")
                res = await swap(mint, "SELL", tokens)
                if res:
                    tg(f"🔴 **SELL DONE!** Captured ~{int(profit*100)}% profit.")
                    break
            await asyncio.sleep(15)
        except: await asyncio.sleep(10)

async def hourly_report():
    """Notification ya kila saa"""
    while True:
        await asyncio.sleep(3600)
        tg("🟢 **System Live:** Sniper is scanning and monitoring blocks.")

async def main():
    RAYDIUM = "675kPX9MHTjS2zt1qf1NYzt2i64ZEv3M96GvLpSaVYn"
    asyncio.create_task(hourly_report())
    tg("🚀 **SNIPER CORE ONLINE**\nDynamic Block System: *Active*")

    async with websockets.connect(WSS_URL, ping_interval=20) as ws:
        await ws.send(json.dumps({"jsonrpc":"2.0","id":1,"method":"logsSubscribe","params":[{"mentions":[RAYDIUM]},{"commitment":"processed"}]}))
        
        async for msg in ws:
            data = json.loads(msg)
            logs = data.get("params", {}).get("result", {}).get("value", {}).get("logs", [])
            for log in logs:
                if "initialize2" in log.lower():
                    mints = re.findall(r'([1-9A-HJ-NP-Za-km-z]{32,44})', log)
                    for m in mints:
                        if m == RAYDIUM or len(m) < 40: continue
                        
                        # Angalia liquidity na maelezo ya token
                        info = await get_dex_data(m)
                        if info and info['liq'] >= MIN_LIQ:
                            tg(f"💎 **Gem Found:** {info['name']} (${info['symbol']})\nLiquidity: ${info['liq']:,.0f}")
                            buy = await swap(m, "BUY")
                            if buy:
                                tg(f"✅ **Bought!** {info['symbol']}\nTX: `{buy['sig'][:10]}...`")
                                asyncio.create_task(monitor_blocks(m, info['price'], buy['tokens'], info['symbol']))

if __name__ == "__main__":
    asyncio.run(main())
