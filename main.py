import asyncio
import os
import base58
from solders.keypair import Keypair
from solders.pubkey import Pubkey  # Tumeongeza Pubkey hapa
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

# Kurekebisha Wallet Connect
try:
    user = Keypair.from_bytes(base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY')))
    print(f"✅ Wallet Connected: {user.pubkey()}")
except Exception as e:
    print(f"❌ Wallet Error: {e}")

async def test_run():
    print("🚀 Kuanza Jaribio la Mfumo (Direct RPC)...")
    try:
        # 1. Thibitisha Wallet na RPC
        bal_resp = await solana.get_balance(user.pubkey())
        balance = bal_resp.value / 1e9
        bot.send_message(CHAT_ID, f"🔗 **RPC Connected!**\nWallet: `{user.pubkey()}`\nBalance: `{balance:.4f} SOL`")
        
        # 2. Blockchain Access Test (Bila Jupiter)
        # Tunatumia Pubkey.from_string badala ya Keypair.from_string
        WIF_MINT = "EKpQGSJojbwqzMbtvS4Aa38H49shnk1VS7AnGfWupump"
        mint_pubkey = Pubkey.from_string(WIF_MINT)
        
        info = await solana.get_account_info(mint_pubkey)
        if info.value:
            bot.send_message(CHAT_ID, "✅ **Blockchain Access OK!**\nNaweza kusoma token data moja kwa moja. Tayari kuanza trading!")
        else:
            bot.send_message(CHAT_ID, "⚠️ Token data haijapatikana, lakini RPC ipo sawa.")
            
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ Error: {str(e)}")
        print(f"Error detail: {e}")

if __name__ == "__main__":
    asyncio.run(test_run())
