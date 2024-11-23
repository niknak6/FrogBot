# modules.translate

from typing import Dict, Set, List, Union
from collections import defaultdict
from modules.utils import database
from disnake import Embed, Color
from disnake.ext import commands
from core import config
import disnake
import asyncio
import logging
import openai

client = openai.OpenAI(api_key=config.read().get('OPENAI_API_KEY'))

COMBINED_PROMPT = """You are a translation assistant. Your job is to:
1. Detect languages accurately
2. Translate messages while maintaining context and nuance
3. Never add commentary or additional messages
4. Always use full language names (e.g., 'English', 'French', 'Spanish'), never ISO codes
5. Return responses in this exact format:
   DETECTED:<language_name>
   TRANSLATIONS:
   <language_name>:translated_text
   <language_name>:translated_text

Previous conversation context:"""

class TranslationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.thread_histories: Dict[int, List[dict]] = {}
        self.MAX_HISTORY = 50
        self.language_usage: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    async def load_language_usage(self, user_id: int):
        usage_data = await database.get_language_usage(user_id)
        self.language_usage[user_id] = defaultdict(int, usage_data)

    async def _make_openai_request(self, messages: List[dict], thread_id: int) -> str:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0,
        )
        result = response.choices[0].message.content.strip()
        messages.append({"role": "assistant", "content": result})
        self.thread_histories[thread_id] = messages[-self.MAX_HISTORY:]
        return result

    async def handle_message_translation(self, content: str, target_langs: Set[str], thread_id: int, username: str, user_id: int, message: Union[disnake.Message, disnake.ModalInteraction]) -> tuple[str, Dict[str, str]]:
        message_content = content
        if isinstance(message, disnake.Message):
            for mention in message.mentions:
                message_content = message_content.replace(f'<@{mention.id}>', mention.display_name)
                message_content = message_content.replace(f'<@!{mention.id}>', mention.display_name)
        readable_langs = [' '.join(word.capitalize() for word in lang.split()) for lang in target_langs]
        prompt = f"Detect the language of this text and translate it to {', '.join(readable_langs)}:\n{message_content}"
        response = await self._make_openai_request(
            self._prepare_message(thread_id, prompt, username),
            thread_id
        )
        lines = response.strip().split('\n')
        detected_lang = lines[0].replace('DETECTED:', '').strip().lower()
        translations = {}
        for line in lines[2:]:
            if ':' in line:
                lang, trans = line.split(':', 1)
                lang = lang.strip().lower()
                translations[lang] = content if trans.strip() == content else trans.strip()
        self.language_usage[user_id][detected_lang] += 1
        await database.update_language_usage(user_id, detected_lang)
        if user_id not in self.language_usage:
            await self.load_language_usage(user_id)
        total_messages = sum(self.language_usage[user_id].values())
        if total_messages >= 5:
            usage_percentages = {
                lang: (count / total_messages) * 100 
                for lang, count in self.language_usage[user_id].items()
            }
            preferred_lang = max(usage_percentages.items(), key=lambda x: x[1])[0]
            if usage_percentages[preferred_lang] > 70:
                current_user_lang = await database.get_user_language(thread_id, user_id)
                if current_user_lang != preferred_lang:
                    await self.handle_new_user_language(thread_id, user_id, preferred_lang)
        return detected_lang, translations

    async def handle_new_user_language(self, thread_id: int, user_id: int, lang_code: str) -> None:
        await asyncio.gather(
            database.set_user_language(thread_id, user_id, lang_code),
            database.add_thread_language(thread_id, lang_code)
        )

    def _prepare_message(self, thread_id: int, content: str, username: str) -> List[dict]:
        messages = self.get_thread_history(thread_id).copy()
        messages.append({"role": "user", "content": f"{username}: {content}"})
        return messages

    def get_thread_history(self, thread_id: int) -> List[dict]:
        return self.thread_histories.setdefault(
            thread_id, 
            [{"role": "system", "content": COMBINED_PROMPT}]
        )

    def create_translation_embed(self, message: disnake.Message, original_text: str, translations: Dict[str, str], auto: bool = True) -> Embed:
        embed = Embed(title="🌐 Auto-Translations" if auto else "🌐 Translation", color=Color.blue())
        if not auto:
            embed.add_field(name="📝 Original", value=f"```{original_text}```", inline=False)
        for lang, text in translations.items():
            display_lang = ' '.join(word.capitalize() for word in lang.split())
            embed.add_field(name=f"🔄 {display_lang}", value=f"```{text}```", inline=False)
        author = message.author
        embed.set_author(
            name=f"{'Translations for' if auto else 'Requested by'} {author.display_name}",
            icon_url=author.avatar.url if author.avatar else None
        )
        embed.set_footer(text="⚠️ These translations were generated by an AI language model and may not be perfectly accurate.")
        return embed

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        if (message.author.bot or 
            not isinstance(message.channel, disnake.Thread) or
            not await database.is_thread_active(message.channel.id)):
            return
        thread_id = message.channel.id
        user_id = message.author.id
        content = message.content
        username = message.author.display_name
        thread_languages = await database.get_thread_languages(thread_id)
        if not thread_languages:
            return
        current_lang, translations = await self.handle_message_translation(
            content, 
            set(thread_languages), 
            thread_id, 
            username,
            user_id,
            message
        )
        user_lang = await database.get_user_language(thread_id, user_id)
        if not user_lang:
            await self.handle_new_user_language(thread_id, user_id, current_lang)
        translations = {
            lang: trans 
            for lang, trans in translations.items() 
            if lang != current_lang and trans != content
        }
        if translations:
            embed = self.create_translation_embed(message, content, translations)
            await message.reply(embed=embed, mention_author=False)

    @commands.slash_command(name="translate", description="Translation management commands")
    async def translate_group(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @translate_group.sub_command(name="message", description="Translate a message to another language")
    async def translate_message(self, inter: disnake.ApplicationCommandInteraction):
        await self.show_translate_modal(inter)

    async def show_translate_modal(self, inter: disnake.ApplicationCommandInteraction):
        modal = disnake.ui.Modal(
            title="Translate Text",
            custom_id="translate_modal",
            components=[
                disnake.ui.TextInput(
                    label="Text to translate",
                    custom_id="text_to_translate",
                    style=disnake.TextInputStyle.paragraph,
                    max_length=1000,
                    placeholder="Enter the text you want to translate..."
                ),
                disnake.ui.TextInput(
                    label="Target language",
                    custom_id="target_language",
                    style=disnake.TextInputStyle.short,
                    max_length=50,
                    placeholder="e.g., Spanish, French, German..."
                )
            ]
        )
        await inter.response.send_modal(modal)

    @commands.Cog.listener("on_modal_submit")
    async def on_translate_modal_submit(self, inter: disnake.ModalInteraction):
        if inter.custom_id != "translate_modal":
            return
        text_to_translate = inter.text_values["text_to_translate"]
        target_lang = inter.text_values["target_language"]
        detected_lang, translations = await self.handle_message_translation(
            text_to_translate,
            {target_lang.lower()},
            inter.channel.id if isinstance(inter.channel, disnake.Thread) else 0,
            inter.author.display_name,
            inter.author.id,
            inter
        )
        embed = self.create_translation_embed(inter, text_to_translate, translations, auto=False)
        await inter.response.send_message(embed=embed)

    @translate_group.sub_command(name="thread", description="Manage thread translation settings")
    async def thread_group(
        self,
        inter: disnake.ApplicationCommandInteraction,
        action: str = commands.Param(
            choices=["enable", "disable", "status"],
            description="Action to perform"
        )
    ):
        if action == "enable":
            await self.enable_translation(inter)
        elif action == "disable":
            await self.disable_translation(inter)
        elif action == "status":
            await self.translation_status(inter)

    @translate_group.sub_command(name="usage", description="Manage your language usage statistics")
    async def usage_group(
        self,
        inter: disnake.ApplicationCommandInteraction,
        action: str = commands.Param(
            choices=["view", "reset"],
            description="Action to perform"
        )
    ):
        if action == "view":
            await self.language_usage_stats(inter)
        elif action == "reset":
            await self.reset_usage_stats(inter)

    async def enable_translation(self, inter: disnake.ApplicationCommandInteraction):
        if not isinstance(inter.channel, disnake.Thread):
            await self._send_embed_response(inter, "❌ Invalid Channel", "This command can only be used in threads!", Color.red())
            return
        thread_id = inter.channel.id
        try:
            if await database.is_thread_active(thread_id):
                await self._send_embed_response(inter, "❌ Already Active", "Auto-translation is already enabled in this thread!", Color.red())
                return
            await database.set_thread_active(thread_id, True)
            self.thread_histories[thread_id] = [{"role": "system", "content": COMBINED_PROMPT}]
            description = ("Auto-translation has been enabled for this thread!\n\n"
                          "**How it works**\n"
                          "Users' language preference will be automatically detected and used for translations.")
            await self._send_embed_response(inter, "🌐 Translation Enabled", description, Color.green(), ephemeral=False)
        except Exception as e:
            logging.error(f"Failed to enable translation in thread {thread_id}: {e}")
            await self._send_embed_response(inter, "❌ Error", "Failed to enable translation. Please try again later.", Color.red())

    async def disable_translation(self, inter: disnake.ApplicationCommandInteraction):
        if not isinstance(inter.channel, disnake.Thread):
            await self._send_embed_response(inter, "❌ Invalid Channel", "This command can only be used in threads!", Color.red())
            return
        thread_id = inter.channel.id
        try:
            if not await database.is_thread_active(thread_id):
                await self._send_embed_response(inter, "❌ Not Active", "Auto-translation is not enabled in this thread!", Color.red())
                return
            await database.set_thread_active(thread_id, False)
            self.thread_histories.pop(thread_id, None)
            await self._send_embed_response(inter, "🌐 Translation Disabled", "Auto-translation has been disabled for this thread.", Color.orange(), ephemeral=False)
        except Exception as e:
            logging.error(f"Failed to disable translation in thread {thread_id}: {e}")
            await self._send_embed_response(inter, "❌ Error", "Failed to disable translation. Please try again later.", Color.red())

    async def translation_status(self, inter: disnake.ApplicationCommandInteraction):
        if not isinstance(inter.channel, disnake.Thread):
            await self._send_embed_response(inter, "❌ Invalid Channel", "This command can only be used in threads!", Color.red())
            return
        is_active = await database.is_thread_active(inter.channel.id)
        embed = Embed(
            title="🌐 Translation Status",
            description=f"Auto-translation is currently **{'enabled' if is_active else 'disabled'}** in this thread.",
            color=Color.green() if is_active else Color.red()
        )
        if is_active:
            thread_languages = await database.get_thread_languages(inter.channel.id)
            if thread_languages:
                formatted_langs = [' '.join(word.capitalize() for word in lang.split()) for lang in thread_languages]
                embed.add_field(
                    name="Active Languages",
                    value=", ".join(formatted_langs),
                    inline=False
                )
        await inter.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: disnake.Thread):
        await database.clear_thread_data(thread.id)
        self.thread_histories.pop(thread.id, None)

    async def language_usage_stats(self, inter: disnake.ApplicationCommandInteraction):
        user_id = inter.author.id
        if user_id not in self.language_usage:
            await self.load_language_usage(user_id)
        if not self.language_usage[user_id]:
            await self._send_embed_response(
                inter,
                "📊 Language Usage Statistics",
                "No language usage data available yet.",
                Color.blue()
            )
            return
        total_messages = sum(self.language_usage[user_id].values())
        usage_stats = []
        for lang, count in self.language_usage[user_id].items():
            percentage = (count / total_messages) * 100
            display_lang = ' '.join(word.capitalize() for word in lang.split())
            usage_stats.append(f"{display_lang}: {percentage:.1f}% ({count} messages)")
        embed = Embed(
            title="📊 Language Usage Statistics",
            description="\n".join(usage_stats),
            color=Color.blue()
        )
        await inter.response.send_message(embed=embed, ephemeral=True)

    async def reset_usage_stats(self, inter: disnake.ApplicationCommandInteraction):
        user_id = inter.author.id
        await database.clear_language_usage(user_id)
        self.language_usage.pop(user_id, None)
        await self._send_embed_response(
            inter,
            "📊 Statistics Reset",
            "Your language usage statistics have been reset.",
            Color.green()
        )

def setup(bot):
    bot.add_cog(TranslationCog(bot))