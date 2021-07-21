import discord
from discord.ext import commands
import typing
import asyncio
from pytz import timezone, UnknownTimeZoneError
from datetime import datetime, timedelta
from datetime import timezone as tz
import re

class BadTimeString(commands.BadArgument):
    pass
class TimeStringConverter(commands.Converter):

    async def convert(self, ctx, argument):
        formats = ["%H:%M", "%H:%M:%S", "%I%p", "%I:%M%p", "%I %p", "%I:%M %p"]
        dt = None
        today_at = None
        for f in formats:
            try:
                dt = datetime.strptime(argument, f)
                today_at = datetime.utcnow().replace(hour=dt.hour, minute=dt.minute, second=dt.second)
                break
            except ValueError:
                continue
        if not dt or not today_at:
            raise BadTimeString("Time format input was invalid", argument)
        else:
            return today_at

class RelativeTime(commands.Converter):
    units = {
            "d": 3600 * 24,
            "h": 3600,
            "m": 60,
            "s": 1
            }
    async def convert(self, ctx: commands.Context, argument: str):
        total_seconds = 0
        for match in re.finditer(r"(?P<amount>\d+)\s?(?P<unit>\w+)", argument):
            amount = match.group("amount")
            unit = match.group("unit").lower()[0]
            total_seconds += int(amount) * self.units.get(unit, 0)
        return datetime.now(tz.utc) + timedelta(seconds=total_seconds)


class Time(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.table_creation = self.bot.loop.create_task(self.create_user_time_entries())
        self.time_format = '%H:%M:%S'
        self.unknown_tz = ("Unknown timezone please refer to this table to find your correct one: "
                "<https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>\n"
                "the format is usually `Region/City`")

    def build_timer_response(self, when: datetime, format_: typing.Optional[str]):
        if format_:
            format_ = f":{format_}"
        else:
            format_ = ""
        return {
                "content": f"`<t:{int(when.timestamp())}{format_}>`", 
                "embed": discord.Embed(description=f"<t:{int(when.timestamp())}{format_}>")
                }
    @commands.group(name="countdown", aliases=["timer"], invoke_without_command=True)
    async def timer(self, ctx: commands.Context, * ,when: RelativeTime):
        """
        Commands for creating a discord time mention give a relative time in format
        `.timer 1h 20m 50s`
        """
        await ctx.send(**self.build_timer_response(when, "R"))

    @timer.command()
    async def default(self, ctx, *, when: RelativeTime):
        """
        create a default time mention (date + time)
        """
        await ctx.send(**self.build_timer_response(when, None))

    @timer.command()
    async def short(self, ctx, *, when: RelativeTime):
        """
        create a short time mention (just time without date)
        """
        await ctx.send(**self.build_timer_response(when, "T"))

    @timer.command()
    async def long(self, ctx, *, when: RelativeTime):
        """
        create a long time mention (weekday, date and time)
        """
        await ctx.send(**self.build_timer_response(when, "F"))

    async def create_user_time_entries(self):
        await self.bot.db.execute("""
            CREATE TABLE IF NOT EXISTS user_tz(
                user_id BIGINT PRIMARY KEY,
                timezone TEXT
            )
        """)

    @commands.group(name="time", invoke_without_command=True)
    async def user_time(self, ctx: commands.Context, user : typing.Optional[discord.Member]):
        """
        show the time of a user if they added their timezone to the database
        """
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
        """
        set your own timezone for tracking check the following list to find the name of your timezone:
        https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
        """
        try:
            tz = timezone(timezone_name)
        except UnknownTimeZoneError:
            return await ctx.send(self.unknown_tz)
        await self.bot.db.execute("INSERT INTO user_tz(user_id, timezone) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET timezone = $2", ctx.author.id, timezone_name)
        await ctx.send(f"I stored your timezone info as `{timezone_name}`")

    @user_time.command(name="now")
    async def time_now(self, ctx, timezone_name):
        """
        get the current time of a timezone see following list for timezone names
        https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
        """
        try:
            tz = timezone(timezone_name)
        except UnknownTimeZoneError:
            return await ctx.send(self.unknown_tz)
        dt = datetime.now(tz=tz)
        await ctx.send(f"the current time of timezone `{timezone_name}` is {dt.strftime(self.time_format)}")
        
    @user_time.command(name="difference")
    async def time_difference(self, ctx, from_, to):
        """
        compare the time difference between two timezones
        https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
        """
        try:
            now = datetime.now()
            tz_from = timezone(from_)
            tz_to = timezone(to)
            dt1 = now.astimezone(tz_from).replace(tzinfo=None)
            dt2 = now.astimezone(tz_to).replace(tzinfo=None)
        except UnknownTimeZoneError:
            return await ctx.send(self.unknown_tz)
        embed = discord.Embed(title=f"Time difference between {from_} and {to}")
        embed.add_field(name=from_, value=dt1.strftime(self.time_format), inline=False)
        embed.add_field(name=to, value=dt2.strftime(self.time_format), inline=False)
        time_diff = dt1 - dt2
        hours, remainder = divmod(int(time_diff.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        embed.add_field(name=f"time difference from {from_} to {to}", value=f"{hours:02}:{minutes:02}:{seconds:02}", inline=False)
        await ctx.send(embed=embed)

    @user_time.command(name="convert")
    async def time_convert(self, ctx, time: TimeStringConverter, from_, to):
        """
        convert one provided time with timezone to another timezone 
        example: `time convert 13:45 Europe/Berlin US/Eastern`
        available input time formats are `13:12:02` `15:22` `"1:45 pm/am"` `12pm/am`
        """
        try:
            tz_from = timezone(from_)
            tz_to = timezone(to)
        except UnknownTimeZoneError:
            return await ctx.send(self.unknown_tz)
        dt_from = tz_from.localize(time)
        dt_utc = dt_from.astimezone(timezone('UTC'))
        dt_to = dt_utc.astimezone(tz_to)
        await ctx.send(f"{dt_from.strftime(self.time_format)} `{from_}` in `{to}` is {dt_to.strftime(self.time_format)}")


def setup(bot):
    bot.add_cog(Time(bot))
