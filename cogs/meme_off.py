from discord.ext import commands
from discord.utils import get
from .utils import checks
import asyncio
import typing
from datetime import datetime, timedelta
import random

class TemplateSubmission():

    def __init__(self, user_id):
        self.user_id = user_id
        self.templates = []

    def add_template(self, template_link):
        self.templates.append(template_link)

    def get_template(self):
        if self.templates:
            choice = random.choice(self.templates)
            self.templates.remove(choice)
            return choice
        return None

    def __eq__(self, other):
        if isinstance(other, TemplateSubmission):
            return self.user_id == other.user_id
        return false


class MemeOff(commands.Cog):
    """Command suite for Animemes meme-offs only"""
    def __init__(self, bot):
        self.bot = bot
        self.timer_task = None
        self.timer_timestamp = None
        self.submitted_templates = {}
        self.template_order = None

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

    @commands.dm_only()
    @meme_off.command("submit")
    async def meme_off_submit(self, ctx, link: typing.Optional[str]):
        """
        **ONLY IN DMs:** add a template to the random rotation, file needs to be attached for this command
        """
        if ctx.message.attachments:
            template_submission = self.submitted_templates.get(ctx.author.id, None)
            if not template_submission:
                template_submission = TemplateSubmission(ctx.author.id)

            template_submission.add_template(ctx.message.attachments[0].url)
            self.submitted_templates[ctx.author.id] = template_submission
            await ctx.send("template successfully submitted")
        elif link:
            template_submission = self.submitted_templates.get(ctx.author.id, None)
            if not template_submission:
                template_submission = TemplateSubmission(ctx.author.id)

            template_submission.add_template(link)
            self.submitted_templates[ctx.author.id] = template_submission
            await ctx.send("template successfully submitted")
        else:
            return await ctx.send("You need to attach a file to your message or provide a link")

    @checks.channel_only("memeoff")
    @meme_off.command(name="template", aliases=["temp"])
    async def meme_off_template(self, ctx):
        """get a random submission from the template rotation"""
        if not self.template_order:
            if not self.submitted_templates:
                return await ctx.send("No templates submitted")
            self.template_order = [u for u in self.submitted_templates.keys()]
            random.shuffle(self.template_order)
        submission = self.submitted_templates[self.template_order.pop()]
        template = submission.get_template()
        while not template:
            if len(self.template_order) == 0:
                break
            submission = self.submitted_templates[self.template_order.pop()]
            template = submission.get_template()
        if not template:
            return await ctx.send("no templates left")
        await ctx.send(f"Template for this round from <@{submission.user_id}> is:\n{template}")

    @commands.has_any_role("Subreddit-Senpai", "Discord-Senpai")
    @checks.channel_only("memeoff")
    @meme_off.command(name="delete_templates", aliases=["deltemplates", "delTemplates", "delete"])
    async def meme_off_templates_reset(self, ctx):
        """ remove all template submissions"""
        self.submitted_templates = {}
        await ctx.send("all templates removed")

def setup(bot):
    bot.add_cog(MemeOff(bot))

