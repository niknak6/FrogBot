# modules.on_thread_create

from disnake.ui import Button, View
from disnake.ext import commands
import logging
import asyncio
import disnake

EMOJI_MAP = {
    1294572834303119400: ["🐞", "📜", "📹", "✅"],
    1162100167110053888: ["🐞", "📜", "📹", "✅"],
    1160318669839147259: ["💡", "🧠", "✅"],
}

class ThreadCreateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def add_reaction(self, message, emoji):
        try:
            await message.add_reaction(emoji)
            await asyncio.sleep(0.5)
        except Exception as e:
            logging.error(f"Error adding reaction {emoji}: {e}")
            await asyncio.sleep(2)

    class ConfirmationView(View):
        def __init__(self, message, original_poster_id):
            super().__init__()
            self.message = message
            self.original_poster_id = original_poster_id
            done_button = Button(style=disnake.ButtonStyle.green, label="Done!")
            done_button.callback = self.on_done_button_clicked
            self.add_item(done_button)

        async def on_done_button_clicked(self, interaction):
            if interaction.user.id != self.original_poster_id:
                return
            done_embed = disnake.Embed(
                title="Bug Report Information Added",
                description="The user has indicated they added all the information requested to their bug report.",
                color=disnake.Color.green()
            )
            await self.message.edit(embed=done_embed, view=None)

    async def handle_bug_report(self, thread):
        original_message = await thread.fetch_message(thread.id)
        embed = disnake.Embed(
            title="Bug Report Assistance",
            description=(
                "Greetings! It seems you're working on a bug report. To help you more effectively, could you please share the following details:\n"
                '- Did you check for updates? Your bug may already be fixed!\n'
                '- Which branch are you using? (e.g., FrogPilot, FrogPilot-Staging, or any other)\n'
                '- Was there an error in the error log? You can find this in the "Software" panel!\n'
                '- If you think it may be toggle related, post a copy of your toggles! You can find a copy of them in "Fleet Manager" in the "Tools" section!\n'
            ),
            color=disnake.Color.blue()
        )
        embed.set_footer(text="If you need help with any of these steps, please let me know by replying to this message!")
        view = self.ConfirmationView(None, original_message.author.id)
        message = await original_message.reply(embed=embed, view=view)
        view.message = message

    @commands.Cog.listener()
    async def on_thread_create(self, thread):
        try:
            await asyncio.sleep(1)
            emojis_to_add = EMOJI_MAP.get(thread.parent_id, [])
            first_non_bot_message = None
            async for message in thread.history(limit=None):
                if not message.author.bot:
                    first_non_bot_message = message
                    break
            if first_non_bot_message:
                await asyncio.gather(*(self.add_reaction(first_non_bot_message, emoji) for emoji in emojis_to_add))
            if thread.parent_id == 1162100167110053888:
                await self.handle_bug_report(thread)
        except Exception as e:
            logging.error(f"Error in on_thread_create: {e}")

def setup(bot):
    bot.add_cog(ThreadCreateCog(bot))