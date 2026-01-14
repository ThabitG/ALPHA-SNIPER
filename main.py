import asyncio, os, json, base58, aiohttp, websockets, re
from threading import Thread
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from dotenv import load_dotenv
import telebot

# ---------- SETUP & CONFIG ----------
load_dotenv()

# Hapa tunahakikisha Token haipo tupu (None) kuzuia kosa la 'NoneType'
TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TOKEN:
    print("❌ ERROR: TELEGRAM_TOKEN haijapatikana kwenye Environment Variables!")
    exit(1)

CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
bot = telebot.TeleBot(TOKEN)
solana = AsyncClient(os.getenv('RPC_URL'))
WSS_URL = os.getenv('WSS_URL')

# Kupakia Wallet
try:
    private_key_str = os.getenv('SOLANA_PRIVATE_KEY')
    if not private_key_str:
        raise ValueError("SOLANA_PRIVATE_KEY is missing!")
    user = Keypair.from_bytes(base58.b58decode(private_key_str))
    print(f"✅ Wallet Imechajiwa: {user.pubkey()}")
except Exception as e:
    print(f"❌ Wallet Error: {e}")
    exit(1)

# ---------- TRADING SETTINGS ----------
AMOUNT_SOL = 0.03
MAX_SLIPPAGE = 1500      # 15% slippage
PRIORITY_FEE = 100000    # MEV protection

def tg(m):
    """Function ya kutuma ripoti Telegram"""
    try: bot.send_message(CHAT_ID, m, parse_mode='Markdown')
    except Exception as e: print(f"TG Error: {e}")

# ---------- SWAP ENGINE (Jupiter V6) ----------

async def swap(in_mint, out_mint, amount):
    async with aiohttp.ClientSession() as session:
        try:
            # Pata nukuu (Quote) kutoka Jupiter
            quote_url = f"https://quote-api.jup.ag/v6/quote?inputMint={in_mint}&outputMint={out_mint}&amount={int(amount)}&slippageBps={MAX_SLIPPAGE}"
            async with session.get(quote_url) as resp:
                quote = await resp.json()
            
            # Tengeneza muamala (Swap Transaction)
            swap_data = {
                "quoteResponse": quote,
                "userPublicKey": str(user.pubkey()),
                "wrapAndUnwrapSol": True,
                "prioritizationFeeLamports": PRIORITY_FEE
            }
            async with session.post("https://quote-api.jup.ag/v6/swap", json=swap_data) as resp:
                tx_data = await resp.json()
            
            # Saini na tuma muamala
            raw_tx = base58.b58decode(tx_data["swapTransaction"])
            tx = VersionedTransaction.from_bytes(raw_tx)
            signed_tx = VersionedTransaction(tx.message, [user.sign_message(tx.message)])
            
            res = await solana.send_raw_transaction(bytes(signed_tx))
            return {"sig": str(res.value), "amt": float(quote["outAmount"])}
        except Exception as e:
            print(f"Swap Failed: {e}")
            return None

# ---------- LISTENER (New Pairs) ----------

async def main_listener():
    RAYDIUM_LP_V4 = "675kPX9MHTjS2zt1qf1NYzt2i64ZEv3M96GvLpSaVYn"
    
    async with websockets.connect(WSS_URL) as ws:
        # Jiunge na logi za Raydium
        subscription_msg = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [{"mentions": [RAYDIUM_LP_V4]}, {"commitment": "processed"}]
        }
        await ws.send(json.dumps(subscription_msg))
        tg("🚀 **ALPHA-SNIPER v4.0 ACTIVE (Render)**\nSystem: Monitoring New Pairs...")

        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                logs = data.get("params", {}).get("result", {}).get("value", {}).get("logs", [])
                
                for log in logs:
                    if "initialize2" in log.lower():
                        # Hapa ndipo tunakamata Mint address ya token mpya
                        match = re.search(r'([1-9A-HJ-NP-Za-km-z]{32,44})', log)
                        if match:
                            token_mint = match.group(1)
                            if token_mint == RAYDIUM_LP_V4: continue
                            
                            tg(f"🎯 **New Token Detected!**\nMint: `{token_mint}`\nBuying: {AMOUNT_SOL} SOL")
                            # Anza kununua (Buy Logic)
                            buy = await swap("So11111111111111111111111111111111111111112", token_mint, AMOUNT_SOL * 1e9)
                            if buy:
                                tg(f"✅ **Buy Success!**\nSig: [Solscan](https://solscan.io/tx/{buy['sig']})")
            except Exception:
                await asyncio.sleep(1)
                continue

# ---------- EXECUTION ----------

if __name__ == "__main__":
    # 1. Safisha webhooks zote zilizokwama kuzuia Conflict 409
    try:
        bot.remove_webhook()
        print("✅ Fresh start: Webhook removed.")
    except:
        pass

    # 2. Washa Telegram Polling kwenye thread yake
    # skip_pending=True inahakikisha bot haisomi meseji za zamani zilizokwama
    polling_thread = Thread(target=lambda: bot.infinity_polling(non_stop=True, skip_pending=True), daemon=True)
    polling_thread.start()
    
    # 3. Washa Solana Sniper Engine
    try:
        asyncio.run(main_listener())
    except KeyboardInterrupt:
        print("🛑 System Stopped.")
