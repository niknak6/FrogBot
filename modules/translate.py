# modules.translate

from disnake import TextInputStyle, ui, Embed, Color
from modules.utils.GPT import OpenAIAgent
from disnake.ext import commands
import asyncio
import disnake
import re

TIMEOUT = 300
TRANSLATE_MODAL_ID = 'translate_modal'
AUTO_TRANSLATE_MODAL_ID = 'auto_translate_modal'

class TranslateCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.chat_engine = OpenAIAgent.from_tools(
            [],
            system_prompt="You are a translator. Translate the following message to the specified language. Provide only the translated text without any additional explanations.",
            verbose=False
        )
        self.auto_translate_threads = {}

    @commands.slash_command()
    async def translate(self, inter: disnake.ApplicationCommandInteraction, mode: str = commands.Param(default="single", choices=["single", "auto", "off"])):
        if mode == "auto":
            if not isinstance(inter.channel, disnake.Thread):
                await inter.response.send_message("Auto-translation can only be enabled in threads.", ephemeral=True)
                return
            await self.show_auto_translate_modal(inter)
        elif mode == "off":
            await self.turn_off_auto_translate(inter)
        else:
            await self.show_translate_modal(inter)

    @commands.message_command(name="Translate Message")
    async def translate_message(self, inter: disnake.MessageCommandInteraction):
        await self.show_translate_modal(inter, inter.target.content, inter.target.author.display_name)

    async def show_translate_modal(self, inter, message=None, author=None):
        await inter.response.send_modal(
            title="Translate",
            custom_id=TRANSLATE_MODAL_ID,
            components=[
                ui.TextInput(label="Target Language", placeholder="Enter the target language (e.g., Spanish)", custom_id="target_lang", style=TextInputStyle.short),
                ui.TextInput(label="Message", value=message, placeholder="Enter the message to translate" if not message else None, custom_id="message", style=TextInputStyle.paragraph, required=not bool(message))
            ],
        )
        try:
            modal_inter = await inter.client.wait_for('modal_submit', check=lambda i: i.custom_id == TRANSLATE_MODAL_ID and i.author.id == inter.author.id, timeout=TIMEOUT)
            message, target_lang = modal_inter.text_values.get('message', ''), modal_inter.text_values.get('target_lang', '')
            translated_text = await self.translate_text(self.replace_mentions(inter, message), target_lang)
            await modal_inter.response.send_message(embed=self.create_translation_embed(inter, message, translated_text, target_lang, author) if translated_text else "❌ Translation error.")
        except asyncio.TimeoutError:
            await inter.followup.send("⏰ Translation request timed out.")

    async def show_auto_translate_modal(self, inter):
        await inter.response.send_modal(
            title="Auto Translate Setup",
            custom_id=AUTO_TRANSLATE_MODAL_ID,
            components=[
                ui.TextInput(label="Source Language", placeholder="Enter the source language (e.g., English)", custom_id="source_lang", style=TextInputStyle.short),
                ui.TextInput(label="Target Language", placeholder="Enter the target language (e.g., Spanish)", custom_id="target_lang", style=TextInputStyle.short),
            ],
        )
        try:
            modal_inter = await inter.client.wait_for('modal_submit', check=lambda i: i.custom_id == AUTO_TRANSLATE_MODAL_ID and i.author.id == inter.author.id, timeout=TIMEOUT)
            source_lang, target_lang = modal_inter.text_values.get('source_lang', ''), modal_inter.text_values.get('target_lang', '')
            self.auto_translate_threads[inter.channel.id] = (source_lang, target_lang)
            await modal_inter.response.send_message(f"Auto-translation enabled in this thread. Source: {source_lang}, Target: {target_lang}")
        except asyncio.TimeoutError:
            await inter.followup.send("⏰ Auto-translation setup timed out.")

    async def turn_off_auto_translate(self, inter):
        if not isinstance(inter.channel, disnake.Thread):
            await inter.response.send_message("Auto-translation can only be turned off in threads where it was enabled.", ephemeral=True)
            return
        if inter.channel.id in self.auto_translate_threads:
            del self.auto_translate_threads[inter.channel.id]
            await inter.response.send_message("Auto-translation has been turned off for this thread.")
        else:
            await inter.response.send_message("Auto-translation was not enabled for this thread.")

    def replace_mentions(self, inter, message):
        return re.sub(r'<@!?(\d+)>', lambda m: f"@{inter.guild.get_member(int(m.group(1))).display_name}" if inter.guild.get_member(int(m.group(1))) else m.group(0), message)

    async def translate_text(self, message, target_lang):
        response = await asyncio.to_thread(self.chat_engine.chat, f"Translate this to {target_lang}: {message}")
        return response.response.strip() if response and response.response else None

    def create_translation_embed(self, inter, original_message, translated_text, target_lang, author):
        embed = Embed(title=f"🌐 Translation to {target_lang}", color=Color.blue())
        embed.add_field(name=f"📝 Original{f' (by {author})' if author else ''}", value=f"```{original_message}```", inline=False)
        embed.add_field(name="🔄 Translated", value=f"```{translated_text}```", inline=False)
        embed.set_author(name=f"Requested by {inter.author.display_name}", icon_url=inter.author.avatar.url if inter.author.avatar else None)
        embed.set_footer(text="⚠️ This translation was generated by an AI language model and may not be perfectly accurate.")
        return embed

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not isinstance(message.channel, disnake.Thread):
            return
        if message.channel.id in self.auto_translate_threads:
            source_lang, target_lang = self.auto_translate_threads[message.channel.id]
            translated_text = await self.translate_text(self.replace_mentions(message, message.content), target_lang)
            if translated_text:
                embed = self.create_translation_embed(message, message.content, translated_text, target_lang, message.author.display_name)
                await message.channel.send(embed=embed)

def setup(client):
    client.add_cog(TranslateCog(client))