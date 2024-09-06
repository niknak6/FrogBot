# modules.translate

from disnake import TextInputStyle, ui, Embed, Color, ApplicationCommandInteraction, MessageCommandInteraction, Thread
from modules.utils.GPT import OpenAIAgent
from disnake.ext import commands
import asyncio
import re
from typing import Optional, Tuple, Set, Dict

TIMEOUT = 300
TRANSLATE_MODAL_ID = 'translate_modal'
AUTO_TRANSLATE_MODAL_ID = 'auto_translate_modal'

class TranslateCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.chat_engine = OpenAIAgent.from_tools(
            [],
            system_prompt="You are a translator. Translate the following message to the specified language. If the source language is not specified, detect it automatically. Provide only the translated text without any additional explanations.",
            verbose=False
        )
        self.auto_translate_threads: Dict[int, Tuple[str, str]] = {}
        self.user_language_preferences: Dict[int, str] = {}
        self.auto_translate_opt_in: Set[int] = set()

    @commands.slash_command(
        name="translate",
        description="Translate messages or manage auto-translation settings",
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def translate(
        self,
        inter: ApplicationCommandInteraction,
        message: Optional[str] = commands.Param(default=None, description="Message to translate"),
        auto: Optional[str] = commands.Param(default=None, choices=["on", "off"], description="Turn auto-translation on/off"),
        set_language: Optional[str] = commands.Param(default=None, description="Set your preferred language"),
        toggle: Optional[bool] = commands.Param(default=None, description="Toggle opt-in/out of auto-translation"),
        list_languages: bool = commands.Param(default=False, description="List active languages"),
        status: bool = commands.Param(default=False, description="Show translation status")
    ):
        if all(param is None for param in [message, auto, set_language, toggle]) and not list_languages and not status:
            await self.show_translate_modal(inter)
            return

        if auto is not None:
            if not isinstance(inter.channel, Thread):
                await inter.response.send_message("Auto-translation can only be used in threads.", ephemeral=True)
                return
            await self.show_auto_translate_modal(inter) if auto == "on" else await self.turn_off_auto_translate(inter)
        elif message:
            await self.show_translate_modal(inter, message)
        elif set_language:
            self.user_language_preferences[inter.author.id] = set_language
            await inter.response.send_message(f"Your preferred language has been set to {set_language}.", ephemeral=True)
        elif toggle is not None:
            self.auto_translate_opt_in.symmetric_difference_update({inter.author.id})
            await inter.response.send_message(f"You have opted {'in' if inter.author.id in self.auto_translate_opt_in else 'out'} of auto-translation.", ephemeral=True)
        elif list_languages:
            await self.list_active_languages(inter)
        elif status:
            await self.show_translation_status(inter)

    @commands.message_command(name="Translate Message")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def translate_message(self, inter: MessageCommandInteraction):
        await self.show_translate_modal(inter, inter.target.content, inter.target.author.display_name)

    async def show_translate_modal(self, inter, message=None, author=None):
        await inter.response.send_modal(
            title="Translate",
            custom_id=TRANSLATE_MODAL_ID,
            components=[
                ui.TextInput(label="Target Language", placeholder="Enter the target language (e.g., Spanish)", custom_id="target_lang", style=TextInputStyle.short),
                ui.TextInput(label="Message", value=message, placeholder="Enter the message to translate" if not message else None, custom_id="message", style=TextInputStyle.paragraph, required=not bool(message)),
                ui.TextInput(label="Source Language (optional)", placeholder="Leave blank for auto-detection", custom_id="source_lang", style=TextInputStyle.short, required=False),
            ],
        )
        try:
            modal_inter = await inter.client.wait_for('modal_submit', check=lambda i: i.custom_id == TRANSLATE_MODAL_ID and i.author.id == inter.author.id, timeout=TIMEOUT)
            message, target_lang, source_lang = modal_inter.text_values.get('message', ''), modal_inter.text_values.get('target_lang', ''), modal_inter.text_values.get('source_lang', '')
            translated_text = await self.translate_text(self.replace_mentions(inter, message), target_lang, source_lang)
            await modal_inter.response.send_message(embed=self.create_translation_embed(inter, message, translated_text, target_lang, author, is_auto=False) if translated_text else "❌ Translation error.")
        except asyncio.TimeoutError:
            await inter.followup.send("⏰ Translation request timed out.")

    async def show_auto_translate_modal(self, inter):
        await inter.response.send_modal(
            title="Auto Translate Setup",
            custom_id=AUTO_TRANSLATE_MODAL_ID,
            components=[
                ui.TextInput(label="Target Language", placeholder="Enter the target language (e.g., Spanish)", custom_id="target_lang", style=TextInputStyle.short),
                ui.TextInput(label="Source Language (optional)", placeholder="Leave blank for auto-detection", custom_id="source_lang", style=TextInputStyle.short, required=False),
            ],
        )
        try:
            modal_inter = await inter.client.wait_for('modal_submit', check=lambda i: i.custom_id == AUTO_TRANSLATE_MODAL_ID and i.author.id == inter.author.id, timeout=TIMEOUT)
            source_lang, target_lang = modal_inter.text_values.get('source_lang', 'auto'), modal_inter.text_values.get('target_lang', '')
            self.auto_translate_threads[inter.channel.id] = (source_lang, target_lang)
            await modal_inter.response.send_message(f"Auto-translation enabled in this thread. Source: {'Auto-detect' if source_lang == 'auto' else source_lang}, Target: {target_lang}")
        except asyncio.TimeoutError:
            await inter.followup.send("⏰ Auto-translation setup timed out.")

    async def turn_off_auto_translate(self, inter):
        if not isinstance(inter.channel, Thread):
            await inter.response.send_message("Auto-translation can only be turned off in threads where it was enabled.", ephemeral=True)
            return
        if inter.channel.id in self.auto_translate_threads:
            del self.auto_translate_threads[inter.channel.id]
            await inter.response.send_message("Auto-translation has been turned off for this thread.")
        else:
            await inter.response.send_message("Auto-translation was not enabled for this thread.")

    @staticmethod
    def replace_mentions(inter, message):
        return re.sub(r'<@!?(\d+)>', lambda m: f"@{inter.guild.get_member(int(m.group(1))).display_name}" if inter.guild.get_member(int(m.group(1))) else m.group(0), message)

    async def translate_text(self, message, target_lang, source_lang=None):
        prompt = f"Translate this to {target_lang}{f' from {source_lang}' if source_lang else ''}: {message}"
        response = await asyncio.to_thread(self.chat_engine.chat, prompt)
        return response.response.strip() if response and response.response else None

    @staticmethod
    def create_translation_embed(inter, original_message, translated_text, target_lang, author, is_auto=False):
        embed = Embed(title=f"🌐 Translation to {target_lang}", color=Color.blue())
        if not is_auto:
            embed.add_field(name=f"📝 Original{f' (by {author})' if author else ''}", value=f"```{original_message}```", inline=False)
        embed.add_field(name="🔄 Translated", value=f"```{translated_text}```", inline=False)
        embed.set_author(name=f"Requested by {inter.author.display_name}", icon_url=inter.author.avatar.url if inter.author.avatar else None)
        embed.set_footer(text="⚠️ This translation was generated by an AI language model and may not be perfectly accurate.")
        return embed

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not isinstance(message.channel, Thread):
            return
        if message.channel.id in self.auto_translate_threads:
            source_lang, target_lang = self.auto_translate_threads[message.channel.id]
            translated_text = await self.translate_text(self.replace_mentions(message, message.content), target_lang, source_lang)
            if translated_text:
                embed = self.create_translation_embed(message, message.content, translated_text, target_lang, message.author.display_name, is_auto=True)
                await message.reply(embed=embed)

    @translate.error
    @translate_message.error
    async def translate_error(self, inter, error):
        await inter.response.send_message(f"{'This command is on cooldown. Try again in {:.1f} seconds.'.format(error.retry_after) if isinstance(error, commands.CommandOnCooldown) else f'An error occurred: {error}'}", ephemeral=True)

    async def list_active_languages(self, inter):
        if not self.auto_translate_threads:
            await inter.response.send_message("No active auto-translations at the moment.", ephemeral=True)
            return

        translations = []
        for thread_id, (source_lang, target_lang) in self.auto_translate_threads.items():
            thread = inter.guild.get_thread(thread_id)
            thread_name = thread.name if thread else f"Unknown Thread ({thread_id})"
            translations.append(f"• {thread_name}: {source_lang} → {target_lang}")

        message = "Active auto-translations:\n" + "\n".join(translations)
        await inter.response.send_message(message, ephemeral=True)

def setup(client):
    client.add_cog(TranslateCog(client))