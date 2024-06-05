# modules.reactions.primary_mod

from disnake.ext import commands

class PrimaryModCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        content_lower = message.content.lower()
        if any(keyword in content_lower for keyword in ['primary mod']):
            await message.channel.send(':eyes:')

def setup(bot):
    bot.add_cog(PrimaryModCog(bot))