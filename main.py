import asyncio, os, json, base58, aiohttp
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from dotenv import load_dotenv
import telebot

# ---------- SETUP ----------
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
RPC_URL = os.getenv('RPC_URL')

bot = telebot.TeleBot(TOKEN)
solana = AsyncClient(RPC_URL)
user = Keypair.from_bytes(base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY')))

async def swap(in_m, out_m, amt, action="Trade"):
    async with aiohttp.ClientSession() as s:
        try:
            q_url = f"https://quote-api.jup.ag/v6/quote?inputMint={in_m}&outputMint={out_m}&amount={int(amt)}&slippageBps=1500"
            async with s.get(q_url) as r: q = await r.json()
            p = {"quoteResponse": q, "userPublicKey": str(user.pubkey()), "wrapAndUnwrapSol": True}
            async with s.post("https://quote-api.jup.ag/v6/swap", json=p) as r: sw = await r.json()
            raw = base58.b58decode(sw["swapTransaction"])
            tx = VersionedTransaction.from_bytes(raw)
            signed = VersionedTransaction(tx.message, [user.sign_message(tx.message)])
            res = await solana.send_raw_transaction(bytes(signed))
            return {"sig": str(res.value), "amt": float(q["outAmount"])}
        except Exception as e:
            print(f"Error: {e}")
            return None

async def test_run():
    print("🚀 Kuanza Jaribio...")
    bot.send_message(CHAT_ID, "🧪 **Bot ya Majaribio Ipo Online!**\nInajaribu kununua kiasi kidogo cha SOL...")
    
    # Jaribio la kununua WIF (kiasi kidogo sana 0.005 SOL)
    TEST_MINT = "EKpQGSJojbwqzMbtvS4Aa38H49shnk1VS7AnGfWupump"
    buy = await swap("So11111111111111111111111111111111111111112", TEST_MINT, 0.005*1e9, "TEST BUY")
    
    if buy:
        bot.send_message(CHAT_ID, f"✅ **Kununua Kumefanikiwa!**\nSig: `{buy['sig']}`\nInasubiri sekunde 10 kuuza...")
        await asyncio.sleep(10)
        sell = await swap(TEST_MINT, "So11111111111111111111111111111111111111112", buy["amt"], "TEST SELL")
        if sell:
            bot.send_message(CHAT_ID, "🎉 **Kuuza Kumefanikiwa!** Bot yako ipo tayari 100%.")
    else:
        bot.send_message(CHAT_ID, "❌ **Kununua Kumefeli.** Angalia log za Render au RPC URL.")

if __name__ == "__main__":
    asyncio.run(test_run())
