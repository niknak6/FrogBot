# modules.on_thread_create

import asyncio

EMOJI_MAP = {
    1162100167110053888: ["🐞", "📜", "📹", "✅"],
    1167651506560962581: ["💡", "🧠", "✅"],
    1160318669839147259: ["💡", "🧠", "✅"],
}

async def add_reaction(message, emoji):
    try:
        await message.add_reaction(emoji)
        await asyncio.sleep(0.5)
    except Exception as e:
        print(f"Error adding reaction {emoji}: {e}")
        await asyncio.sleep(2)

import disnake
from disnake.ui import Button, View

class ConfirmationView(View):
    def __init__(self):
        super().__init__()
        self.add_item(Button(style=disnake.ButtonStyle.green, label="Yes"))
        self.add_item(Button(style=disnake.ButtonStyle.red, label="No"))

async def on_thread_create(thread):
    try:
        await asyncio.sleep(1)
        emojis_to_add = EMOJI_MAP.get(thread.parent_id, [])
        async for message in thread.history(limit=1):
            await asyncio.gather(*(add_reaction(message, emoji) for emoji in emojis_to_add))
        
        if thread.parent_id == 1162100167110053888:
            view = ConfirmationView()
            await thread.send("Do you want the bot to help?", view=view)
    except Exception as e:
        print(f"Error in on_thread_create: {e}")

def setup(client):
    client.event(on_thread_create)