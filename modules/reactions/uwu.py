# modules.reactions.uwu

from disnake.ext import commands
import random

class UwuCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.uwu_responses = ['Wibbit X3 *nuzzles*', 'OwO', 'Froggy hugs for you~', 'Hai hai, Kero-chan desu~', 'Froggy wisdom: always keep it kawaii, even in the rain!', 'Froggy waifu for laifu!']
        self.last_used_uwu = None

    async def send_uwu_response(self, message):
        last_response = self.last_used_uwu
        available_responses = [response for response in self.uwu_responses if response != last_response]
        if not available_responses:
            available_responses = self.uwu_responses
        selected_response = random.choice(available_responses)
        self.last_used_uwu = selected_response
        await message.channel.send(selected_response)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if 'uwu' in message.content.lower():
            await self.send_uwu_response(message)

def setup(bot):
    bot.add_cog(UwuCog(bot))