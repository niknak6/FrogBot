# modules.on_thread_create

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
    def __init__(self, message, original_poster_id):
        super().__init__()
        self.message = message
        self.original_poster_id = original_poster_id
        no_button = Button(style=disnake.ButtonStyle.red, label="No")
        no_button.callback = self.on_no_button_clicked
        self.add_item(no_button)

    async def on_no_button_clicked(self, interaction):
        if interaction.user.id != self.original_poster_id:
            return
        await self.message.delete()

async def on_thread_create(thread):
    try:
        await asyncio.sleep(1)
        emojis_to_add = EMOJI_MAP.get(thread.parent_id, [])
        async for message in thread.history(limit=1):
            await asyncio.gather(*(add_reaction(message, emoji) for emoji in emojis_to_add))
        
        if thread.parent_id == 1162100167110053888:
            original_message = await thread.fetch_message(thread.id)
            message = await original_message.reply("Would you like assistance from the bot? If so, please reply to this message with \"yes\".")
            view = ConfirmationView(message, original_message.author.id)
            await message.edit(view=view)
    except Exception as e:
        print(f"Error in on_thread_create: {e}")

def setup(client):
    client.event(on_thread_create)