# modules.check_points

from modules.utils.progression import create_progress_bar, calculate_user_rank_and_next_rank_name, role_thresholds
from modules.utils.database import initialize_points_database, get_user_points, db_access_with_retry
from disnake.ext import commands
from disnake import User
import datetime
import disnake

class CheckPointsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_user(self, ctx, args):
        if len(args) > 1 and ctx.message.author.guild_permissions.administrator:
            try:
                return await commands.UserConverter().convert(ctx, args[1])
            except commands.UserNotFound:
                await ctx.send("User not found.")
                return None
        return ctx.author

    @commands.slash_command(description="Check points")
    async def check_points(self, ctx, user: User = None):
        if not ctx.guild:
            await ctx.send("This command can only be used in a guild.")
            return
        user = user or ctx.author
        if not (ctx.author == user or ctx.author.guild_permissions.administrator):
            await ctx.send("Invalid syntax. Please use '/check points [@user]'.")
            return
        await initialize_points_database(user)
        user_points = await get_user_points(user.id)
        if not isinstance(user_points, int):
            await ctx.send("Error: User points data is not in the expected format.")
            return
        all_users_points = await self.get_all_users_points()
        sorted_users = sorted(all_users_points.items(), key=lambda x: x[1], reverse=True)
        user_rank = next((index for index, (u_id, _) in enumerate(sorted_users) if u_id == user.id), -1)
        embed = await self.create_embed(ctx, user, sorted_users, user_rank)
        await ctx.send(embed=embed)

    async def get_all_users_points(self):
        rows = await db_access_with_retry('SELECT user_id, points FROM user_points')
        return {user_id: points for user_id, points in rows}

    async def create_embed(self, ctx, user, sorted_users, user_rank):
        start_index = max(0, user_rank - 2)
        end_index = min(len(sorted_users), start_index + 5) if start_index < 2 else min(start_index + 5, len(sorted_users))
        embed = disnake.Embed(
            title="**🏆 Your Current Standing**",
            description="Here's your current points, rank, etc.",
            color=disnake.Color.gold()
        )
        embed.set_footer(text=f"Leaderboard as of {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
        for index in range(start_index, end_index):
            field = await self.create_embed_field(ctx, user, sorted_users, index)
            if field:
                embed.add_field(name="\u200b", value=field, inline=False)
        return embed

    async def create_embed_field(self, ctx, user, sorted_users, index):
        user_id, points = sorted_users[index]
        member = ctx.guild.get_member(user_id)
        if not member:
            return None
        display_name = member.display_name
        _, next_rank_name, points_needed, current_threshold, next_threshold = await calculate_user_rank_and_next_rank_name(ctx, member, role_thresholds)
        progress_length = next_threshold - current_threshold
        progress_current = points - current_threshold
        progress_bar = create_progress_bar(progress_current, progress_length)
        rank_emoji = ["🥇", "🥈", "🥉"][index] if index < 3 else f"#{index + 1}"
        rank_text = f"{rank_emoji} | {'***__' if user_id == user.id else ''}{display_name}: {points:,} points{'__***' if user_id == user.id else ''}\nProgress: {progress_bar} ({points_needed:,} pts to {next_rank_name})"
        return rank_text

def setup(bot):
    bot.add_cog(CheckPointsCog(bot))