import asyncio  # Tumesahihisha hili kuzuia NameError
import os
import json
import base58
import aiohttp
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

bot = telebot.TeleBot(TOKEN)
solana = AsyncClient(RPC_URL)

try:
    user = Keypair.from_bytes(base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY')))
    print(f"✅ Wallet Connected: {user.pubkey()}")
except Exception as e:
    print(f"❌ Wallet Error: {e}")

async def swap(in_m, out_m, amt):
    """Kazi ya kubadilisha coins kwa kutumia Jupiter V6 na Retry Logic"""
    for attempt in range(3):  # Jaribu mara 3 kama mtandao unasumbua
        async with aiohttp.ClientSession() as s:
            try:
                # Tumesahihisha uunganishaji wa host hapa
                q_url = f"https://quote-api.jup.ag/v6/quote?inputMint={in_m}&outputMint={out_m}&amount={int(amt)}&slippageBps=1500"
                async with s.get(q_url, timeout=15) as r:
                    q = await r.json()
                
                if 'swapTransaction' not in q:
                    # Tunahitaji swap data
                    p_url = "https://quote-api.jup.ag/v6/swap"
                    p_data = {
                        "quoteResponse": q,
                        "userPublicKey": str(user.pubkey()),
                        "wrapAndUnwrapSol": True
                    }
                    async with s.post(p_url, json=p_data, timeout=15) as r:
                        sw = await r.json()
                else:
                    sw = q

                raw = base58.b58decode(sw["swapTransaction"])
                tx = VersionedTransaction.from_bytes(raw)
                signed = VersionedTransaction(tx.message, [user.sign_message(tx.message)])
                
                res = await solana.send_raw_transaction(bytes(signed))
                return {"sig": str(res.value), "amt": float(q["outAmount"])}
            
            except Exception as e:
                print(f"⚠️ Attempt {attempt+1} failed: {e}")
                await asyncio.sleep(3)
    return None

async def test_run():
    print("🚀 Kuanza Jaribio...")
    try:
        bot.send_message(CHAT_ID, "🧪 **ALPHA-SNIPER Test Mode**\nBot imeanza majaribio ya Trade...")
    except Exception as e:
        print(f"❌ Telegram Error: {e}")

    # Coin ya majaribio (WIF)
    WIF_MINT = "EKpQGSJojbwqzMbtvS4Aa38H49shnk1VS7AnGfWupump"
    SOL_MINT = "So11111111111111111111111111111111111111112"
    
    # Jaribu kununua kiasi kidogo sana (0.005 SOL)
    buy = await swap(SOL_MINT, WIF_MINT, 0.005 * 1e9)
    
    if buy:
        msg = f"✅ **Kununua Kumefanikiwa!**\nSig: `{buy['sig']}`\n[Solscan](https://solscan.io/tx/{buy['sig']})\nSubiri sekunde 10 niuze..."
        bot.send_message(CHAT_ID, msg)
        await asyncio.sleep(10)
        
        sell = await swap(WIF_MINT, SOL_MINT, buy['amt'])
        if sell:
            bot.send_message(CHAT_ID, f"🎉 **Kuuza Kumefanikiwa!**\nSig: `{sell['sig']}`\nBot ipo tayari!")
        else:
            bot.send_message(CHAT_ID, "❌ Kuuza kumefeli baada ya majaribio.")
    else:
        bot.send_message(CHAT_ID, "❌ Kununua kumefeli. Angalia log mpya za Render.")

if __name__ == "__main__":
    asyncio.run(test_run())
