# modules.translate

from disnake import Embed, Color, ApplicationCommandInteraction, Thread, TextInputStyle, ModalInteraction, MessageCommandInteraction
from typing import Optional, Set, Dict
from collections import defaultdict
from disnake.ext import commands
from openai import AsyncOpenAI
from core import Config
import disnake
import re

TRANSLATE_MODAL_ID = 'translate_modal'

class TranslateCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        config = Config()
        api_key = config.read().get('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OpenAI API key not found in config")
        self.openai_client = AsyncOpenAI(api_key=api_key)
        self.thread_data = {
            'auto_translate': {},
            'user_preferences': {},
        }
        self.message_cache = defaultdict(dict)

    async def _translate_with_openai(self, system_prompt: str, user_content: str) -> Optional[str]:
        try:
            response = await self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI API error: {e}")
            return None

    async def detect_language(self, text: str) -> str:
        result = await self._translate_with_openai(
            "Detect the language. Respond with language name in English.",
            text[:100]
        )
        return result.lower() if result else "unknown"

    async def translate_text(self, message: str, target_lang: str, source_lang: Optional[str] = None) -> Optional[str]:
        system_prompt = f"Translate the following {'from ' + source_lang + ' ' if source_lang else ''}to {target_lang}. Provide only the translated text."
        return await self._translate_with_openai(system_prompt, message)

    def _validate_thread(self, channel) -> tuple[bool, Optional[str]]:
        if not isinstance(channel, Thread):
            return False, "This feature is only available in threads."
        if channel.id not in self.thread_data['auto_translate']:
            return False, "Auto-translation is not enabled in this thread."
        return True, None

    async def translate_to_multiple_languages(self, text: str, target_languages: Set[str]) -> Dict[str, str]:
        source_lang = await self.detect_language(text)
        translations = {}
        source_lang_norm = source_lang.lower().strip()
        for lang in target_languages:
            lang_norm = lang.lower().strip()
            if lang_norm != source_lang_norm:
                translated = await self.translate_text(text, lang, source_lang)
                if translated:
                    translations[lang] = translated
        return translations

    @staticmethod
    def filter_content(content: str) -> str:
        content = re.sub(r'http[s]?://\S+|attachment://\S+\.(?:jpg|jpeg|png|gif|webp)', '', content)
        return '\n'.join(line.strip() for line in content.split('\n') if line.strip())

    @staticmethod
    def replace_mentions(inter, message: str) -> str:
        return re.sub(
            r'<@!?(\d+)>', 
            lambda m: f"@{inter.guild.get_member(int(m.group(1))).display_name}" 
                if inter.guild.get_member(int(m.group(1))) 
                else m.group(0), 
            message
        )

    async def handle_auto_translate(self, inter: ApplicationCommandInteraction, auto: str):
        if not isinstance(inter.channel, Thread):
            await inter.response.send_message("Auto-translation can only be used in threads.", ephemeral=True)
            return
        if auto == "on":
            self.thread_data['auto_translate'].setdefault(inter.channel.id, set())
            await inter.response.send_message(
                "Auto-translation enabled in this thread. Users can set their preferred language using `/translate set_language`."
            )
        else:
            self.thread_data['auto_translate'].pop(inter.channel.id, None)
            await inter.response.send_message("Auto-translation has been turned off for this thread.")

    async def set_user_language(self, inter: ApplicationCommandInteraction, language: str):
        is_valid, error_msg = self._validate_thread(inter.channel)
        if not is_valid:
            await inter.response.send_message(error_msg, ephemeral=True)
            return
        normalized_lang = language.strip()
        self.thread_data['user_preferences'][inter.author.id] = normalized_lang
        self.thread_data['auto_translate'][inter.channel.id].add(normalized_lang)
        await inter.response.send_message(
            f"Your preferred language has been set to {normalized_lang} for this thread.",
            ephemeral=True
        )

    @commands.slash_command(name="translate", description="Translate messages or manage auto-translation settings")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def translate(self, inter: ApplicationCommandInteraction, 
                        auto: Optional[str] = commands.Param(default=None, choices=["on", "off"], description="Turn auto-translation on/off"),
                        set_language: Optional[str] = commands.Param(default=None, description="Set your preferred language"),
                        remove_languages: Optional[str] = commands.Param(default=None, description="Remove language(s) from auto-translate (comma-separated)"),
                        status: Optional[bool] = commands.Param(default=None, description="Show translation status")):
        if auto:
            await self.handle_auto_translate(inter, auto)
        elif set_language:
            await self.set_user_language(inter, set_language)
        elif remove_languages:
            await self.remove_languages(inter, remove_languages)
        elif status:
            await self.show_translation_status(inter)
        else:
            await self.show_translate_modal(inter)

    @commands.message_command(name="Translate")
    async def translate_message(self, inter: MessageCommandInteraction):
        await self.show_translate_modal(inter, inter.target.content, message_command=True)

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

    async def show_translation_status(self, inter):
        if not isinstance(inter.channel, Thread):
            await inter.response.send_message("Translation status is only available in threads.", ephemeral=True)
            return
        thread_id = inter.channel.id
        if thread_id not in self.thread_data['auto_translate']:
            await inter.response.send_message("Auto-translation is not enabled in this thread.", ephemeral=True)
            return
        active_languages = self.thread_data['auto_translate'][thread_id]
        user_language = self.thread_data['user_preferences'].get(inter.author.id, "Not set")
        status_message = f"Auto-translation status for this thread:\n• Enabled: Yes\n• Active languages: {', '.join(sorted(active_languages))}\n• Your preferred language: {user_language}"
        await inter.response.send_message(status_message, ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not isinstance(message.channel, Thread) or message.channel.id not in self.thread_data['auto_translate']:
            return
        filtered_content = self.filter_content(message.content)
        if filtered_content:
            source_text = self.replace_mentions(message, filtered_content)
            translations = await self.translate_to_multiple_languages(source_text, self.thread_data['auto_translate'][message.channel.id])
            if translations:
                embed = self.create_translation_embed(message, source_text, translations, auto=True)
                await message.reply(embed=embed)

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

    @translate.error
    async def translate_error(self, inter, error):
        await inter.response.send_message(f"{'This command is on cooldown. Try again in {:.1f} seconds.'.format(error.retry_after) if isinstance(error, commands.CommandOnCooldown) else f'An error occurred: {error}'}", ephemeral=True)

    async def remove_languages(self, inter, languages_to_remove):
        if not isinstance(inter.channel, Thread) or inter.channel.id not in self.thread_data['auto_translate']:
            await inter.response.send_message("You can only remove languages in threads with auto-translation enabled.", ephemeral=True)
            return
        languages = [lang.strip().lower() for lang in languages_to_remove.split(',')]
        thread_languages = self.thread_data['auto_translate'][inter.channel.id]
        removed = []
        not_found = []
        thread_languages_lower = {lang.lower() for lang in thread_languages}
        for lang in languages:
            if lang in thread_languages_lower:
                original_lang = next(l for l in thread_languages if l.lower() == lang)
                thread_languages.remove(original_lang)
                removed.append(original_lang)
            else:
                not_found.append(lang)
        response = []
        if removed:
            response.append(f"Removed language(s): {', '.join(removed)}")
        if not_found:
            response.append(f"Language(s) not found: {', '.join(not_found)}")
        await inter.response.send_message('\n'.join(response), ephemeral=True)
        for user_id, pref_lang in list(self.thread_data['user_preferences'].items()):
            if pref_lang.lower() in [lang.lower() for lang in removed]:
                del self.thread_data['user_preferences'][user_id]

def setup(client):
    client.add_cog(TranslateCog(client))