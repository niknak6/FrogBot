# modules.translate

from asyncio import Queue, create_task, Task, sleep
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

CONSTANTS = {
    'MODEL_NAME': "gpt-4o-mini",
    'USAGE_THRESHOLD': 1,
    'PREFERRED_LANG_THRESHOLD': 70,
    'MAX_HISTORY': 50,
    'MAX_CACHED_THREADS': 1000,
    'NUM_WORKERS': 3,
    'CLEANUP_INTERVAL': 3600
}

openai_client = openai.OpenAI(api_key=config.read().get('OPENAI_API_KEY'))

COMBINED_PROMPT = """You are a translation assistant. Your job is to:
1. Detect languages accurately
2. Translate messages while maintaining context and nuance
3. Never add commentary or additional messages
4. Always use full language names (e.g., 'English', 'French', 'Spanish')
5. Return responses in this format:
   DETECTED:<language_name>
   TRANSLATIONS:
   <language_name>:translated_text
   <language_name>:translated_text"""

class TranslationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.thread_histories: Dict[int, List[dict]] = {}
        self.language_usage: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.language_usage_cache = {}
        self.translation_queue = Queue()
        self.worker_tasks: List[Task] = []
        self.cleanup_task = None
        self._ready = False

    async def cog_load(self):
        if self._ready:
            return
        self._ready = True
        await self.setup_tasks()

    def cog_unload(self):
        if self.cleanup_task:
            self.cleanup_task.cancel()
        for task in self.worker_tasks:
            task.cancel()
        self.thread_histories.clear()
        self.language_usage_cache.clear()
        self.language_usage.clear()
        self._ready = False

    async def setup_tasks(self):
        if self.cleanup_task:
            self.cleanup_task.cancel()
        for task in self.worker_tasks:
            task.cancel()
        self.worker_tasks.clear()
        self.cleanup_task = create_task(self.periodic_cleanup())
        self.worker_tasks.extend(create_task(self.translation_worker()) for _ in range(CONSTANTS['NUM_WORKERS']))

    async def periodic_cleanup(self):
        while True:
            try:
                active_threads = {
                    thread_id: history 
                    for thread_id, history in self.thread_histories.items()
                    if await database.is_thread_active(thread_id)
                }
                self.thread_histories = active_threads
                if len(self.thread_histories) > CONSTANTS['MAX_CACHED_THREADS']:
                    threads_to_remove = sorted(
                        self.thread_histories.keys(),
                        key=lambda x: len(self.thread_histories[x])
                    )[:len(self.thread_histories) - CONSTANTS['MAX_CACHED_THREADS']]
                    for thread_id in threads_to_remove:
                        del self.thread_histories[thread_id]
                self.language_usage_cache.clear()
                logging.info(f"Cleanup completed. Active threads: {len(self.thread_histories)}")
            except Exception as e:
                logging.error(f"Error during cleanup: {e}")
            await sleep(CONSTANTS['CLEANUP_INTERVAL'])

    async def on_thread_delete(self, thread: disnake.Thread):
        await database.clear_thread_data(thread.id)
        self.thread_histories.pop(thread.id, None)
        logging.info(f"Cleaned up data for deleted thread {thread.id}")

    def _format_language_name(self, lang: str) -> str:
        return ' '.join(word.capitalize() for word in lang.split())

    async def handle_message_translation(
        self, 
        content: str, 
        target_langs: Set[str], 
        thread_id: int, 
        username: str, 
        user_id: int, 
        message: Union[disnake.Message, disnake.ModalInteraction]
    ) -> tuple[str, Dict[str, str]]:
        try:
            content = content.replace('\n', ' ').strip()
            if not content:
                return '', {}
            if isinstance(message, disnake.Message) and message.mentions:
                for mention in message.mentions:
                    content = content.replace(f'<@{mention.id}>', mention.display_name)\
                                   .replace(f'<@!{mention.id}>', mention.display_name)
            readable_langs = [self._format_language_name(lang) for lang in target_langs]
            prompt = f"Translate this complete message to {', '.join(readable_langs)}:\n{content}"
            response = await self._make_openai_request(
                self._prepare_message(thread_id, prompt, username),
                thread_id
            )
            lines = response.strip().split('\n')
            if not lines or not lines[0].startswith('DETECTED:'):
                raise ValueError("Invalid response format from translation model")
            detected_lang = lines[0].replace('DETECTED:', '').strip().lower()
            if not detected_lang:
                raise ValueError("No detected language in response")
            translations = {
                lang.strip().lower(): trans.strip()
                for line in lines[2:] if ':' in line
                for lang, trans in [line.split(':', 1)]
            }
            await asyncio.gather(
                database.update_language_usage(user_id, detected_lang),
                self._update_user_language_preference(user_id, detected_lang, thread_id)
            )
            if thread_id in self.thread_histories and len(self.thread_histories[thread_id]) > CONSTANTS['MAX_HISTORY']:
                self.thread_histories[thread_id] = (
                    [self.thread_histories[thread_id][0]]  # Keep system prompt
                    + self.thread_histories[thread_id][-(CONSTANTS['MAX_HISTORY']-1):]
                )
            return detected_lang, {
                lang: trans 
                for lang, trans in translations.items()
                if lang != detected_lang and trans.strip() != content.strip()
            }
        except Exception as e:
            logging.error(f"Translation error: {e}")
            self.thread_histories.pop(thread_id, None)
            raise

    async def _make_openai_request(self, messages: List[dict], thread_id: int) -> str:
        try:
            response = openai_client.chat.completions.create(
                model=CONSTANTS['MODEL_NAME'],
                messages=messages,
                temperature=0,
            )
            result = response.choices[0].message.content.strip()
            if thread_id in self.thread_histories:
                self.thread_histories[thread_id].append({
                    "role": "assistant", 
                    "content": result
                })
            return result
        except Exception as e:
            logging.error(f"OpenAI API error: {e}")
            raise

    async def _update_user_language_preference(self, user_id: int, detected_lang: str, thread_id: int):
        try:
            if user_id not in self.language_usage:
                await self.load_language_usage(user_id)
            detected_lang = detected_lang.lower().strip()
            self.language_usage[user_id][detected_lang] += 1
            total_messages = sum(self.language_usage[user_id].values())
            if total_messages >= CONSTANTS['USAGE_THRESHOLD']:
                usage_percentages = {
                    lang: (count / total_messages) * 100 
                    for lang, count in self.language_usage[user_id].items()
                }
                preferred_lang = max(usage_percentages.items(), key=lambda x: x[1])[0]
                if usage_percentages[preferred_lang] > CONSTANTS['PREFERRED_LANG_THRESHOLD']:
                    current_user_lang = await database.get_user_language(thread_id, user_id)
                    if current_user_lang != preferred_lang:
                        await self.handle_new_user_language(thread_id, user_id, preferred_lang)
        except Exception as e:
            logging.error(f"Error updating language preference: {e}")

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

    def create_translation_embed(
        self, 
        message: disnake.Message, 
        original_text: str, 
        translations: Dict[str, str], 
        auto: bool = True
    ) -> Embed:
        embed = Embed(
            title="🌐 Auto-Translations" if auto else "🌐 Translation", 
            color=Color.blue()
        )
        if not auto:
            embed.add_field(
                name="📝 Original", 
                value=f"```{original_text}```", 
                inline=False
            )
        for lang, text in translations.items():
            if text and text.strip():
                display_lang = self._format_language_name(lang)
                embed.add_field(
                    name=f"🔄 {display_lang}", 
                    value=f"```{text}```", 
                    inline=False
                )
        author = message.author
        embed.set_author(
            name=f"{'Translations for' if auto else 'Requested by'} {author.display_name}",
            icon_url=author.avatar.url if author.avatar else None
        )
        embed.set_footer(
            text="⚠️ These translations were generated by an AI language model and may not be perfectly accurate."
        )
        return embed

    async def translation_worker(self):
        while True:
            try:
                job = await self.translation_queue.get()
                try:
                    message, content, target_langs, thread_id, username, user_id = job
                    if message.channel.locked or not await database.is_thread_active(thread_id):
                        continue
                    if not content.strip():
                        continue
                    _, translations = await self.handle_message_translation(
                        content, target_langs, thread_id, username, user_id, message
                    )
                    if translations:
                        embed = self.create_translation_embed(message, content, translations)
                        try:
                            await message.reply(embed=embed, mention_author=False)
                        except disnake.HTTPException as e:
                            logging.error(f"Failed to send translation: {e}")
                except Exception as e:
                    worker_id = id(asyncio.current_task())
                    logging.error(f"Error in worker {worker_id}: {e}")
                finally:
                    self.translation_queue.task_done()
            except Exception as e:
                worker_id = id(asyncio.current_task())
                logging.error(f"Translation worker {worker_id} critical error: {e}")
                await sleep(1)

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        if (message.author.bot or 
            not isinstance(message.channel, disnake.Thread) or
            not await database.is_thread_active(message.channel.id)):
            return
        thread_languages = await database.get_thread_languages(message.channel.id)
        if not thread_languages:
            return
        await self.translation_queue.put((
            message, 
            message.content, 
            set(thread_languages), 
            message.channel.id, 
            message.author.display_name, 
            message.author.id
        ))

    @commands.slash_command(name="translate", description="Translation management commands")
    async def translate_group(self, inter: disnake.ApplicationCommandInteraction):
        pass

    @translate_group.sub_command(name="message", description="Translate a message to another language")
    async def translate_message(self, inter: disnake.ApplicationCommandInteraction):
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
        await inter.response.defer()
        text_to_translate = inter.text_values["text_to_translate"]
        target_lang = inter.text_values["target_language"]
        _, translations = await self.handle_message_translation(
            text_to_translate,
            {target_lang.lower()},
            inter.channel.id if isinstance(inter.channel, disnake.Thread) else 0,
            inter.author.display_name,
            inter.author.id,
            inter
        )
        embed = self.create_translation_embed(inter, text_to_translate, translations, auto=False)
        await inter.edit_original_response(embed=embed)

    @translate_group.sub_command(name="thread", description="Manage thread translation settings")
    async def thread_group(
        self,
        inter: disnake.ApplicationCommandInteraction,
        action: str = commands.Param(choices=["enable", "disable", "status"], description="Action to perform")):
        actions = {
            "enable": self.enable_translation,
            "disable": self.disable_translation,
            "status": self.translation_status
        }
        await actions[action](inter)

    @translate_group.sub_command(name="usage", description="Manage your language usage statistics")
    async def usage_group(
        self,
        inter: disnake.ApplicationCommandInteraction,
        action: str = commands.Param(choices=["view", "reset"], description="Action to perform")):
        actions = {
            "view": self.language_usage_stats,
            "reset": self.reset_usage_stats
        }
        await actions[action](inter)

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
            description = (
                "Auto-translation has been enabled for this thread!\n\n"
                "**How it works**\n"
                "Users' language preference will be automatically detected and used for translations."
            )
            await self._send_embed_response(inter, "🌐 Translation Enabled", description, Color.green(), ephemeral=False)
        except Exception as e:
            logging.error(f"Failed to enable translation in thread {thread_id}: {e}")
            await self._send_embed_response(inter, "❌ Error", "Failed to enable translation. Please try again later.", Color.red())

    async def disable_translation(self, inter: disnake.ApplicationCommandInteraction):
        if not isinstance(inter.channel, disnake.Thread):
            await self._send_embed_response( inter, "❌ Invalid Channel", "This command can only be used in threads!", Color.red())
            return
        thread_id = inter.channel.id
        try:
            if not await database.is_thread_active(thread_id):
                await self._send_embed_response( inter, "❌ Not Active", "Auto-translation is not enabled in this thread!", Color.red())
                return
            await database.set_thread_active(thread_id, False)
            self.thread_histories.pop(thread_id, None)
            await self._send_embed_response( inter, "🌐 Translation Disabled", "Auto-translation has been disabled for this thread.", Color.orange(), ephemeral=False)
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
                formatted_langs = [self._format_language_name(lang) for lang in thread_languages]
                embed.add_field(
                    name="Active Languages",
                    value=", ".join(formatted_langs),
                    inline=False
                )
        await inter.response.send_message(embed=embed, ephemeral=True)

    async def language_usage_stats(self, inter: disnake.ApplicationCommandInteraction):
        user_id = inter.author.id
        if user_id not in self.language_usage:
            await self.load_language_usage(user_id)
        if not self.language_usage[user_id]:
            await self._send_embed_response(inter, "📊 Language Usage Statistics", "No language usage data available yet.", Color.blue())
            return
        total_messages = sum(self.language_usage[user_id].values())
        usage_stats = [
            f"{self._format_language_name(lang)}: {(count / total_messages) * 100:.1f}% ({count} messages)"
            for lang, count in self.language_usage[user_id].items()
        ]
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
        await self._send_embed_response(inter, "📊 Statistics Reset", "Your language usage statistics have been reset.", Color.green())

    async def _send_embed_response(
        self, 
        inter: disnake.ApplicationCommandInteraction,
        title: str,
        description: str,
        color: Color,
        ephemeral: bool = True
    ):
        embed = Embed(title=title, description=description, color=color)
        await inter.response.send_message(embed=embed, ephemeral=ephemeral)

    async def load_language_usage(self, user_id: int):
        try:
            usage_data = await database.get_language_usage(user_id)
            self.language_usage[user_id] = defaultdict(int, usage_data)
        except Exception as e:
            logging.error(f"Error loading language usage for user {user_id}: {e}")
            self.language_usage[user_id] = defaultdict(int)

def setup(bot):
    bot.add_cog(TranslationCog(bot))