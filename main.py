import asyncio, os, json, base58, aiohttp, websockets, re, threading
from datetime import datetime
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient

# ================== VARIABLES (DIRECT LINK - FIXED) ==================
TELEGRAM_TOKEN = "8333756822:AAG7RatQLr29OtIiPBURFMZdFTD7Gk6WEC0"
CHAT_ID = "2101969412"
RPC_URL = "https://mainnet.helius-rpc.com/?api-key=ce083377-f005-464a-9d07-91188b868229"
WSS_URL = "wss://mainnet.helius-rpc.com/?api-key=ce083377-f005-464a-9d07-91188b868229"
PRIVATE_KEY = "3tDP4iffWTi7s929ULM7JxMFK2Ha2HsiF7YrhYt9HrUgdfx6EW9ZupK2TD6B87XSx5joZx4y3YxyuogSkrj2JvXz"

# ================== INITIALIZATION ==================
solana = AsyncClient(RPC_URL)
user = Keypair.from_bytes(base58.b58decode(PRIVATE_KEY))
BOT_ACTIVE = True
BUY_AMOUNT_SOL = 0.03
MIN_LIQ = 5000
PRIORITY_FEE = 500_000
BLACKLIST = set()

async def tg_send(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as s:
        try:
            await s.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=5)
        except: pass

async def get_dex_data(mint):
    async with aiohttp.ClientSession() as s:
        try:
            async with s.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=6) as r:
                d = await r.json()
                if not d.get("pairs"): return None
                p = d["pairs"][0]
                liq = float(p["liquidity"]["usd"])
                if liq < MIN_LIQ: return None
                return {"symbol": p["baseToken"]["symbol"], "liq": liq, "price": float(p["priceUsd"])}
        except: return None

async def swap(mint, side="BUY", amount=0):
    SOL_MINT = "So11111111111111111111111111111111111111112"
    input_mint = SOL_MINT if side == "BUY" else mint
    output_mint = mint if side == "BUY" else SOL_MINT
    amt = int(BUY_AMOUNT_SOL * 1e9) if side == "BUY" else int(amount)
    async with aiohttp.ClientSession() as s:
        try:
            q_url = f"https://quote-api.jup.ag/v6/quote?inputMint={input_mint}&outputMint={output_mint}&amount={amt}&slippageBps=1500"
            async with s.get(q_url) as r: q = await r.json()
            p = {"quoteResponse": q, "userPublicKey": str(user.pubkey()), "prioritizationFeeLamports": PRIORITY_FEE}
            async with s.post("https://quote-api.jup.ag/v6/swap", json=p) as r: sw = await r.json()
            tx = VersionedTransaction.from_bytes(base58.b58decode(sw["swapTransaction"]))
            signed_tx = VersionedTransaction(tx.message, [user.sign_message(tx.message)])
            res = await solana.send_raw_transaction(bytes(signed_tx))
            return {"sig": str(res.value), "tokens": q["outAmount"]}
        except: return None

async def monitor_position(mint, buy_price, tokens, symbol):
    floor = buy_price * 0.85
    await tg_send(f"🛡️ *Monitoring* `{symbol}`")
    while True:
        data = await get_dex_data(mint)
        if not data:
            await asyncio.sleep(20)
            continue
        price = data["price"]
        profit = (price - buy_price) / buy_price
        if profit >= 1.00: floor = max(floor, buy_price * 1.50)
        elif profit >= 0.50: floor = max(floor, buy_price * 1.20)
        if price <= floor:
            sell = await swap(mint, "SELL", tokens)
            if sell:
                await tg_send(f"🎯 *EXIT {symbol}*\nProfit: `{profit*100:.1f}%`")
                break
        await asyncio.sleep(20)

async def main():
    RAYDIUM_LP_V4 = "675kPX9MHTjS2zt1qf1NYzt2i64ZEv3M96GvLpSaVYn"
    await tg_send("🚀 *ALPHA-SNIPER SOLANA LIVE*")
    async with websockets.connect(WSS_URL) as ws:
        await ws.send(json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
            "params": [{"mentions": [RAYDIUM_LP_V4]}, {"commitment": "processed"}]
        }))
        async for msg in ws:
            data = json.loads(msg)
            logs = data.get("params", {}).get("result", {}).get("value", {}).get("logs", [])
            for log in logs:
                if "initialize2" in log.lower():
                    mints = re.findall(r'([1-9A-HJ-NP-Za-km-z]{32,44})', log)
                    for m in mints:
                        if len(m) >= 40 and m not in BLACKLIST:
                            info = await get_dex_data(m)
                            if info:
                                await tg_send(f"💎 *New Coin:* `{info['symbol']}`\nLiq: `${info['liq']:,.0f}`")
                                res = await swap(m, "BUY")
                                if res: asyncio.create_task(monitor_position(m, info["price"], res["tokens"], info["symbol"]))

if __name__ == "__main__":
    asyncio.run(main())
