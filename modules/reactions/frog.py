# modules.reactions.frog

from disnake.ext import commands

class FrogCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        content_lower = message.content.lower()
        if content_lower == '🐸':
            await message.channel.send(":frog:")

def setup(bot):
    bot.add_cog(FrogCog(bot))