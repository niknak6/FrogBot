# modules.add_remove_points

from modules.utils.progression import calculate_user_rank_and_next_rank_name, create_points_embed, role_thresholds
from modules.utils.database import initialize_points_database, update_points, get_user_points
from modules.roles import check_user_points
from modules.utils.commons import is_admin
from disnake.ext import commands
from disnake import User

class PointsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(description="Add points to a user")
    @is_admin()
    async def add(self, ctx, points: int, user: User, reason: str = None):
        await self.handle_points_command(ctx, points, user, "add", reason)

    @commands.slash_command(description="Remove points from a user")
    @is_admin()
    async def remove(self, ctx, points: int, user: User, reason: str = None):
        await self.handle_points_command(ctx, points, user, "remove", reason)

    async def handle_points_command(self, ctx, points, user, action, reason):
        print(f"{action.capitalize()}ing points: Points: {points}, User: {user}")
        if points < 0:
            print("Invalid points.")
            await ctx.send("Points must be a positive number.")
            return
        await initialize_points_database(user)
        current_points = await get_user_points(user.id)
        new_points = current_points + points if action == "add" else current_points - points
        if await update_points(user.id, new_points):
            await check_user_points(self.bot)
        user_rank, next_rank_name, _, _, _ = await calculate_user_rank_and_next_rank_name(ctx, user, role_thresholds)
        new_embed = await create_points_embed(ctx, user, new_points, role_thresholds, action, user_rank, next_rank_name, points, reason)
        await ctx.send(embed=new_embed)

def setup(bot):
    bot.add_cog(PointsCog(bot))