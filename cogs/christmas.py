from discord.ext import commands
from .utils import checks
import discord
import asyncio
from .utils import dataIO


class Christmas(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.green_role = None
        self.red_role = None
        self.next_role = None
        self.padoru = discord.utils.get(self.bot.emojis, name="PADORUPADORU")
        self.communism = discord.utils.get(self.bot.emojis, name="communism")
        settings_loader = dataIO.DataIO()
        initial_cogs = settings_loader.load_json("initial_cogs")
        initial_cogs.append("cogs.christmas")
        settings_loader.save_json("initial_cogs", initial_cogs)


    def cog_unload(self):
        settings_loader = dataIO.DataIO()
        initial_cogs = settings_loader.load_json("initial_cogs")
        initial_cogs.remove("cogs.christmas")
        settings_loader.save_json("initial_cogs", initial_cogs)

    @commands.command(name="christmas", pass_context=True, hidden=True)
    @checks.is_owner_or_moderator()
    async def _christmas(self, ctx):
        """
        starts christmas time
        """
        server = ctx.message.guild
        self.red_role, self.green_role = await self.get_christmas_roles(server)
        role = discord.utils.get(server.roles, name="Memester")
        if self.red_role.position < role.position or self.green_role.position < role.position:
            await self.red_role.edit(position=role.position+1)
            await self.green_role.edit(position=role.position+1)
        christmas_message = await ctx.send("Christmas time in 3")
        await asyncio.sleep(1)
        await christmas_message.edit(content="Christmas time in 2")
        await asyncio.sleep(1)
        await christmas_message.edit(content="Christmas time in 1")
        await asyncio.sleep(1)
        await christmas_message.edit(content=f"{self.padoru} MERRY CHRISTMAS {self.padoru}")

    async def get_christmas_roles(self, server):
        role_red = discord.utils.get(server.roles, name="ChristmasSoviets")
        role_green = discord.utils.get(server.roles, name="PadoruPatrol")
        if not role_red and not role_green:
            role_red = await server.create_role(name="ChristmasSoviets",color=discord.Color(int("c62f2f",16)))
            role_green = await server.create_role(name="PadoruPatrol",color=discord.Color(int("157718",16)))
        return role_red, role_green

    @checks.channel_only(191536772352573440, 390617633147453444)
    @commands.command(name="grinch")
    async def leave_christmas_role(self, ctx):
        """
        remove your christmas role
        """
        christmas_role = next(filter(lambda r: r == self.green_role or r == self.red_role, ctx.author.roles), None)
        if christmas_role:
            await ctx.author.remove_roles(christmas_role)
            await ctx.send("removed your christmas role")
        else:
            await ctx.send("You don't have any christmas roles")
    
    @checks.channel_only(191536772352573440, 390617633147453444)
    @commands.command(name="padoru")
    async def join_padoru(self, ctx):
        """
        join the padoru color squad
        """
        if self.green_role is None:
            self.green_role = discord.utils.get(ctx.guild.roles, name="PadoruPatrol")
        await ctx.author.add_roles(self.green_role)
        if self.red_role in ctx.author.roles:
            await ctx.author.remove_roles(self.red_role)
        await ctx.send(f"you joined the {self.padoru} squad")

    @checks.channel_only(191536772352573440, 390617633147453444)
    @commands.command(name="soviet")
    async def join_soviets(self, ctx):
        """
        join the christmas soviet squad
        """
        if self.red_role is None:
            self.red_role = discord.utils.get(ctx.guild.roles, name="ChristmasSoviets")
        await ctx.author.add_roles(self.red_role)
        if self.green_role in ctx.author.roles:
            await ctx.author.remove_roles(self.green_role)
        await ctx.send(f"you joined the {self.communism} squad")






async def setup(bot):
    await bot.add_cog(Christmas(bot))
