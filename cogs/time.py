import discord
from discord.ext import commands
import typing
import asyncio
from pytz import timezone, UnknownTimeZoneError
from datetime import datetime

class Time(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.table_creation = self.bot.loop.create_task(self.create_user_time_entries())
        self.time_format = '%H:%M:%S'

    async def create_user_time_entries(self):
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS user_tz(
                user_id BIGINT PRIMARY KEY,
                timezone TEXT
            )
        """)

    @commands.group(name="time", invoke_without_command=True)
    async def user_time(self, ctx: commands.Context, user : typing.Optional[discord.Member]):
        await asyncio.wait_for(self.table_creation, timeout=None)
        if not user:
            user = ctx.author
        tz = await self.bot.db.fetchval("SELECT timezone from user_tz WHERE user_id = $1", user.id)
        if not tz:
            return await ctx.send("User has not stored their timezone here")            
        dt = datetime.now(tz=timezone(tz))
        await ctx.send(f"{user.mention}'s current time is: {dt.strftime(self.time_format)}", allowed_mentions=discord.AllowedMentions.none())

    @user_time.command(name="set")
    async def user_time_set(self, ctx, timezone_name):
        try:
            tz = timezone(timezone_name)
        except UnknownTimeZoneError:
            return await ctx.send("Unknown timezone please refer to this table to find your correct one: "
                    "<https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>\n"
                    "the format is `Country/City`")
        await self.bot.db.execute("INSERT INTO user_tz(user_id, timezone) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET timezone = $2", ctx.author.id, timezone_name)
        await ctx.send(f"I stored your timezone info as `{timezone_name}`")

    @user_time.command(name="now")
    async def time_now(self, ctx, timezone_name):
        try:
            tz = timezone(timezone_name)
        except UnknownTimeZoneError:
            return await ctx.send("Unknown timezone please refer to this table to find your correct one: "
                    "<https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>\n"
                    "the format is `Country/City`")
        dt = datetime.now(tz=tz)
        await ctx.send(f"the current time of timezone `{timezone_name}` is {dt.strftime(self.time_format)}")
        
    @user_time.command(name="convert")
    async def time_convert(self, ctx, from_, to):
        try:
            now = datetime.now()
            tz_from = timezone(from_)
            tz_to = timezone(to)
            dt1 = now.astimezone(tz_from).replace(tzinfo=None)
            dt2 = now.astimezone(tz_to).replace(tzinfo=None)
        except UnknownTimeZoneError:
            return await ctx.send("Unknown timezone please refer to this table to find your correct one: "
                    "<https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>\n"
                    "the format is `Country/City`")
        embed = discord.Embed(title=f"Time difference between {from_} and {to}")
        embed.add_field(name=from_, value=dt1.strftime(self.time_format), inline=False)
        embed.add_field(name=to, value=dt2.strftime(self.time_format), inline=False)
        time_diff = dt1 - dt2
        hours, remainder = divmod(int(time_diff.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        embed.add_field(name=f"time difference from {from_} to {to}", value=f"{hours:02}:{minutes:02}:{seconds:02}", inline=False)
        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(Time(bot))
