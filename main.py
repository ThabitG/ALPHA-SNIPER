import asyncio
import os
import json
import base58
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

async def test_run():
    print("🚀 Kuanza Jaribio la Mfumo (Direct RPC)...")
    try:
        # 1. Thibitisha Wallet na RPC
        bal = await solana.get_balance(user.pubkey())
        bot.send_message(CHAT_ID, f"🔗 **RPC Connected!**\nWallet: `{user.pubkey()}`\nBalance: `{bal.value / 1e9} SOL`")
        
        # 2. Hapa tutaweka Direct Swap logic ya Raydium
        # Ili usipate error ya Jupiter, tunatumia kwanza 'get_account_info' ya token
        WIF_MINT = "EKpQGSJojbwqzMbtvS4Aa38H49shnk1VS7AnGfWupump"
        info = await solana.get_account_info(Keypair.from_string(WIF_MINT).pubkey())
        
        if info:
            bot.send_message(CHAT_ID, "✅ **Blockchain Access OK!**\nNaweza kuona data za tokens bila Jupiter. Tayari kuanza Sniper sasa.")
        
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_run())
