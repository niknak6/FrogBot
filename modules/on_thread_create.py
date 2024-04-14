import asyncio

EMOJI_MAP = {
    1162100167110053888: ["🐞", "📜", "📹", "✅"],
    1167651506560962581: ["💡", "🧠", "✅"],
    1160318669839147259: ["💡", "🧠", "✅"],
}

async def add_reaction(message, emoji):
    try:
        await message.add_reaction(emoji)
    except Exception as e:
        print(f"Error adding reaction {emoji}: {e}")

async def on_thread_create(thread):
    try:
        emojis_to_add = EMOJI_MAP.get(thread.parent_id, [])
        if emojis_to_add:
            async for message in thread.history(limit=1):
                for emoji in emojis_to_add:
                    await add_reaction(message, emoji)
                    await asyncio.sleep(0.5)
    except Exception as e:
        print(f"Error in on_thread_create: {e}")

def setup(client):
    client.event(on_thread_create)
