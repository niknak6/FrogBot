# modules.reactions.cool_frog

from disnake.ext import commands

class CoolFrogCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        content_lower = message.content.lower()
        if ':coolfrog:' in content_lower:
            await message.channel.send('<:coolfrog:1168605051779031060>')

def setup(bot):
    bot.add_cog(CoolFrogCog(bot))