# modules.emoji

from disnake import Button, ButtonStyle, ActionRow, Interaction, Embed, ChannelType
from modules.utils.database import db_access_with_retry, update_points
from modules.roles import check_user_points
from disnake.ext import commands
from contextlib import suppress
import datetime
import asyncio
import disnake

bot_replies = {}

emoji_actions = {
    "✅": "handle_checkmark_reaction",
    "👍": "handle_thumbsup_reaction",
    "👎": "handle_thumbsdown_reaction"
}

emoji_points = {
    "🐞": 250,
    "📜": 250,
    "📹": 500,
    "💡": 100,
    "🧠": 250,
    "❤️": 100
}

emoji_responses = {
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

    async def handle_reaction(self, payload, reaction_type, reply_message):
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)

        if message.author != self.bot.user:
            return

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        required_rank_id = 1198482895342411846

        if not any(role.id >= required_rank_id for role in member.roles):
            return

        print(f"{reaction_type} reaction received from user {payload.user_id}")
        await message.reply(reply_message)

    async def handle_thumbsup_reaction(self, payload):
        await self.handle_reaction(payload, "Thumbs up", "Thank you for your positive feedback!")

    async def handle_thumbsdown_reaction(self, payload):
        await self.handle_reaction(payload, "Thumbs down", "We're sorry to hear that. We'll strive to do better.")

    async def process_close(self, payload):
        if payload.user_id == self.bot.user.id or payload.guild_id is None:
            return
        emoji_name = str(payload.emoji)
        if emoji_name not in emoji_actions:
            return
        message = await self.bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
        if emoji_name == "✅" and ChannelType.forum and (payload.member.guild_permissions.administrator or payload.user_id == 126123710435295232):
            await self.handle_checkmark_reaction(payload, message.author.id)

    async def handle_checkmark_reaction(self, payload, original_poster_id):
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        thread_id = message.thread.id
        guild = self.bot.get_guild(payload.guild_id)
        thread = disnake.utils.get(guild.threads, id=thread_id)
        embed = Embed(
            title="Resolution of Request/Report",
            description=f"<@{original_poster_id}>, your request or report is considered resolved. Are you satisfied with the resolution?\nThis thread will be closed in 24 hours.",
            color=0x3498db
        )
        embed.set_footer(text="Selecting 'Yes' will close and delete this thread. Selecting 'No' will keep the thread open.")
        action_row = disnake.ui.ActionRow(
            disnake.ui.Button(style=ButtonStyle.green, label="Yes", custom_id=f"yes_{thread_id}"),
            disnake.ui.Button(style=ButtonStyle.red, label="No", custom_id=f"no_{thread_id}")
        )
        satisfaction_message = await channel.send(embed=embed, components=[action_row])
        db_access_with_retry(
            "INSERT INTO interactions (message_id, user_id, thread_id, satisfaction_message_id, channel_id) VALUES (?, ?, ?, ?, ?)",
            (message.id, original_poster_id, thread_id, satisfaction_message.id, payload.channel_id)
        )

        async def send_reminder():
            await asyncio.sleep(43200)
            await channel.send(f"<@{original_poster_id}>, please select an option. If you don't respond within 12 hours from now, the thread will be closed.")

        reminder_task = asyncio.create_task(send_reminder())

        try:
            interaction = await self.bot.wait_for("interaction", timeout=86400, check=lambda i: i.user.id == original_poster_id)
            if interaction.component.label == "Yes":
                if thread:
                    await thread.delete()
            else:
                await interaction.response.send_message(content="We're sorry to hear that. We'll strive to do better.")
                await interaction.message.delete()
        except asyncio.TimeoutError:
            await channel.send(f"<@{original_poster_id}>, you did not select an option within 24 hours. This thread will now be closed.")
            if thread:
                await thread.delete()
        finally:
            with suppress(asyncio.CancelledError):
                reminder_task.cancel()

    async def process_emoji_reaction(self, payload):
        guild = self.bot.get_guild(payload.guild_id)
        reactor = guild.get_member(payload.user_id)
        if not reactor.guild_permissions.administrator:
            return
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        user_id = message.author.id
        user_points = self.get_user_points(user_id)
        points_to_add = emoji_points[str(payload.emoji)]
        new_points = user_points + points_to_add
        if await update_points(user_id, new_points):
            await check_user_points(self.bot)
        await self.manage_bot_response(payload, points_to_add, str(payload.emoji))

    async def process_reaction(self, payload):
        if payload.guild_id is None:
            return
        emoji_name = str(payload.emoji)
        if emoji_name in emoji_points:
            await self.process_emoji_reaction(payload)
        elif emoji_name in emoji_actions:
            if emoji_name == "✅":
                await self.process_close(payload)
            else:
                function_name = emoji_actions[emoji_name]
                function = getattr(self, function_name)
                await function(payload)

    def get_user_points(self, user_id):
        user_points_dict = db_access_with_retry('SELECT * FROM user_points WHERE user_id = ?', (user_id,))
        return user_points_dict[0][1] if user_points_dict else 0

    async def manage_bot_response(self, payload, points_to_add, emoji_name):
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        bot_reply_info = bot_replies.get(message.id, {'reply_id': None, 'total_points': 0, 'reasons': []})
        if emoji_responses[emoji_name] not in bot_reply_info['reasons']:
            bot_reply_info['reasons'].append(emoji_responses[emoji_name])
        total_points = bot_reply_info['total_points'] + points_to_add
        embed = self.create_points_embed(message.author, total_points, bot_reply_info['reasons'], emoji_name)
        if bot_reply_info['reply_id']:
            try:
                bot_reply_message = await channel.fetch_message(bot_reply_info['reply_id'])
                await bot_reply_message.edit(embed=embed)
            except disnake.NotFound:
                bot_reply_info['reply_id'] = None
        if not bot_reply_info['reply_id']:
            if message.id in bot_replies:
                bot_reply_message = await channel.fetch_message(bot_replies[message.id]['reply_id'])
                await bot_reply_message.edit(embed=embed)
            else:
                bot_reply_message = await message.reply(embed=embed)
                bot_reply_info['reply_id'] = bot_reply_message.id
        bot_replies[message.id] = {'reply_id': bot_reply_message.id, 'total_points': total_points, 'reasons': bot_reply_info['reasons']}

    def create_points_embed(self, user, total_points, reasons, emoji_name):
        title = f"Points Updated: {emoji_name}"
        description = f"{user.display_name} was awarded points for:"
        reason_to_emoji = {reason: emoji for emoji, reason in emoji_responses.items()}
        reasons_text = "\n".join([f"{reason_to_emoji.get(reason, '❓')} for {reason}" for reason in reasons])
        embed = disnake.Embed(
            title=title,
            description=description,
            color=disnake.Color.green()
        )
        embed.add_field(name="Reasons", value=reasons_text, inline=False)
        embed.add_field(name="Total Points", value=f"{total_points}", inline=True)
        embed.set_footer(text=f"Updated on {datetime.datetime.now().strftime('%Y-%m-%d')} | '/check_points' for more info.")
        return embed

    async def load_interaction_states(self):
        interaction_states = db_access_with_retry("SELECT message_id, user_id, thread_id, satisfaction_message_id, channel_id FROM interactions")
        for state in interaction_states:
            message_id, user_id, thread_id, satisfaction_message_id, channel_id = state
            asyncio.create_task(self.resume_interaction(message_id, user_id, thread_id, satisfaction_message_id, channel_id))

    async def resume_interaction(self, message_id, user_id, thread_id, satisfaction_message_id, channel_id):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return
        try:
            satisfaction_message = await channel.fetch_message(satisfaction_message_id)
        except Exception as e:
            print(f"Error fetching message: {e}")
            return

        async def send_reminder():
            await asyncio.sleep(43200)
            await channel.send(f"<@{user_id}>, please select an option.")

        reminder_task = asyncio.create_task(send_reminder())

        try:
            interaction = await self.bot.wait_for("interaction", timeout=86400, check=lambda i: i.user.id == user_id)
            thread = disnake.utils.get(channel.guild.threads, id=thread_id)
            if hasattr(interaction, 'message') and interaction.message.id == satisfaction_message.id:
                if interaction.component.label == "Yes":
                    await interaction.response.send_message(content="Excellent! We're pleased to know you're satisfied. This thread will now be closed.")
                    if thread:
                        await thread.delete()
                else:
                    await interaction.response.send_message(content="We're sorry to hear that. We'll strive to do better.")
                    await interaction.message.delete()
            else:
                await interaction.response.send_message(content="We're sorry, there was an error processing your response.")
        except asyncio.TimeoutError:
            if thread:
                await thread.delete()
        finally:
            with suppress(asyncio.CancelledError):
                reminder_task.cancel()
            db_access_with_retry("DELETE FROM interactions WHERE thread_id = ?", (thread_id,))

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_interaction_states()
        print('Interaction states are loaded.')

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        await self.process_reaction(payload)

    @commands.Cog.listener()
    async def on_button_click(self, interaction: Interaction):
        custom_id = interaction.component.custom_id
        if not custom_id.startswith("yes_") and not custom_id.startswith("no_"):
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

def setup(bot):
    bot.add_cog(EmojiCog(bot))
