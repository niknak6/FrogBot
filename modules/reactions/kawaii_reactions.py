# modules.reactions.kawaii_reactions

from tiktoken import encoding_for_model
from disnake.ext import commands
from openai import AsyncOpenAI
from core import Config
import random

class KawaiiReactionsCog(commands.Cog):
    __slots__ = ('bot', 'fallback_responses', 'last_used', 'openai_client', 'max_context_tokens', 'encoding')
    
    SYSTEM_PROMPTS = {
        'uwu': "You are a shy, sweet anime-speaking frog. Generate ONE short kawaii response (max 50 characters) using uwu-style speech patterns. Include frog terms, emoticons, and lots of '~' characters. Be extremely cute and gentle. Respond to the user's message in a relevant way.",
        'owo': "You are an energetic, excited anime-speaking frog. Generate ONE short kawaii response (max 50 characters) using owo-style speech patterns. Include frog terms, emoticons, and lots of '*action*' text. Be bouncy and enthusiastic! Respond to the user's message in a relevant way!"
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
        self.max_context_tokens = 500
        self.encoding = encoding_for_model("gpt-4")

    def count_tokens(self, text: str) -> int:
        return len(self.encoding.encode(text))

    async def get_message_history(self, message):
        messages = []
        total_tokens = 0
        async for msg in message.channel.history():
            if not msg.author.bot:
                content = msg.content
                token_count = self.count_tokens(content)
                if total_tokens + token_count > self.max_context_tokens:
                    break
                messages.append(content)
                total_tokens += token_count
        messages.reverse()
        history = "\n".join(messages)
        print(f"Context tokens: {self.count_tokens(history)}")
        return history

    async def generate_response(self, response_type, message_history):
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPTS[response_type]},
                    {"role": "user", "content": f"Previous messages:\n{message_history}"}
                ],
                max_tokens=50,
                temperature=0.9
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI API error: {e}")
            return random.choice(self.fallback_responses[response_type])

    async def send_response(self, message, response_type):
        message_history = await self.get_message_history(message)
        new_response = await self.generate_response(response_type, message_history)
        if new_response == self.last_used[response_type]:
            new_response = await self.generate_response(response_type, message_history)
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