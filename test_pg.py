import asyncio
import asyncpg


async def t():
    try:
        c = await asyncpg.connect(
            user="user",
            password="1111",
            database="school_monitor",
            host="localhost",
            port=5432,
        )
        print("✅ CONNECT OK")
        await c.close()
    except Exception as e:
        print("❌ ERROR:", e)


asyncio.run(t())
