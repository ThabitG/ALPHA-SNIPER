# [Tumia Setup ile ile ya Config toka Code 1]
# Badilisha main_listener na hii kwa sekunde chache:

async def test_run():
    # Tunajaribu kununua WIF (au coin yoyote maarufu) kwa kiasi kidogo sana
    TEST_MINT = "EKpQGSJojbwqzMbtvS4Aa38H49shnk1VS7AnGfWupump" 
    print("🧪 Kuanza Jaribio la Kununua...")
    buy = await swap("So11111111111111111111111111111111111111112", TEST_MINT, 0.01*1e9, "TEST BUY")
    
    if buy:
        print("✅ Kununua Kumefanikiwa! Kusubiri sekunde 10 ili kuuza...")
        await asyncio.sleep(10)
        sell = await swap(TEST_MINT, "So11111111111111111111111111111111111111112", buy["amt"], "TEST SELL")
        if sell:
            print("✅ Kuuza Kumefanikiwa! Bot yako iko tayari 100%.")
        else: print("❌ Kuuza Kumefeli.")
    else: print("❌ Kununua Kumefeli. Angalia RPC URL au Salio.")

if __name__ == "__main__":
    asyncio.run(test_run())
