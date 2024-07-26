# models.reactions.weeb

from disnake.ext import commands

class WeebCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        content_lower = message.content.lower()
        if content_lower == "weeb":
            await message.channel.send('https://media1.tenor.com/m/rM6sdvGLYCMAAAAC/bonk.gif')

def setup(bot):
    bot.add_cog(WeebCog(bot))