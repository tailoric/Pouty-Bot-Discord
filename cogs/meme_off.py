import discord
from discord.ext import commands
from discord.utils import get
from .utils import checks, paginator
import asyncio
import aiohttp
import io
import typing
from datetime import datetime, timedelta
import random
from itertools import groupby

class TemplateSubmission():

    def __init__(self, user_id):
        self.user_id = user_id
        self.templates = []

    def add_template(self, template_link):
        self.templates.append(template_link)

    @property
    def has_template(self):
        return len(self.templates) > 0

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
        self.create_table = self.bot.loop.create_task(self.initialize_table())
        if not hasattr(self.bot, 'meme_off_timer'):
            self.bot.meme_off_timer = None
        if not hasattr(self.bot, 'meme_off_timer_timestamp'):
            self.bot.meme_off_timer_timestamp = None
        if not hasattr(self.bot, 'submitted_templates'):
            self.bot.submitted_templates = {}
            self.bot.loop.create_task(self.load_templates())
        self.template_order = None
        if not hasattr(self.bot, 'pinned_template'):
            self.bot.pinned_template = None
            self.bot.pinned_by = None
        self.session = aiohttp.ClientSession()

    
    async def initialize_table(self):
        await self.bot.db.execute("""
        CREATE TABLE IF NOT EXISTS meme_off_templates(
            user_id BIGINT NOT NULL,
            link TEXT
        )
        """)

    async def load_templates(self):
        await asyncio.wait_for(self.create_table, timeout=None)
        results = await self.bot.db.fetch("""
            SELECT * FROM meme_off_templates
        """)
        grouped_templates = groupby(results, key=lambda r: r['user_id'])
        for user, templates in grouped_templates:
            template_submission = self.bot.submitted_templates.get(user, TemplateSubmission(user))
            for template in templates:
                template_submission.add_template(template['link'])
            self.bot.submitted_templates[user] = template_submission

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    @commands.group(name="meme-off", aliases=["meme_off", "memeoff", "mo"])
    @checks.channel_only("memeoff")
    async def meme_off(self, ctx):
        """
        command suite for organizing and doing meme offs
        """
        message_parts = ctx.message.content.split()
        if len(message_parts) > 1 and ctx.invoked_subcommand is None:
            return await ctx.send(f"No subcommand `{message_parts[1]}` found, use `{ctx.prefix}mo help` for more help.")

    @meme_off.command(name="help")
    async def meme_off_help(self, ctx):
        """
        sends this help message
        """
        await ctx.send_help(self.meme_off)
    @commands.has_any_role("Subreddit-Senpai", "Discord-Senpai")
    @commands.guild_only()
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

    @commands.guild_only()
    @meme_off.command(name="start")
    async def meme_off_start(self, ctx, *, round_duration: str):
        """
        create a timer for the current round [typical inputs are 30 minutes or 60 minutes]
        If done in reply to a message then it will also pin that message (for pinning the template)
        """
        if ctx.message.reference and not self.bot.pinned_template:
            message = await self.fetch_message(ctx)
            await message.pin()
            self.bot.pinned_template = message
            self.bot.pinned_by = ctx.author
        if self.bot.meme_off_timer is not None:
            if not self.bot.meme_off_timer.cancelled() or not self.bot.meme_off_timer.done():
                return await ctx.send("There is already a timer running. Cancel it with `.meme-off cancel` first")
        if round_duration.endswith("s"):
            round_duration = round_duration[:-1]
        time_units = {"hour": 3600, "minute": 60, "second": 1}
        amount, unit = round_duration.split(" ")
        amount = int(amount)
        if amount < 0: 
            return await ctx.send("Only positive values allowed")
        if amount * time_units[unit] > 604800:
            return await ctx.send("Number too highm, the countdown can go for 7 days at max")
        if unit not in time_units.keys():
            return await ctx.send(f"No valid time unit the only available units are:\n{', '.join(time_units.keys())}")
        delay = int(amount) * time_units[unit]
        await ctx.send(f"Timer set to {amount} {unit}(s)")
        self.bot.meme_off_timer = self.bot.loop.create_task(self.timer(delay, ctx))

    @commands.guild_only()
    @meme_off.command(name="deadline", aliases=["dl"])
    async def meme_off_deadline(self, ctx):
        """ see how much time is left until the current deadline is over"""
        if not self.bot.meme_off_timer_timestamp:
            return await ctx.send("No timer set currently")
        time_diff = self.bot.meme_off_timer_timestamp - datetime.utcnow()
        minutes, seconds = divmod(time_diff.seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days = time_diff.days
        message = ""
        if days:
            message += f"{days} day{'s' if days > 1 else ''} "
        if hours:
            message += f"{hours} hour{'s' if hours > 1 else ''} "
        if minutes:
            message += f"{minutes} minute{'s' if minutes > 1 else ''} "
        if seconds:
            message += f"and {seconds} second{'s' if seconds > 1 else ''} "
        message += "left"
        await ctx.send(message)

    @commands.guild_only()
    @meme_off.command(name="cancel")
    async def meme_off_cancel(self, ctx):
        """
        cancel the current timer
        """
        self.bot.meme_off_timer.cancel()
        self.bot.meme_off_timer = None
        self.bot.meme_off_timer_timestamp = None
        await ctx.send("Timer was cancelled")

    async def timer(self, delay, ctx):
        self.bot.meme_off_timer_timestamp = datetime.utcnow() + timedelta(seconds=delay)
        await asyncio.sleep(delay)
        await ctx.send("Round has finished now.")
        if self.bot.pinned_template:
            await self.bot.pinned_template.unpin()
        self.bot.pinned_template = None
        self.bot.pinned_by = None
        self.bot.meme_off_timer = None
        self.bot.meme_off_timer_timestamp = None

    @commands.dm_only()
    @meme_off.command("submit")
    async def meme_off_submit(self, ctx, link: typing.Optional[str]):
        """
        **ONLY IN DMs:** add a template to the random rotation, file needs to be attached for this command
        """
        if ctx.message.attachments:
            template_submission = self.bot.submitted_templates.get(ctx.author.id, None)
            if not template_submission:
                template_submission = TemplateSubmission(ctx.author.id)

            template_submission.add_template(ctx.message.attachments[0].url)
            self.bot.submitted_templates[ctx.author.id] = template_submission
            await ctx.send("template successfully submitted")
            await self.bot.db.execute("""
                INSERT INTO meme_off_templates (user_id, link) VALUES ($1, $2)
            """, ctx.author.id, ctx.message.attachments[0].url)
        elif link:
            if not link.startswith("http"):
                return await ctx.send("please provide a link")
            template_submission = self.bot.submitted_templates.get(ctx.author.id, None)
            if not template_submission:
                template_submission = TemplateSubmission(ctx.author.id)

            template_submission.add_template(link)
            self.bot.submitted_templates[ctx.author.id] = template_submission
            await ctx.send("template successfully submitted")
            await self.bot.db.execute("""
                INSERT INTO meme_off_templates (user_id, link) VALUES ($1, $2)
            """, ctx.author.id, link)
        else:
            return await ctx.send("You need to attach a file to your message or provide a link")

    @commands.guild_only()
    @meme_off.command(name="template", aliases=["temp"])
    async def meme_off_template(self, ctx):
        """get a random submission from the template rotation"""
        if self.bot.pinned_template:
            return await ctx.send("A template is currently pinned remove it before getting a new one")
        if not self.template_order:
            if not self.bot.submitted_templates:
                return await ctx.send("No templates submitted")
            self.template_order = [u for u in self.bot.submitted_templates.keys() if self.bot.submitted_templates[u].has_template]
            random.shuffle(self.template_order)
            if not self.template_order:
                return await ctx.send("No templates left")
        submission = self.bot.submitted_templates[self.template_order.pop()]
        template = submission.get_template()
        if not template:
            return await ctx.send("no templates left")
        embed = discord.Embed(title="Meme Off Template", description=f"Template for this round from <@{submission.user_id}> is", url=template)
        async with self.session.get(template) as resp:
            print(resp.content_type)
            if "image" in resp.content_type:
                embed.set_image(url=template)
                self.bot.pinned_template = await ctx.send(embed=embed)
            else:
                buf = io.BytesIO(await resp.read())
                file_type = template.rpartition(".")[2]
                f = discord.File(fp=buf, filename=f"mo_template.{file_type}")
                self.bot.pinned_template = await ctx.send(file=f, embed=embed)
        await self.bot.pinned_template.pin()
        self.bot.pinned_by = ctx.author
        await self.bot.db.execute("""
        DELETE FROM meme_off_templates WHERE user_id = $1 and link = $2
        """, submission.user_id, template)

    @commands.has_any_role("Subreddit-Senpai", "Discord-Senpai")
    @meme_off.command(name="list_templates", aliases=["ltemplate"])
    async def meme_off_template_list(self, ctx):
        entries = []
        for user_id, template in self.bot.submitted_templates.items():
            if template.has_template:
                entries.append((user_id,'\n'.join(template.templates)))
        field_pages = paginator.FieldPages(ctx, entries=entries)
        if len(entries) == 0:
            await ctx.send("no templates")
        else:
            await field_pages.paginate()

    @commands.has_any_role("Subreddit-Senpai", "Discord-Senpai")
    @commands.guild_only()
    @meme_off.command(name="delete_templates", aliases=["deltemplates", "delTemplates", "delete"])
    async def meme_off_templates_reset(self, ctx):
        """ remove all template submissions"""
        self.bot.submitted_templates = {}
        await ctx.send("all templates removed")

    async def fetch_message(self, ctx):
        message = ctx.message.reference.resolved
        if isinstance(message, discord.DeletedReferencedMessage):
            guild = self.bot.get_guild(message.guild_id)
            channel = guild.get_channel(message.channel_id)
            message = await channel.fetch_message(message.id)
        return message
            
    @commands.guild_only()
    @meme_off.command(name="pin", aliases=[])
    async def meme_off_pin(self, ctx, message : typing.Optional[discord.Message]):
        """
        provide a message link to pin as template, or reply to a message that should be pinned
        """
        if ctx.message.reference and not message:
            message = await self.fetch_message(ctx)
        if not message:
            return await ctx.send("No message provided or couldn't fetch message")
        if self.bot.pinned_template:
            return await ctx.send("There already is a template pinned!")
        await message.pin()
        self.bot.pinned_template = message
        self.bot.pinned_by = ctx.author

    @commands.guild_only()
    @meme_off.command(name="unpin", aliases=[])
    async def meme_off_unpin(self, ctx):
        """
        unpin the last template (only usable by moderators or the user who pinned the template)
        """
        if not self.bot.pinned_template:
            return await ctx.send("There is no template pinned right now")
        role_names = [r.name for r in ctx.author.roles]
        if ctx.author == self.bot.pinned_by or "Discord-Senpai" in role_names or "Subreddit-Senpai" in role_names:
            await self.bot.pinned_template.unpin()
            self.bot.pinned_template = None
            self.bot.pinned_by = None
            await ctx.send("template unpinned")
        else:
            await ctx.send("Only a moderator or the user who pinned the template can unpin it")


def setup(bot):
    bot.add_cog(MemeOff(bot))

