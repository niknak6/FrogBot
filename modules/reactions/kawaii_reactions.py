# modules.reactions.kawaii_reactions

from disnake.ext import commands
from openai import AsyncOpenAI
from core import Config
import random

class KawaiiReactionsCog(commands.Cog):
    __slots__ = ('bot', 'fallback_responses', 'last_used', 'openai_client')
    
    SYSTEM_PROMPTS = {
        'uwu': "You are a shy, sweet anime-speaking frog. Generate ONE short kawaii response (max 50 characters) using uwu-style speech patterns. Include frog terms, emoticons, and lots of '~' characters. Be extremely cute and gentle.",
        'owo': "You are an energetic, excited anime-speaking frog. Generate ONE short kawaii response (max 50 characters) using owo-style speech patterns. Include frog terms, emoticons, and lots of '*action*' text. Be bouncy and enthusiastic!"
    }
    
    FALLBACK_RESPONSES = {
        'uwu': ['UwU~', '*ribbit*', 'Froggy~'],
        'owo': ['OwO!', '*hop*', 'Kero!']
    }
    
    def __init__(self, bot):
        self.bot = bot
        self.fallback_responses = self.FALLBACK_RESPONSES
        self.last_used = {'uwu': None, 'owo': None}
        api_key = Config().read().get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OpenAI API key not found in config")
        self.openai_client = AsyncOpenAI(api_key=api_key)

    async def generate_response(self, response_type):
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPTS[response_type]},
                    {"role": "user", "content": "Generate a response"}
                ],
                max_tokens=50,
                temperature=0.9
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI API error: {e}")
            return random.choice(self.fallback_responses[response_type])

    async def send_response(self, message, response_type):
        new_response = await self.generate_response(response_type)
        if new_response == self.last_used[response_type]:
            new_response = await self.generate_response(response_type)
        self.last_used[response_type] = new_response
        await message.channel.send(new_response)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        content_lower = message.content.lower()
        if 'uwu' in content_lower:
            await self.send_response(message, 'uwu')
        elif 'owo' in content_lower:
            await self.send_response(message, 'owo')

def setup(bot):
    bot.add_cog(KawaiiReactionsCog(bot)) 