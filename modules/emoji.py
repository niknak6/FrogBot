# modules.emoji

from modules.utils.database import db_access_with_retry, update_points
from disnake import ButtonStyle, Embed, Interaction
from modules.roles import check_user_points
from disnake.ext import commands
from contextlib import suppress
from typing import Dict, List
import disnake
import asyncio

REQUIRED_RANK_ID = 1198482895342411846

EMOJI_ACTIONS = {
    "✅": "handle_checkmark_reaction",
    "👍": "handle_thumbsup_reaction",
    "👎": "handle_thumbsdown_reaction"
}

EMOJI_POINTS = {
    "🐞": 250, "📜": 250, "📹": 500,
    "💡": 100, "🧠": 250, "❤️": 100
}

EMOJI_RESPONSES = {
    "🐞": "their bug report",
    "📜": "submitting an error log",
    "📹": "including footage",
    "💡": "a feature request",
    "🧠": "making sure it was well-thought-out",
    "❤️": "being a good frog"
}

class EmojiCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot_replies: Dict[int, Dict] = {}

    async def process_reaction(self, payload: disnake.RawReactionActionEvent, is_add: bool) -> None:
        if payload.guild_id is None:
            return
        emoji_name = str(payload.emoji)
        print(f"Processing reaction: {emoji_name}, is_add: {is_add}")
        if emoji_name in EMOJI_POINTS:
            await self.process_emoji_reaction(payload, is_add)
        elif emoji_name in EMOJI_ACTIONS and is_add:
            await getattr(self, EMOJI_ACTIONS[emoji_name])(payload)

    async def process_emoji_reaction(self, payload: disnake.RawReactionActionEvent, is_add: bool) -> None:
        guild = self.bot.get_guild(payload.guild_id)
        reactor = guild.get_member(payload.user_id)
        if not reactor.guild_permissions.administrator:
            return
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        user_id = message.author.id
        user_points = await self.get_user_points(user_id)
        points_to_change = EMOJI_POINTS[str(payload.emoji)]
        new_points = user_points + points_to_change if is_add else user_points - points_to_change
        if await update_points(user_id, new_points):
            await check_user_points(self.bot)
        await self.manage_bot_response(payload, points_to_change, str(payload.emoji), is_add)

    async def handle_thumbsup_reaction(self, payload: disnake.RawReactionActionEvent) -> None:
        await self.handle_reaction(payload, "Thumbs up", "Thank you for your positive feedback!")

    async def handle_thumbsdown_reaction(self, payload: disnake.RawReactionActionEvent) -> None:
        await self.handle_reaction(payload, "Thumbs down", "We're sorry to hear that. We'll strive to do better.")

    async def handle_checkmark_reaction(self, payload: disnake.RawReactionActionEvent) -> None:
        print(f"handle_checkmark_reaction called. Payload: {payload}")
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        thread = channel if isinstance(channel, disnake.Thread) else message.thread
        if not thread:
            print(f"Error: No thread found for message {message.id}")
            return
        embed = Embed(
            title="Resolution of Request/Report",
            description=f"<@{message.author.id}>, your request or report is considered resolved. Are you satisfied with the resolution?\nThis thread will be closed in 24 hours.",
            color=0x3498db
        )
        embed.set_footer(text="Selecting 'Yes' will close and delete this thread. Selecting 'No' will keep the thread open.")
        action_row = disnake.ui.ActionRow(
            disnake.ui.Button(style=ButtonStyle.green, label="Yes", custom_id=f"yes_{thread.id}"),
            disnake.ui.Button(style=ButtonStyle.red, label="No", custom_id=f"no_{thread.id}")
        )
        try:
            satisfaction_message = await thread.send(embed=embed, components=[action_row])
            print(f"Satisfaction message sent: {satisfaction_message.id}")
            db_access_with_retry(
                "INSERT INTO interactions (message_id, user_id, thread_id, satisfaction_message_id, channel_id) VALUES (?, ?, ?, ?, ?)",
                (message.id, message.author.id, thread.id, satisfaction_message.id, payload.channel_id)
            )
            print("Interaction data inserted into database")
            await self.wait_for_user_response(thread, message.author.id, satisfaction_message)
        except Exception as e:
            print(f"Error in handle_checkmark_reaction: {e}")

    async def process_close(self, payload: disnake.RawReactionActionEvent) -> None:
        print(f"process_close called with payload: {payload}")
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        print(f"Channel type: {channel.type}, Message author ID: {message.author.id}")
        if isinstance(channel, disnake.Thread):
            print(f"Checkmark in thread. Reactor ID: {payload.user_id}")
            if payload.member.guild_permissions.administrator or payload.user_id == 126123710435295232:
                print("User has permission to close. Calling handle_checkmark_reaction")
                await self.handle_checkmark_reaction(payload)
            else:
                print("User does not have permission to close")
        else:
            print(f"Not a thread. Channel type: {channel.type}")

    async def handle_reaction(self, payload: disnake.RawReactionActionEvent, reaction_type: str, reply_message: str) -> None:
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        if message.author == self.bot.user:
            guild = self.bot.get_guild(payload.guild_id)
            member = guild.get_member(payload.user_id)
            if any(role.id >= REQUIRED_RANK_ID for role in member.roles):
                print(f"{reaction_type} reaction received from user {payload.user_id}")
                await message.reply(reply_message)

    async def wait_for_user_response(self, thread: disnake.Thread, user_id: int, satisfaction_message: disnake.Message) -> None:
        async def send_reminder():
            await asyncio.sleep(43200)
            await thread.send(f"<@{user_id}>, please select an option. If you don't respond within 12 hours from now, the thread will be closed.")
        reminder_task = asyncio.create_task(send_reminder())
        try:
            interaction = await self.bot.wait_for(
                "button_click",
                timeout=86400,
                check=lambda i: i.message.id == satisfaction_message.id and i.user.id == user_id
            )
            if interaction.component.custom_id.startswith("yes"):
                await interaction.response.send_message(content="Excellent! We're pleased to know you're satisfied. This thread will now be closed.")
                await asyncio.sleep(5)
                await thread.delete()
            else:
                await interaction.response.send_message(content="We're sorry to hear that. We'll strive to do better.")
                await satisfaction_message.delete()
                with suppress(asyncio.CancelledError):
                    reminder_task.cancel()
        except asyncio.TimeoutError:
            await thread.send(f"<@{user_id}>, you did not select an option within 24 hours. This thread will now be closed.")
            await asyncio.sleep(5)
            await thread.delete()
        finally:
            with suppress(asyncio.CancelledError):
                reminder_task.cancel()
            db_access_with_retry("DELETE FROM interactions WHERE thread_id = ?", (thread.id,))

    async def manage_bot_response(self, payload: disnake.RawReactionActionEvent, points_to_change: int, emoji_name: str, is_add: bool) -> None:
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        bot_reply_info = self.bot_replies.get(message.id, {'reply_id': None, 'total_points': 0, 'reasons': []})
        reason = EMOJI_RESPONSES[emoji_name]
        if is_add:
            if reason not in bot_reply_info['reasons']:
                bot_reply_info['reasons'].append(reason)
            total_points = bot_reply_info['total_points'] + points_to_change
        else:
            if reason in bot_reply_info['reasons']:
                bot_reply_info['reasons'].remove(reason)
            total_points = bot_reply_info['total_points'] - points_to_change
        embed = self.create_points_embed(message.author, total_points, bot_reply_info['reasons'], emoji_name)
        if bot_reply_info['reply_id']:
            try:
                bot_reply_message = await channel.fetch_message(bot_reply_info['reply_id'])
                await bot_reply_message.edit(embed=embed)
            except disnake.NotFound:
                bot_reply_info['reply_id'] = None
        if not bot_reply_info['reply_id']:
            bot_reply_message = await message.reply(embed=embed)
            bot_reply_info['reply_id'] = bot_reply_message.id
        self.bot_replies[message.id] = {'reply_id': bot_reply_message.id, 'total_points': total_points, 'reasons': bot_reply_info['reasons']}

    def create_points_embed(self, user: disnake.User, total_points: int, reasons: List[str], emoji_name: str) -> Embed:
        title = f"Points Updated: {emoji_name}"
        description = f"{user.display_name} was awarded points for:"
        reason_to_emoji = {reason: emoji for emoji, reason in EMOJI_RESPONSES.items()}
        reasons_text = "\n".join([f"{reason_to_emoji.get(reason, '❓')} for {reason}" for reason in reasons])
        embed = disnake.Embed(
            title=title,
            description=description,
            color=disnake.Color.green()
        )
        embed.add_field(name="Reasons", value=reasons_text, inline=False)
        embed.add_field(name="Total Points", value=f"{total_points}", inline=True)
        embed.set_footer(text=f"Updated on {disnake.utils.utcnow().strftime('%Y-%m-%d')} | '/check_points' for more info.")
        return embed

    async def get_user_points(self, user_id: int) -> int:
        user_points_dict = await db_access_with_retry('SELECT * FROM user_points WHERE user_id = ?', (user_id,))
        return user_points_dict[0][1] if user_points_dict else 0

    async def load_interaction_states(self) -> None:
        interaction_states = await db_access_with_retry("SELECT message_id, user_id, thread_id, satisfaction_message_id, channel_id FROM interactions")
        for state in interaction_states:
            message_id, user_id, thread_id, satisfaction_message_id, channel_id = state
            asyncio.create_task(self.resume_interaction(message_id, user_id, thread_id, satisfaction_message_id, channel_id))

    async def resume_interaction(self, message_id: int, user_id: int, thread_id: int, satisfaction_message_id: int, channel_id: int) -> None:
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return
        try:
            satisfaction_message = await channel.fetch_message(satisfaction_message_id)
            thread = disnake.utils.get(channel.guild.threads, id=thread_id)
            await self.wait_for_user_response(thread, user_id, satisfaction_message)
        except Exception as e:
            print(f"Error resuming interaction: {e}")
            db_access_with_retry("DELETE FROM interactions WHERE thread_id = ?", (thread_id,))

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.load_interaction_states()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: disnake.RawReactionActionEvent) -> None:
        await self.process_reaction(payload, is_add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: disnake.RawReactionActionEvent) -> None:
        await self.process_reaction(payload, is_add=False)

    @commands.Cog.listener()
    async def on_button_click(self, interaction: Interaction) -> None:
        custom_id = interaction.component.custom_id
        if not custom_id.startswith(("yes_", "no_")):
            return
        try:
            thread_id = int(custom_id.split("_")[1])
        except ValueError:
            await interaction.response.send_message("Error: Invalid button ID format.", ephemeral=True)
            return
        interaction_data = db_access_with_retry("SELECT user_id FROM interactions WHERE thread_id = ?", (thread_id,))
        if not interaction_data:
            await interaction.response.send_message("Error: No interaction data found.", ephemeral=True)
            return
        original_poster_id = interaction_data[0][0]
        if interaction.user.id != original_poster_id:
            await interaction.response.send_message("Only the thread creator can interact with these buttons.", ephemeral=True)
            return
        thread = disnake.utils.get(interaction.guild.threads, id=thread_id)
        if custom_id.startswith("yes_"):
            await interaction.response.send_message(content="Excellent! We're pleased to know you're satisfied. This thread will now be closed.")
            if thread:
                await thread.delete()
        else:
            await interaction.response.send_message(content="We're sorry to hear that. We'll strive to do better.")
            await interaction.message.delete()
            db_access_with_retry("DELETE FROM interactions WHERE thread_id = ?", (thread_id,))

def setup(bot: commands.Bot) -> None:
    bot.add_cog(EmojiCog(bot))