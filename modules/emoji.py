# modules.emoji

from modules.utils.database import db_access_with_retry, update_points
from disnake import Embed, Interaction, ActionRow, Button, ButtonStyle
from disnake.ext import commands
from typing import Dict, List
import asyncio
import disnake

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

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_interaction_states()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: disnake.RawReactionActionEvent):
        await self.process_reaction(payload, is_add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: disnake.RawReactionActionEvent):
        await self.process_reaction(payload, is_add=False)

    @commands.Cog.listener()
    async def on_button_click(self, interaction: Interaction):
        await self.process_button_click(interaction)

    async def process_reaction(self, payload: disnake.RawReactionActionEvent, is_add: bool):
        if payload.guild_id is None:
            return
        emoji_name = str(payload.emoji)
        if emoji_name in EMOJI_POINTS:
            await self.process_emoji_points(payload, is_add)
        elif emoji_name in EMOJI_ACTIONS and is_add:
            await getattr(self, EMOJI_ACTIONS[emoji_name])(payload)

    async def process_emoji_points(self, payload: disnake.RawReactionActionEvent, is_add: bool):
        guild = self.bot.get_guild(payload.guild_id)
        reactor = guild.get_member(payload.user_id)
        if not reactor.guild_permissions.administrator:
            return
        user_id = (await self.fetch_message(payload)).author.id
        new_points = await self.update_user_points(user_id, payload.emoji, is_add)
        await self.update_bot_reply(payload, new_points, str(payload.emoji), is_add)

    async def update_user_points(self, user_id: int, emoji: disnake.PartialEmoji, is_add: bool) -> int:
        emoji_name = str(emoji)
        points_to_change = EMOJI_POINTS[emoji_name]
        user_points = await self.get_user_points(user_id)
        new_points = user_points + points_to_change if is_add else user_points - points_to_change
        if await update_points(user_id, new_points):
            return new_points

    async def fetch_message(self, payload: disnake.RawReactionActionEvent):
        channel = self.bot.get_channel(payload.channel_id)
        return await channel.fetch_message(payload.message_id)

    async def update_bot_reply(self, payload: disnake.RawReactionActionEvent, total_points: int, emoji: str, is_add: bool):
        message = await self.fetch_message(payload)
        reply_info = self.bot_replies.get(message.id, {'reply_id': None, 'total_points': 0, 'reasons': []})
        reason = EMOJI_RESPONSES[emoji]
        reason_tuple = (emoji, reason)
        if is_add:
            if reason_tuple not in reply_info['reasons']:
                reply_info['reasons'].append(reason_tuple)
            reply_info['total_points'] += EMOJI_POINTS[emoji]
        else:
            if reason_tuple in reply_info['reasons']:
                reply_info['reasons'].remove(reason_tuple)
            reply_info['total_points'] -= EMOJI_POINTS[emoji]
        embed = await self.create_points_embed(message.author, reply_info['total_points'], reply_info['reasons'])
        await self.edit_or_create_reply(message, reply_info, embed)

    async def edit_or_create_reply(self, message, reply_info, embed):
        channel = message.channel
        if reply_info['reply_id']:
            try:
                reply_message = await channel.fetch_message(reply_info['reply_id'])
                await reply_message.edit(embed=embed)
            except disnake.NotFound:
                reply_info['reply_id'] = None
        if not reply_info['reply_id']:
            reply_message = await message.reply(embed=embed)
            reply_info['reply_id'] = reply_message.id
        self.bot_replies[message.id] = reply_info

    async def send_interaction_error(self, interaction, message):
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)

    def parse_thread_id(self, custom_id: str) -> int:
        try:
            return int(custom_id.split("_")[1])
        except ValueError:
            return None

    async def get_original_poster_id(self, thread_id: int) -> int:
        interaction_data = await db_access_with_retry("SELECT user_id FROM interactions WHERE thread_id = ?", (thread_id,))
        return interaction_data[0][0] if interaction_data else None

    async def create_points_embed(self, user: disnake.User, total_points: int, reasons: List[tuple]) -> Embed:
        title = "Points Updated"
        description = f"{user.display_name} was awarded points for:"
        reasons_text = "\n".join([f"{emoji} for {reason}" for emoji, reason in reasons])
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

    async def handle_checkmark_reaction(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        if not message.thread:
            await channel.send("This message is not part of a thread.")
            return
        thread_id = message.thread.id
        guild = self.bot.get_guild(payload.guild_id)
        thread = disnake.utils.get(guild.threads, id=thread_id)
        original_poster_id = await self.get_original_poster_id(thread_id)
        if not original_poster_id:
            return
        embed = self.create_resolution_embed(original_poster_id)
        action_row = self.create_action_row(thread_id)
        satisfaction_message = await channel.send(embed=embed, components=[action_row])
        await self.save_interaction_data(message.id, original_poster_id, thread_id, satisfaction_message.id, payload.channel_id)
        await self.schedule_reminder(channel, original_poster_id)
        await self.await_user_interaction(channel, original_poster_id, thread)

    def create_resolution_embed(self, user_id):
        embed = Embed(
            title="Resolution of Request/Report",
            description=f"<@{user_id}>, your request or report is considered resolved. Are you satisfied with the resolution?\nThis thread will be closed in 25 hours.",
            color=0x3498db
        )
        embed.set_footer(text="Selecting 'Yes' will close and delete this thread. Selecting 'No' will keep the thread open.")
        return embed

    def create_action_row(self, thread_id):
        return ActionRow(
            Button(style=ButtonStyle.green, label="Yes", custom_id=f"yes_{thread_id}"),
            Button(style=ButtonStyle.red, label="No", custom_id=f"no_{thread_id}")
        )

    async def save_interaction_data(self, message_id, user_id, thread_id, satisfaction_message_id, channel_id):
        await db_access_with_retry(
            "INSERT INTO interactions (message_id, user_id, thread_id, satisfaction_message_id, channel_id) VALUES (?, ?, ?, ?, ?)",
            (message_id, user_id, thread_id, satisfaction_message_id, channel_id)
        )

    async def schedule_reminder(self, channel, user_id):
        async def send_reminder():
            await asyncio.sleep(43200)  # 12 hours
            await channel.send(f"<@{user_id}>, please select an option. If you don't respond within 12 hours from now, the thread will be closed.")
        asyncio.create_task(send_reminder())

    async def await_user_interaction(self, channel, user_id, thread):
        try:
            interaction = await self.bot.wait_for("interaction", timeout=86400, check=lambda i: i.user.id == user_id)
            if interaction.component.label == "Yes":
                if thread:
                    await thread.delete()
            else:
                await interaction.response.send_message(content="We're sorry to hear that. We'll strive to do better.")
                await interaction.message.delete()
        except asyncio.TimeoutError:
            await channel.send(f"<@{user_id}>, you did not select an option within 24 hours. This thread will now be closed.")
            if thread:
                await thread.delete()

    async def process_button_click(self, interaction: Interaction):
        custom_id = interaction.component.custom_id
        if not custom_id.startswith(("yes_", "no_")):
            return
        thread_id = self.parse_thread_id(custom_id)
        if thread_id is None:
            await interaction.response.send_message("Invalid button ID format.", ephemeral=True)
            return
        original_poster_id = await self.get_original_poster_id(thread_id)
        if original_poster_id is None:
            await interaction.response.send_message("No interaction data found.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.administrator and interaction.user.id != 126123710435295232:
            await interaction.response.send_message("You do not have permission to interact with these buttons.", ephemeral=True)
            return
        thread = disnake.utils.get(interaction.guild.threads, id=thread_id)
        if custom_id.startswith("yes_"):
            await self.close_thread(interaction, thread)
        else:
            await self.keep_thread_open(interaction)

    async def close_thread(self, interaction, thread):
        if not interaction.response.is_done():
            await interaction.response.send_message(content="Excellent! We're pleased to know you're satisfied. This thread will now be closed.")
        else:
            await interaction.followup.send(content="Excellent! We're pleased to know you're satisfied. This thread will now be closed.")
        if thread:
            await thread.delete()

    async def keep_thread_open(self, interaction):
        if not interaction.response.is_done():
            await interaction.response.send_message(content="We're sorry to hear that. We'll strive to do better.")
        else:
            await interaction.followup.send(content="We're sorry to hear that. We'll strive to do better.")
        await interaction.message.delete()

    async def load_interaction_states(self):
        interaction_states = await db_access_with_retry("SELECT message_id, user_id FROM interactions")
        for message_id, user_id in interaction_states:
            self.bot_replies[message_id] = {"reply_id": None, "user_id": user_id, "total_points": 0, "reasons": []}