# modules.translate

from disnake import Embed, Color, ApplicationCommandInteraction, Thread, TextInputStyle, ModalInteraction, MessageCommandInteraction
from modules.utils.GPT import OpenAIAgent
from typing import Optional, Set, Dict
from disnake.ext import commands
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
            system_prompt="You are a translator. Translate the following message to the specified language. If the source language is not specified, detect it automatically. Provide only the translated text without any additional explanations.",
            verbose=False
        )
        self.auto_translate_threads: Dict[int, Set[str]] = {}
        self.user_language_preferences: Dict[int, str] = {}

    @commands.slash_command(
        name="translate",
        description="Translate messages or manage auto-translation settings",
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def translate(
        self,
        inter: ApplicationCommandInteraction,
        auto: Optional[str] = commands.Param(default=None, choices=["on", "off"], description="Turn auto-translation on/off"),
        set_language: Optional[str] = commands.Param(default=None, description="Set your preferred language"),
        status: Optional[bool] = commands.Param(default=None, description="Show translation status")
    ):
        if auto is not None:
            if not isinstance(inter.channel, Thread):
                await inter.response.send_message("Auto-translation can only be used in threads.", ephemeral=True)
                return
            if auto == "on":
                await self.turn_on_auto_translate(inter)
            else:
                await self.turn_off_auto_translate(inter)
        elif set_language:
            if not isinstance(inter.channel, Thread) or inter.channel.id not in self.auto_translate_threads:
                await inter.response.send_message("You can only set your language in threads with auto-translation enabled.", ephemeral=True)
                return
            await self.set_user_language(inter, set_language)
        elif status:
            await self.show_translation_status(inter)
        else:
            await inter.response.send_message("Please use this command with one of the options: `auto`, `set_language`, or `status`. For translating messages, use the message context menu.", ephemeral=True)

    @commands.message_command(name="Translate")
    async def translate_message(self, inter: MessageCommandInteraction):
        modal = disnake.ui.Modal(
            title="Translate Message",
            custom_id="translate_modal",
            components=[
                disnake.ui.TextInput(
                    label="Target language",
                    custom_id="target_language",
                    style=TextInputStyle.short,
                    max_length=50,
                ),
            ],
        )
        await inter.response.send_modal(modal)

    async def show_translate_modal(self, inter: ApplicationCommandInteraction, text_to_translate: str = ""):
        modal = disnake.ui.Modal(
            title="Translate Text",
            custom_id="translate_modal",
            components=[
                disnake.ui.TextInput(
                    label="Text to translate",
                    custom_id="text_to_translate",
                    style=TextInputStyle.paragraph,
                    max_length=1000,
                    value=text_to_translate,
                ),
                disnake.ui.TextInput(
                    label="Target language",
                    custom_id="target_language",
                    style=TextInputStyle.short,
                    max_length=50,
                ),
            ],
        )
        await inter.response.send_modal(modal)

    @commands.Cog.listener("on_modal_submit")
    async def on_translate_modal_submit(self, inter: ModalInteraction):
        if inter.custom_id == "translate_modal":
            target_language = inter.text_values["target_language"]
            text_to_translate = inter.target.content  # Get the content of the original message
            translated_text = await self.translate_text(text_to_translate, target_language)
            if translated_text:
                translations = {target_language: translated_text}
                embed = self.create_multi_translation_embed(inter.target, text_to_translate, translations)
                await inter.response.send_message(embed=embed)
            else:
                await inter.response.send_message("Sorry, I couldn't translate the text. Please try again.", ephemeral=True)

    def create_multi_translation_embed(self, message_or_inter, original_text, translations):
        embed = Embed(title="🌐 Translation", color=Color.blue())
        embed.add_field(name="📝 Original", value=f"```{original_text}```", inline=False)
        for lang, text in translations.items():
            embed.add_field(name=f"🔄 {lang}", value=f"```{text}```", inline=False)
        if isinstance(message_or_inter, disnake.Message):
            author = message_or_inter.author
        else:
            author = message_or_inter.author
        embed.set_author(name=f"Requested by {author.display_name}", icon_url=author.avatar.url if author.avatar else None)
        embed.set_footer(text="⚠️ This translation was generated by an AI language model and may not be perfectly accurate.")
        return embed

    async def turn_on_auto_translate(self, inter):
        if inter.channel.id not in self.auto_translate_threads:
            self.auto_translate_threads[inter.channel.id] = set()
        await inter.response.send_message("Auto-translation enabled in this thread. Users can set their preferred language using `/translate set_language`.")

    async def turn_off_auto_translate(self, inter):
        if inter.channel.id in self.auto_translate_threads:
            del self.auto_translate_threads[inter.channel.id]
            await inter.response.send_message("Auto-translation has been turned off for this thread.")
        else:
            await inter.response.send_message("Auto-translation was not enabled for this thread.")

    async def set_user_language(self, inter, language):
        self.user_language_preferences[inter.author.id] = language
        if isinstance(inter.channel, Thread) and inter.channel.id in self.auto_translate_threads:
            self.auto_translate_threads[inter.channel.id].add(language)
        await inter.response.send_message(f"Your preferred language has been set to {language}.", ephemeral=True)

    async def show_translation_status(self, inter):
        if not isinstance(inter.channel, Thread):
            await inter.response.send_message("Translation status is only available in threads.", ephemeral=True)
            return
        thread_id = inter.channel.id
        if thread_id not in self.auto_translate_threads:
            await inter.response.send_message("Auto-translation is not enabled in this thread.", ephemeral=True)
            return
        active_languages = self.auto_translate_threads[thread_id]
        user_language = self.user_language_preferences.get(inter.author.id, "Not set")
        status_message = f"Auto-translation status for this thread:\n"
        status_message += f"• Enabled: Yes\n"
        status_message += f"• Active languages: {', '.join(sorted(active_languages))}\n"
        status_message += f"• Your preferred language: {user_language}"
        await inter.response.send_message(status_message, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not isinstance(message.channel, Thread):
            return
        if message.channel.id in self.auto_translate_threads:
            source_text = self.replace_mentions(message, message.content)
            translations = await self.translate_to_multiple_languages(source_text, self.auto_translate_threads[message.channel.id])
            if translations:
                embed = self.create_auto_translation_embed(message, translations)
                await message.reply(embed=embed)

    async def translate_to_multiple_languages(self, text, target_languages):
        translations = {}
        source_lang = await self.detect_language(text)
        for target_lang in target_languages:
            if target_lang.lower() != source_lang.lower():
                translated_text = await self.translate_text(text, target_lang, source_lang)
                if translated_text:
                    translations[target_lang] = translated_text
        return translations

    async def detect_language(self, text):
        prompt = f"Detect the language of the following text and respond with only the language name in English: {text}"
        response = self.chat_engine.chat(prompt)
        return response.response.strip().lower() if response and response.response else "unknown"

    async def translate_text(self, message, target_lang, source_lang=None):
        prompt = f"Translate this {'from ' + source_lang + ' ' if source_lang else ''}to {target_lang}: {message}"
        response = self.chat_engine.chat(prompt)
        return response.response.strip() if response and response.response else None

    def create_auto_translation_embed(self, message, translations):
        embed = Embed(title="🌐 Auto-Translations", color=Color.blue())
        for lang, text in translations.items():
            embed.add_field(name=f"🔄 {lang}", value=f"```{text}```", inline=False)
        embed.set_author(name=f"Translations for {message.author.display_name}", icon_url=message.author.avatar.url if message.author.avatar else None)
        embed.set_footer(text="⚠️ These translations were generated by an AI language model and may not be perfectly accurate.")
        return embed

    def create_multi_translation_embed(self, message_or_inter, original_text, translations):
        embed = Embed(title="🌐 Translation", color=Color.blue())
        embed.add_field(name="📝 Original", value=f"```{original_text}```", inline=False)
        for lang, text in translations.items():
            embed.add_field(name=f"🔄 {lang}", value=f"```{text}```", inline=False)
        if isinstance(message_or_inter, disnake.Message):
            author = message_or_inter.author
        else:
            author = message_or_inter.author
        embed.set_author(name=f"Requested by {author.display_name}", icon_url=author.avatar.url if author.avatar else None)
        embed.set_footer(text="⚠️ This translation was generated by an AI language model and may not be perfectly accurate.")
        return embed

    @staticmethod
    def replace_mentions(inter, message):
        return re.sub(r'<@!?(\d+)>', lambda m: f"@{inter.guild.get_member(int(m.group(1))).display_name}" if inter.guild.get_member(int(m.group(1))) else m.group(0), message)

    @translate.error
    async def translate_error(self, inter, error):
        await inter.response.send_message(f"{'This command is on cooldown. Try again in {:.1f} seconds.'.format(error.retry_after) if isinstance(error, commands.CommandOnCooldown) else f'An error occurred: {error}'}", ephemeral=True)

def setup(client):
    client.add_cog(TranslateCog(client))