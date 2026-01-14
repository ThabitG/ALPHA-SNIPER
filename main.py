# [Tumia Setup na Config toka Code 1 hapo juu]

async def test_run():
    # Tunatumia coin yoyote maarufu (mfano: WIF) kwa ajili ya test
    TEST_MINT = "EKpQGSJojbwqzMbtvS4Aa38H49shnk1VS7AnGfWupump" 
    
    print("🧪 Kuanza Jaribio la Kununua (0.005 SOL)...")
    buy = await swap("So11111111111111111111111111111111111111112", TEST_MINT, 0.005*1e9, "TEST BUY")
    
    if buy:
        print(f"✅ Kununua Kumefanikiwa! Sig: {buy['sig']}")
        print("⏳ Kusubiri sekunde 10 ili kuuza...")
        await asyncio.sleep(10)
        
        sell = await swap(TEST_MINT, "So11111111111111111111111111111111111111112", buy["amt"], "TEST SELL")
        if sell:
            print(f"✅ Kuuza Kumefanikiwa! Sig: {sell['sig']}")
            print("🎉 Bot yako imethibitishwa kufanya kazi 100%!")
        else:
            print("❌ Kuuza Kumefeli.")
    else:
        print("❌ Kununua Kumefeli. Angalia salio au RPC URL.")

if __name__ == "__main__":
    asyncio.run(test_run())
