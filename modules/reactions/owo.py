# modules.reactions.owo

from disnake.ext import commands
import random

class OwoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.owo_responses = ['o3o', 'UwU', 'Hoppy-chan kawaii desu~', 'Ribbit-senpai noticed you!', 'Froggy power, activate! Transform into maximum kawaii mode!', 'Wibbit-senpai, notice my kawaii vibes!']
        self.last_used_owo = None

    async def send_owo_response(self, message):
        available_responses = [response for response in self.owo_responses if response != self.last_used_owo]
        if not available_responses:
            available_responses = self.owo_responses
        selected_response = random.choice(available_responses)
        self.last_used_owo = selected_response
        await message.channel.send(selected_response)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if 'owo' in message.content.lower():
            await self.send_owo_response(message)

def setup(bot):
    bot.add_cog(OwoCog(bot))