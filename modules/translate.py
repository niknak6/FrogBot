# modules.translate

from disnake import Embed, Color, ApplicationCommandInteraction, Thread, TextInputStyle, ModalInteraction, MessageCommandInteraction
from modules.utils.GPT import OpenAIAgent
from typing import Optional, Set, Dict
from collections import defaultdict
from disnake.ext import commands
import disnake
import re

TRANSLATE_MODAL_ID = 'translate_modal'

class TranslateCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.chat_engine = OpenAIAgent.from_tools(
            [],
            system_prompt="Translate the following message to the specified language. If source language not specified, detect it. Provide only the translated text.",
            verbose=False
        )
        self.auto_translate_threads: Dict[int, Set[str]] = {}
        self.user_language_preferences: Dict[int, str] = {}
        self.message_cache = defaultdict(dict)

    @commands.slash_command(name="translate", description="Translate messages or manage auto-translation settings")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def translate(self, inter: ApplicationCommandInteraction, auto: Optional[str] = commands.Param(default=None, choices=["on", "off"], description="Turn auto-translation on/off"),
                        set_language: Optional[str] = commands.Param(default=None, description="Set your preferred language"),
                        status: Optional[bool] = commands.Param(default=None, description="Show translation status")):
        if auto:
            await self.handle_auto_translate(inter, auto)
        elif set_language:
            await self.set_user_language(inter, set_language)
        elif status:
            await self.show_translation_status(inter)
        else:
            await self.show_translate_modal(inter)

    @commands.message_command(name="Translate")
    async def translate_message(self, inter: MessageCommandInteraction):
        await self.show_translate_modal(inter, inter.target.content, message_command=True)

    async def handle_auto_translate(self, inter, auto):
        if not isinstance(inter.channel, Thread):
            await inter.response.send_message("Auto-translation can only be used in threads.", ephemeral=True)
            return
        if auto == "on":
            self.auto_translate_threads.setdefault(inter.channel.id, set())
            await inter.response.send_message("Auto-translation enabled in this thread. Users can set their preferred language using `/translate set_language`.")
        else:
            self.auto_translate_threads.pop(inter.channel.id, None)
            await inter.response.send_message("Auto-translation has been turned off for this thread.")

    async def show_translate_modal(self, inter, text_to_translate="", message_command=False):
        components = [
            disnake.ui.TextInput(label="Target language", custom_id="target_language", style=TextInputStyle.short, max_length=50),
        ]
        if message_command:
            modal_custom_id = f"translate_modal_message:{inter.id}"
            self.message_cache[inter.author.id][inter.id] = text_to_translate
        else:
            modal_custom_id = "translate_modal"
            components.insert(0, disnake.ui.TextInput(label="Text to translate", custom_id="text_to_translate", style=TextInputStyle.paragraph, max_length=1000, value=text_to_translate))
        await inter.response.send_modal(disnake.ui.Modal(title="Translate Text", custom_id=modal_custom_id, components=components))

    @commands.Cog.listener("on_modal_submit")
    async def on_translate_modal_submit(self, inter: ModalInteraction):
        if inter.custom_id.startswith("translate_modal"):
            target_language = inter.text_values["target_language"]
            if inter.custom_id.startswith("translate_modal_message"):
                interaction_id = int(inter.custom_id.split(":")[1])
                text_to_translate = self.message_cache[inter.author.id].pop(interaction_id, None)
                if text_to_translate is None:
                    await inter.response.send_message("Sorry, the message to translate couldn't be found. Please try again.", ephemeral=True)
                    return
            else:
                text_to_translate = inter.text_values.get("text_to_translate")
            translated_text = await self.translate_text(text_to_translate, target_language)
            if translated_text:
                embed = self.create_translation_embed(inter, text_to_translate, {target_language: translated_text})
                await inter.response.send_message(embed=embed)
            else:
                await inter.response.send_message("Sorry, I couldn't translate the text. Please try again.", ephemeral=True)

    async def set_user_language(self, inter, language):
        if not isinstance(inter.channel, Thread) or inter.channel.id not in self.auto_translate_threads:
            await inter.response.send_message("You can only set your preferred language in threads with auto-translation enabled.", ephemeral=True)
            return
        self.user_language_preferences[inter.author.id] = language
        self.auto_translate_threads[inter.channel.id].add(language)
        await inter.response.send_message(f"Your preferred language has been set to {language} for this thread.", ephemeral=True)

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
        status_message = f"Auto-translation status for this thread:\n• Enabled: Yes\n• Active languages: {', '.join(sorted(active_languages))}\n• Your preferred language: {user_language}"
        await inter.response.send_message(status_message, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not isinstance(message.channel, Thread) or message.channel.id not in self.auto_translate_threads:
            return
        filtered_content = self.filter_content(message.content)
        if filtered_content:
            source_text = self.replace_mentions(message, filtered_content)
            translations = await self.translate_to_multiple_languages(source_text, self.auto_translate_threads[message.channel.id])
            if translations:
                embed = self.create_translation_embed(message, source_text, translations, auto=True)
                await message.reply(embed=embed)

    def filter_content(self, content):
        content = re.sub(r'http[s]?://\S+|attachment://\S+\.(?:jpg|jpeg|png|gif|webp)', '', content)
        return '\n'.join(line.strip() for line in content.split('\n') if line.strip())

    async def translate_to_multiple_languages(self, text, target_languages):
        source_lang = await self.detect_language(text)
        return {lang: await self.translate_text(text, lang, source_lang) for lang in target_languages if lang.lower() != source_lang.lower()}

    async def detect_language(self, text):
        response = self.chat_engine.chat(f"Detect language. Respond with language name in English: {text[:100]}")
        return response.response.strip().lower() if response and response.response else "unknown"

    async def translate_text(self, message, target_lang, source_lang=None):
        response = self.chat_engine.chat(f"Translate this {'from ' + source_lang + ' ' if source_lang else ''}to {target_lang}: {message}")
        return response.response.strip() if response and response.response else None

    def create_translation_embed(self, message_or_inter, original_text, translations, auto=False):
        embed = Embed(title="🌐 Auto-Translations" if auto else "🌐 Translation", color=Color.blue())
        if not auto:
            embed.add_field(name="📝 Original", value=f"```{original_text}```", inline=False)
        for lang, text in translations.items():
            embed.add_field(name=f"🔄 {lang}", value=f"```{text}```", inline=False)
        author = message_or_inter.author if isinstance(message_or_inter, disnake.Message) else message_or_inter.author
        embed.set_author(name=f"{'Translations for' if auto else 'Requested by'} {author.display_name}", icon_url=author.avatar.url if author.avatar else None)
        embed.set_footer(text="⚠️ These translations were generated by an AI language model and may not be perfectly accurate.")
        return embed

    @staticmethod
    def replace_mentions(inter, message):
        return re.sub(r'<@!?(\d+)>', lambda m: f"@{inter.guild.get_member(int(m.group(1))).display_name}" if inter.guild.get_member(int(m.group(1))) else m.group(0), message)

    @translate.error
    async def translate_error(self, inter, error):
        await inter.response.send_message(f"{'This command is on cooldown. Try again in {:.1f} seconds.'.format(error.retry_after) if isinstance(error, commands.CommandOnCooldown) else f'An error occurred: {error}'}", ephemeral=True)

def setup(client):
    client.add_cog(TranslateCog(client))