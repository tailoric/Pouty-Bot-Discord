from discord.ext import commands
from discord.utils import get
from .utils import checks
import asyncio
import typing
from datetime import datetime, timedelta


class MemeOff(commands.Cog):
    """Command suite for Animemes meme-offs only"""
    def __init__(self, bot):
        self.bot = bot
        self.timer_task = None
        self.timer_timestamp = None

    @commands.group(name="meme-off", aliases=["meme_off", "memeoff", "mo"])
    async def meme_off(self, ctx):
        """
        command suite for organizing and doing meme offs
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(self.meme_off)

    @commands.has_any_role("Subreddit-Senpai", "Discord-Senpai")
    @checks.channel_only("memeoff")
    @meme_off.command(name="ping")
    async def meme_off_ping(self, ctx, *, announcement: typing.Optional[str]):
        """
        ping the meme-off role
        """
        meme_off_role = get(ctx.guild.roles, name="MEMEOFF")
        message_to_send = (f"{meme_off_role.mention} new meme off will start soon react to this message to "
                           f"participate")
        if announcement:
            message_to_send = f"{meme_off_role.mention} {announcement}"
        if meme_off_role:
            await meme_off_role.edit(mentionable=True)
            await ctx.send(message_to_send)
            await meme_off_role.edit(mentionable=False)

    @checks.channel_only("memeoff")
    @meme_off.command(name="start")
    async def meme_off_start(self, ctx, *, round_duration: str):
        """
        create a timer for the current round [typical inputs are 30 minutes or 60 minutes]
        """
        if self.timer_task is not None:
            if not self.timer_task.cancelled() or not self.timer_task.done():
                return await ctx.send("There is already a timer running. Cancel it with `.meme-off cancel` first")
        if round_duration.endswith("s"):
            round_duration = round_duration[:-1]
        time_units = {"hour": 3600, "minute": 60, "second": 1}
        amount, unit = round_duration.split(" ")
        if unit not in time_units.keys():
            return await ctx.send(f"No valid time unit the only available units are:\n{', '.join(time_units.keys())}")
        delay = int(amount) * time_units[unit]
        await ctx.send(f"Timer set to {amount} {unit}(s)")
        self.timer_task = self.bot.loop.create_task(self.timer(delay, ctx))

    @checks.channel_only("memeoff")
    @meme_off.command(name="deadline", aliases=["dl"])
    async def meme_off_deadline(self, ctx):
        """ see how much time is left until the current deadline is over"""
        if not self.timer_timestamp:
            return await ctx.send("No timer set currently")
        time_diff = self.timer_timestamp - datetime.utcnow()
        minutes, seconds = divmod(time_diff.seconds, 60)
        await ctx.send(f"{minutes} minutes and {seconds} seconds left")

    @checks.channel_only("memeoff")
    @meme_off.command(name="cancel")
    async def meme_off_cancel(self, ctx):
        """
        cancel the current timer
        """
        self.timer_task.cancel()
        self.timer_task = None
        self.timer_timestamp = None
        await ctx.send("Timer was cancelled")

    async def timer(self, delay, ctx):
        self.timer_timestamp = datetime.utcnow() + timedelta(seconds=delay)
        await asyncio.sleep(delay)
        await ctx.send("Round has finished now.")
        self.timer_task = None
        self.timer_timestamp = None


def setup(bot):
    bot.add_cog(MemeOff(bot))

