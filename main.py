import asyncio, os, json, base58, aiohttp, websockets, re, threading
from datetime import datetime
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from dotenv import load_dotenv
import telebot

# ================== LOAD ENV ==================
load_dotenv()

RPC_URL = os.getenv("RPC_URL")
WSS_URL = os.getenv("WSS_URL")
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PRIVATE_KEY = os.getenv("SOLANA_PRIVATE_KEY")

bot = telebot.TeleBot(TOKEN)
solana = AsyncClient(RPC_URL)
user = Keypair.from_bytes(base58.b58decode(PRIVATE_KEY))

# ================== GLOBAL STATE ==================
BOT_ACTIVE = True
BUY_AMOUNT_SOL = 0.03
MIN_LIQ = 5000
PRIORITY_FEE = 500_000

STATS = {
    "trades": 0,
    "wins": 0,
    "losses": 0,
    "pnl_usd": 0.0
}

BLACKLIST = set()
tokens_scanned = 0

# ================== TELEGRAM ==================
def tg(msg):
    try:
        bot.send_message(CHAT_ID, msg, parse_mode="Markdown")
    except:
        pass

@bot.message_handler(commands=["on","off","status","pnl","stats","help"])
def commands(msg):
    global BOT_ACTIVE
    if str(msg.chat.id) != CHAT_ID:
        return

    if msg.text == "/on":
        BOT_ACTIVE = True
        tg("🟢 *Bot Enabled*")

    elif msg.text == "/off":
        BOT_ACTIVE = False
        tg("🔴 *Bot Disabled*")

    elif msg.text == "/status":
        bal = asyncio.run(solana.get_balance(user.pubkey()))
        tg(f"🤖 Status: {'ON' if BOT_ACTIVE else 'OFF'}\n💰 Balance: `{bal.value/1e9:.4f} SOL`")

    elif msg.text == "/pnl":
        tg(f"📊 PnL: `${STATS['pnl_usd']:.2f}`\nTrades: {STATS['trades']}")

    elif msg.text == "/stats":
        wr = (STATS["wins"]/STATS["trades"]*100) if STATS["trades"] else 0
        tg(f"📈 Trades: {STATS['trades']}\n✅ Wins: {STATS['wins']}\n❌ Losses: {STATS['losses']}\n🎯 Winrate: {wr:.1f}%")

    elif msg.text == "/help":
        tg("/on /off /status /pnl /stats")

# ================== MARKET DATA ==================
async def get_dex_data(mint):
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=6) as r:
                d = await r.json()
                if not d.get("pairs"): return None
                p = d["pairs"][0]
                return {
                    "symbol": p["baseToken"]["symbol"],
                    "liq": float(p["liquidity"]["usd"]),
                    "price": float(p["priceUsd"])
                }
        except:
            return None

# ================== SWAP ==================
async def swap(mint, side="BUY", amount=0):
    IN = "So11111111111111111111111111111111111111112"
    input_mint = IN if side == "BUY" else mint
    output_mint = mint if side == "BUY" else IN
    amt = int(BUY_AMOUNT_SOL*1e9) if side=="BUY" else int(amount)

    async with aiohttp.ClientSession() as s:
        try:
            q = await (await s.get(
                f"https://quote-api.jup.ag/v6/quote?inputMint={input_mint}&outputMint={output_mint}&amount={amt}&slippageBps=1500"
            )).json()

            p = {
                "quoteResponse": q,
                "userPublicKey": str(user.pubkey()),
                "prioritizationFeeLamports": PRIORITY_FEE
            }

            sw = await (await s.post("https://quote-api.jup.ag/v6/swap", json=p)).json()
            tx = VersionedTransaction.from_bytes(base58.b58decode(sw["swapTransaction"]))
            signed = VersionedTransaction(tx.message, [user.sign_message(tx.message)])
            sig = await solana.send_raw_transaction(bytes(signed))
            return {"sig": str(sig.value), "tokens": q["outAmount"]}
        except:
            return None

# ================== POSITION MONITOR ==================
async def monitor_position(mint, buy_price, tokens, symbol):
    floor = buy_price * 0.85
    tg(f"🛡️ Monitoring `{symbol}`")

    while True:
        data = await get_dex_data(mint)
        if not data:
            await asyncio.sleep(15)
            continue

        price = data["price"]
        profit = (price - buy_price) / buy_price

        if profit >= 1.20:
            floor = max(floor, buy_price * 1.75)
        elif profit >= 0.70:
            floor = max(floor, buy_price * 1.50)
        elif profit >= 0.40:
            floor = max(floor, buy_price * 1.25)

        if price <= floor:
            await swap(mint, "SELL", tokens)

            pnl = profit * BUY_AMOUNT_SOL * 150
            STATS["trades"] += 1
            STATS["pnl_usd"] += pnl

            if profit > 0:
                STATS["wins"] += 1
            else:
                STATS["losses"] += 1

            tg(f"🎯 EXIT `{symbol}`\nProfit: `{int(profit*100)}%`")
            break

        await asyncio.sleep(15)

# ================== SCANNER ==================
async def scan_report():
    global tokens_scanned
    while True:
        await asyncio.sleep(900)
        bal = await solana.get_balance(user.pubkey())
        tg(f"🔍 Scan Report\nTokens: `{tokens_scanned}`\nBalance: `{bal.value/1e9:.4f} SOL`")
        tokens_scanned = 0

async def main():
    global tokens_scanned
    RAYDIUM = "675kPX9MHTjS2zt1qf1NYzt2i64ZEv3M96GvLpSaVYn"

    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    asyncio.create_task(scan_report())

    tg("🚀 *ALPHA-SNIPER LIVE*")

    async with websockets.connect(WSS_URL, ping_interval=20) as ws:
        await ws.send(json.dumps({
            "jsonrpc":"2.0",
            "id":1,
            "method":"logsSubscribe",
            "params":[{"mentions":[RAYDIUM]},{"commitment":"processed"}]
        }))

        async for msg in ws:
            if not BOT_ACTIVE:
                await asyncio.sleep(5)
                continue

            logs = json.loads(msg).get("params",{}).get("result",{}).get("value",{}).get("logs",[])
            for log in logs:
                if "initialize2" in log.lower():
                    mints = re.findall(r'([1-9A-HJ-NP-Za-km-z]{32,44})', log)
                    for m in mints:
                        if m in BLACKLIST or len(m) < 40:
                            continue

                        tokens_scanned += 1
                        info = await get_dex_data(m)
                        if info and info["liq"] >= MIN_LIQ:
                            tg(f"💎 `{info['symbol']}` Liq ${info['liq']:,.0f}")
                            buy = await swap(m, "BUY")
                            if buy:
                                asyncio.create_task(
                                    monitor_position(m, info["price"], buy["tokens"], info["symbol"])
                                )

if __name__ == "__main__":
    asyncio.run(main())
