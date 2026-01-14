import asyncio
import os
import json
import base58
import aiohttp
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Processed
from dotenv import load_dotenv
import telebot

# ---------- SETUP ----------
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
RPC_URL = os.getenv('RPC_URL') # Hapa itatumika Helius yako $49

bot = telebot.TeleBot(TOKEN)
solana = AsyncClient(RPC_URL, commitment=Processed)

try:
    user = Keypair.from_bytes(base58.b58decode(os.getenv('SOLANA_PRIVATE_KEY')))
    print(f"✅ Wallet Connected: {user.pubkey()}")
except Exception as e:
    print(f"❌ Wallet Error: {e}")

async def get_token_balance(mint_address):
    """Inasoma salio moja kwa moja kutoka blockchain kupitia Helius"""
    try:
        resp = await solana.get_token_accounts_by_owner(user.pubkey(), {"mint": mint_address})
        return resp.value[0].account.data # Simplified for test
    except: return 0

async def swap_test(action="BUY"):
    """
    Majaribio ya muamala. Kwa sasa tunatumia Dexscreener API 
    kama mbadala wa Jupiter endapo Jupiter API haipatikani.
    """
    bot.send_message(CHAT_ID, f"🔄 Inajaribu {action} kwa kutumia Helius RPC...")
    
    # Hapa tunaweza kuweka logic ya ku-interact na Raydium moja kwa moja
    # Lakini kwa jaribio la haraka, hebu tuhakikishe muunganisho wa RPC kwanza
    try:
        balance = await solana.get_balance(user.pubkey())
        sol_amt = balance.value / 1e9
        bot.send_message(CHAT_ID, f"✅ RPC Connect OK!\nSalio lako: `{sol_amt:.4f} SOL`")
        
        if sol_amt < 0.01:
            bot.send_message(CHAT_ID, "⚠️ Salio ni dogo sana kufanya trade.")
            return

        # Ikiwa RPC inakubali, tatizo ni Jupiter API pekee
        bot.send_message(CHAT_ID, "🚀 RPC yako ya Helius inafanya kazi. Jupiter API ndiyo inagoma kwenye Render. Inabadilisha muundo sasa...")
        
    except Exception as e:
        bot.send_message(CHAT_ID, f"❌ RPC Error: {str(e)}")

async def test_run():
    print("🚀 Kuanza Jaribio la Mfumo...")
    try:
        bot.send_message(CHAT_ID, "🧪 **System Check Active**")
        await swap_test("BUY")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_run())
