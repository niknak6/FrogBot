# modules.on_thread_create

from modules.utils.GPT import process_message_with_llm
from disnake.ui import Button, View
import asyncio
import disnake

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

class ConfirmationView(View):
    def __init__(self, message, client):
        super().__init__()
        self.message = message
        self.client = client
        yes_button = Button(style=disnake.ButtonStyle.green, label="Yes")
        yes_button.callback = self.on_yes_button_clicked
        self.add_item(yes_button)
        no_button = Button(style=disnake.ButtonStyle.red, label="No")
        no_button.callback = self.on_no_button_clicked
        self.add_item(no_button)

    async def on_yes_button_clicked(self):
        # Fetch the original forum post
        original_post = await self.message.channel.history(limit=1).flatten()
        original_post = original_post[0] if original_post else None
        if original_post:
            # Send the original post to be processed by the LLM
            await process_message_with_llm(original_post, self.client)

    async def on_no_button_clicked(self):
        await self.message.delete()

async def on_thread_create(thread):
    try:
        await asyncio.sleep(1)
        emojis_to_add = EMOJI_MAP.get(thread.parent_id, [])
        async for message in thread.history(limit=1):
            await asyncio.gather(*(add_reaction(message, emoji) for emoji in emojis_to_add))

        if thread.parent_id == 1162100167110053888:
            message = await thread.send("Do you want the bot to help?")
            view = ConfirmationView(message)
            await message.edit(view=view)
    except Exception as e:
        print(f"Error in on_thread_create: {e}")

def setup(client):
    client.event(on_thread_create)