# modules.reactions.DMs

from disnake.ext import commands
import aiohttp

class DMsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_cat_fact(self):
        async with aiohttp.ClientSession() as session:
            async with session.get('https://catfact.ninja/fact') as response:
                if response.status == 200:
                    data = await response.json()
                    return data['fact']
                else:
                    return "Sorry, I couldn't fetch a cat fact right now."

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild is None and not message.author.bot:
            cat_fact = await self.get_cat_fact()
            await message.channel.send(f"{cat_fact}")

def setup(bot):
    bot.add_cog(DMsCog(bot))