from discord.ext import commands
from discord.utils import find
from .utils.checks import channel_only
import discord.ext.commands
import random
import json
import asyncio


class Social(commands.Cog):
    """
    Answers with image to certain interactions
    """

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def find_file(command):
        with open('data/social/{}.json'.format(command), 'r') as f:
            return json.load(f)

    @commands.command(hidden=False, pass_context=True)
    async def pout(self, ctx, *, user=None):
        """ 
        usage: .pout 
        """
        mentioned_users = ctx.message.mentions
        file_name = 'pouts'
        images = await self.find_file(file_name)
        if mentioned_users or not user:
            await ctx.send(random.choice(images))
        else:
            user = user.replace("\"", "")
            found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(hidden=False, pass_context=True)
    async def hug(self, ctx, *, user=None):
        """
            usage: .hug (at) user
        """
        mentioned_users = ctx.message.mentions
        file_name = 'hug'
        images = await self.find_file(file_name)
        if mentioned_users or not user:
            await ctx.send(random.choice(images))
        else:
            user = user.replace("\"", "")
            found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(hidden=False, pass_context=True)
    async def smug(self, ctx, *, user=None):
        """
            usage: .smug (at) user
        """
        mentioned_users = ctx.message.mentions
        file_name = 'smug'
        images = await self.find_file(file_name)
        if mentioned_users or not user:
            await ctx.send(random.choice(images))
        else:
            user = user.replace("\"", "")
            found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(hidden=False, pass_context=True)
    async def cuddle(self, ctx, *, user=None):
        """
            usage: .cuddle (at) user
        """
        mentioned_users = ctx.message.mentions
        file_name = 'cuddle'
        images = await self.find_file(file_name)
        if mentioned_users or not user:
            await ctx.send(random.choice(images))
        else:
            user = user.replace("\"", "")
            found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(hidden=False, pass_context=True)
    async def lewd(self, ctx, *, user=None):
        """
            usage: .lewd (at) user
        """
        mentioned_users = ctx.message.mentions
        file_name = 'lewd'
        images = await self.find_file(file_name)
        if mentioned_users or not user:
            await ctx.send(random.choice(images))
        else:
            user = user.replace("\"", "")
            found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(aliases=["headpat"])
    async def pat(self, ctx, *, user=None):
        """
            usage: .pat (at) user
        """
        mentioned_users = ctx.message.mentions
        file_name = 'pat'
        images = await self.find_file(file_name)
        if mentioned_users or not user:
            await ctx.send(random.choice(images))
        else:
            user = user.replace("\"", "")
            found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(hidden=False, pass_context=True)
    async def bully(self, ctx, *, user=None):
        """
            usage: .bully (at) user
        """
        mentioned_users = ctx.message.mentions
        file_name = 'bully'
        images = await self.find_file(file_name)
        if mentioned_users or not user:
            await ctx.send(random.choice(images))
        else:
            user = user.replace("\"", "")
            found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(hidden=False, pass_context=True)
    async def nobully(self, ctx, *, user=None):
        """
            usage: .nobully
        """
        mentioned_users = ctx.message.mentions
        file_name = 'nobullys'
        images = await self.find_file(file_name)
        if mentioned_users or not user:
            await ctx.send(random.choice(images))
        else:
            user = user.replace("\"", "")
            found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(hidden=False, pass_context=True)
    async def slap(self, ctx, *, user=None):
        """
            usage: .slap (at) user
        """
        mentioned_users = ctx.message.mentions
        file_name = 'slaps'
        images = await self.find_file(file_name)
        if mentioned_users or not user:
            await ctx.send(random.choice(images))
        else:
            user = user.replace("\"", "")
            found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(hidden=False, pass_context=True)
    async def kiss(self, ctx, *, user=None):
        """
            usage: .kiss (at) user
        """
        mentioned_users = ctx.message.mentions
        file_name = 'kiss'
        images = await self.find_file(file_name)
        if mentioned_users or not user:
            await ctx.send(random.choice(images))
        else:
            user = user.replace("\"", "")
            found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(hidden=False, pass_context=True)
    async def blush(self, ctx, *, user=None):
        """
            usage: .blush (at) user
        """
        mentioned_users = ctx.message.mentions
        file_name = 'Blush'
        images = await self.find_file(file_name)
        if mentioned_users or not user:
            await ctx.send(random.choice(images))
        else:
            user = user.replace("\"", "")
            found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(hidden=False, pass_context=True)
    async def cry(self, ctx, *, user=None):
        """
            usage: .cry (at) user
        """
        mentioned_users = ctx.message.mentions
        file_name = 'cry'
        images = await self.find_file(file_name)
        if mentioned_users or not user:
            await ctx.send(random.choice(images))
        else:
            user = user.replace("\"", "")
            found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(hidden=False, pass_context=True)
    async def sleep(self, ctx, *, user=None):
        """
            usage: .sleep (at) user
        """
        mentioned_users = ctx.message.mentions
        file_name = 'sleep'
        images = await self.find_file(file_name)
        if mentioned_users or not user:
            await ctx.send(random.choice(images))
        else:
            user = user.replace("\"", "")
            found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(hidden=True, pass_context=True, aliases=["licc","lic","pero"])
    async def lick(self, ctx, *, user=None):
        mentioned_users = ctx.message.mentions
        file_name = 'lick'
        images = await self.find_file(file_name)
        if mentioned_users or not user:
            await ctx.send(random.choice(images))
        else:
            user = user.replace("\"", "")
            found_user = await commands.MemberConverter().convert(ctx=ctx, argument=user)
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(name="iloveyou")
    async def iloveyou(self, ctx):
        await ctx.send(f"I love you too, {ctx.author.mention} \N{HEAVY BLACK HEART}")
    @commands.command()
    async def love(self, ctx, member: discord.Member):
        """accurately calculate of how much love you are possible of giving to the other user"""
        lover = ctx.author
        love_capability = random.randint(0, 100)
        love_message_string = (f"**{lover.display_name}** is capable of loving "
                               f"**{member.display_name}** a whooping {love_capability}%")
        love_message = await ctx.send(love_message_string)
        def sad_reaction_check(reaction: discord.Reaction, user):
            if isinstance(reaction.emoji, str):
                return False
            reaction_name = reaction.emoji.name
            return 'sad' in reaction_name.lower() \
                   and (user.id == lover.id or user.id == member.id) and love_capability < 60 \
                   and reaction.message.channel.id == ctx.channel.id
        try:
            await self.bot.wait_for('reaction_add', timeout=20.0, check=sad_reaction_check)
        except asyncio.TimeoutError:
            return
        love_bonus = random.randint(0, 100-love_capability)
        love_capability = min(love_capability+love_bonus, 100)
        await love_message.edit(content="\N{SPARKLING HEART} love booster activated recalculating the score"
                                        "\N{SPARKLING HEART}")
        await asyncio.sleep(3)
        await love_message.edit(content=f"**{lover.display_name}** is capable of loving "
                                        f"**{member.display_name}** a whooping {love_capability}% "
                                        f"(with a love boost of {love_bonus}%)")

def setup(bot):
    bot.add_cog(Social(bot))
