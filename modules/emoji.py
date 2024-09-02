# modules.emoji

from modules.utils.database import db_access_with_retry, update_points
from disnake import Embed, ButtonStyle
from disnake.ui import View, Button
from disnake.ext import commands
from typing import Dict, List
import disnake

ADMIN_USER_ID = 126123710435295232

EMOJI_ACTIONS = {
    "👍": "handle_thumbsup_reaction",
    "👎": "handle_thumbsdown_reaction",
    "✅": "handle_checkmark_reaction"
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
    async def on_raw_reaction_add(self, payload: disnake.RawReactionActionEvent):
        await self.process_reaction(payload, is_add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: disnake.RawReactionActionEvent):
        await self.process_reaction(payload, is_add=False)

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
        message = await self.fetch_message(payload)
        user_id = message.author.id
        new_points = await self.update_user_points(user_id, payload.emoji, is_add)
        await self.update_bot_reply(message, new_points, str(payload.emoji), is_add)

    async def update_user_points(self, user_id: int, emoji: disnake.PartialEmoji, is_add: bool) -> int:
        points_to_change = EMOJI_POINTS[str(emoji)]
        user_points = await self.get_user_points(user_id)
        new_points = user_points + points_to_change if is_add else user_points - points_to_change
        if await update_points(user_id, new_points):
            return new_points

    async def fetch_message(self, payload: disnake.RawReactionActionEvent):
        channel = self.bot.get_channel(payload.channel_id)
        return await channel.fetch_message(payload.message_id)

    async def update_bot_reply(self, message: disnake.Message, total_points: int, emoji: str, is_add: bool):
        reply_info = self.bot_replies.get(message.id, {'reply_id': None, 'total_points': 0, 'reasons': []})
        reason_tuple = (emoji, EMOJI_RESPONSES[emoji])
        if is_add:
            if reason_tuple not in reply_info['reasons']:
                reply_info['reasons'].append(reason_tuple)
            reply_info['total_points'] += EMOJI_POINTS[emoji]
        else:
            if reason_tuple in reply_info['reasons']:
                reply_info['reasons'].remove(reason_tuple)
            reply_info['total_points'] -= EMOJI_POINTS[emoji]
        embed = self.create_points_embed(message.author, reply_info['total_points'], reply_info['reasons'])
        await self.edit_or_create_reply(message, reply_info, embed)

    async def edit_or_create_reply(self, message: disnake.Message, reply_info: Dict, embed: Embed):
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

    async def get_user_points(self, user_id: int) -> int:
        user_points_dict = await db_access_with_retry('SELECT * FROM user_points WHERE user_id = ?', (user_id,))
        return user_points_dict[0][1] if user_points_dict else 0

    def create_points_embed(self, user: disnake.User, total_points: int, reasons: List[tuple]) -> Embed:
        embed = disnake.Embed(
            title="Points Update",
            description=f"{user.display_name} has been awarded points for:",
            color=disnake.Color.green()
        )
        reasons_text = "\n".join([f"{emoji} **{reason}**" for emoji, reason in reasons])
        embed.add_field(name="Reasons", value=reasons_text, inline=False)
        embed.add_field(name="Total Points", value=f"{total_points}", inline=True)
        embed.set_footer(text=f"Updated on {disnake.utils.utcnow().strftime('%Y-%m-%d')} | Use '/check_points' for more info.")
        return embed
    
    async def handle_checkmark_reaction(self, payload: disnake.RawReactionActionEvent):
        guild = self.bot.get_guild(payload.guild_id)
        user = guild.get_member(payload.user_id)
        if user.guild_permissions.administrator or user.id == ADMIN_USER_ID:
            channel = self.bot.get_channel(payload.channel_id)
            if isinstance(channel, disnake.Thread):
                message = await channel.fetch_message(payload.message_id)
                op_user = message.author
                embed = disnake.Embed(
                    title="Resolve Your Issue/Request",
                    description=f"{op_user.mention}, has your issue or request been resolved?\nPlease click **Yes** if it has been resolved, or **No** if it hasn't.\n",
                    color=disnake.Color.green()
                )
                embed.set_footer(text="Note: Clicking 'Yes' will delete this thread.")
                view = self.ResolutionView(message)
                await message.reply(embed=embed, view=view)

    class ResolutionView(View):
        def __init__(self, message):
            super().__init__()
            self.message = message
            yes_button = Button(style=ButtonStyle.green, label="Yes")
            no_button = Button(style=ButtonStyle.red, label="No")
            yes_button.callback = self.on_yes_button_clicked
            no_button.callback = self.on_no_button_clicked
            self.add_item(yes_button)
            self.add_item(no_button)
    
        async def on_yes_button_clicked(self, interaction):
            if interaction.user.id == self.message.author.id:
                if isinstance(self.message.channel, disnake.Thread):
                    await self.message.channel.delete()
                else:
                    await interaction.response.send_message("This action can only delete threads.", ephemeral=True)
            else:
                await interaction.response.send_message("Only the original poster can close this thread.", ephemeral=True)
    
        async def on_no_button_clicked(self, interaction):
            if interaction.user.id == self.message.author.id:
                await interaction.message.edit(embed=self.create_apology_embed())
                self.clear_items()
                await interaction.message.edit(view=self)
            else:
                await interaction.response.send_message("Only the original poster can update this thread.", ephemeral=True)
    
        def create_apology_embed(self):
            embed = disnake.Embed(
                title="Issue Not Resolved",
                description="We're sorry that your issue/request was not resolved. Please provide more details for further assistance.",
                color=disnake.Color.red()
            )
            return embed

def setup(bot):
    bot.add_cog(EmojiCog(bot))