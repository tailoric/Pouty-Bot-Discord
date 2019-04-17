from discord.ext import commands
from discord.utils import find
import discord.ext.commands
import random
import json


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
            found_user = commands.MemberConverter(ctx=ctx, argument=user).convert()
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
            found_user = commands.MemberConverter(ctx=ctx, argument=user).convert()
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
            found_user = commands.MemberConverter(ctx=ctx, argument=user).convert()
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
            found_user = commands.MemberConverter(ctx=ctx, argument=user).convert()
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
            found_user = commands.MemberConverter(ctx=ctx, argument=user).convert()
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

    @commands.command(hidden=False, pass_context=True)
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
            found_user = commands.MemberConverter(ctx=ctx, argument=user).convert()
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
            found_user = commands.MemberConverter(ctx=ctx, argument=user).convert()
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
            found_user = commands.MemberConverter(ctx=ctx, argument=user).convert()
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
            found_user = commands.MemberConverter(ctx=ctx, argument=user).convert()
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
            found_user = commands.MemberConverter(ctx=ctx, argument=user).convert()
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
            found_user = commands.MemberConverter(ctx=ctx, argument=user).convert()
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
            found_user = commands.MemberConverter(ctx=ctx, argument=user).convert()
            fmt = '{0}\n{1}'
            await ctx.send(fmt.format(found_user.mention, random.choice(images)))

def setup(bot):
    bot.add_cog(Social(bot))
