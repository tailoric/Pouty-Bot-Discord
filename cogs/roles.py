from discord.ext import commands
from discord.utils import find, get
import discord
import json
import os
import cogs.utils.checks as checks
import random
import colorsys
from .utils.converters import RoleConverter
from .utils.checks import channel_only
import typing
import re

class CustomRoleConverter(RoleConverter):
    """
    This converter is for removing
    """
    async def convert(self, ctx, argument):
        if re.match(r"\d+", argument):
            argument = int(argument)
            return ctx.guild.get_role(argument)
        argument = argument.strip('"')
        return await super().convert(ctx, argument)

class Roles(commands.Cog):
    """role managing commands"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.file_path = 'data/roles.json'
        if os.path.exists(self.file_path):
            with open(self.file_path) as f:
                self.settable_roles = json.load(fp=f)
        else:
            self.settable_roles = []
            self.save_roles_to_file()
        self.lockdown = False


    @checks.is_owner_or_moderator()
    @commands.command()
    async def lockdown(self, ctx, status):
        """
        locks down the server so role doesn't get assigned
        use ".lockdown enable" to enable lockdown and
        ".lockdown disable" to disable
        """
        if status.lower() == "enable":
            self.lockdown = True
            await ctx.send("lockdown enabled")
        else:
            self.lockdown = False
            await ctx.send("lockdown disabled")

    def save_roles_to_file(self):
        with open('data/roles.json', 'w') as file:
            json.dump(self.settable_roles, file)

    @commands.command(name="iam")
    async def assign_role(self, ctx, * , role: CustomRoleConverter):
        """
        assigns you a role
        """
        settable_role = find(lambda r: r.id in self.settable_roles, ctx.guild.roles)
        if role == settable_role and self.lockdown:
            await ctx.send("Server on lockdown due to high amount of people joining try again in a day or two")
            return
        if role.position > settable_role.position:
            if ctx.channel.name != "have-you-read-the-rules":
                await ctx.send("can't give you that role")
            return
        try:
            admin_cog = self.bot.get_cog("Admin")
            if admin_cog:
                if admin_cog.mute_role == role:
                    return
            member = ctx.message.author
            await member.add_roles(role)
            await ctx.send(f"Assigned you the following role: {role.name}")
        except discord.Forbidden as fb:
            await ctx.send("Sorry I don't have the permission to give you that role")

    @commands.command(name="amnot", aliases=["iamnot"])
    async def remove_role(self, ctx, role: CustomRoleConverter):
        """removes a role from you"""
        settable_role = find(lambda r: r.id in self.settable_roles, ctx.guild.roles)
        if role.position > settable_role.position:
            await ctx.send("can't remove that role")
            return
        try:
            member = ctx.message.author
            await member.remove_roles(role)
            await ctx.send("removed your role: %s " % role.name)
        except discord.Forbidden as fb:
            await ctx.send("You either don't have that role or I am not allowed to remove it")

    @checks.is_owner_or_moderator()
    @commands.group(name="roles", pass_context=True)
    async def roles(self, ctx):
        """
        administrative commands for the roles
        """
        pass

    @checks.is_owner_or_moderator()
    @commands.command(name="mention")
    async def roles_ping(self, ctx, role: RoleConverter):
        """
        ping the role by making it mentionable for the ping and remove
        mentionable again
        """
        try:
            await role.edit(mentionable=True)
            await ctx.send(role.mention)
            await role.edit(mentionable=False)
        except discord.Forbidden as fb:
            await ctx.send("I am not allowed to edit this role")

    @roles.command(name="add", pass_context=True)
    async def _add_role(self, ctx, role_name: str, mentionable=True, colour=None):
        """
        add a role the bot can edit
        """
        try:
            server = ctx.message.guild

            set_colour = discord.Colour(value=int(colour, 16)) if colour else discord.Colour(value=None)
            if find(lambda r: r.name == role_name, server.roles):
                await ctx.send('role already exists.')
                return
            new_role = await server.create_role(name=role_name, mentionable=mentionable, colour=set_colour)
            await ctx.send("role `{}` created".format(new_role.name))
        except discord.Forbidden:
            await ctx.send("Sorry I don't have the permission add a role")

    @roles.command(name="remove", pass_context=True)
    async def _remove_role(self, ctx, role_name: str):
        """
        remove a role the bot can edit
        """
        try:
            server = ctx.message.guild
            role = find(lambda r: r.name == role_name, server.roles)
            if not role:
                await ctx.send('role `{}` not found'.format(role_name))
                return
            await server.delete_role(role)
            await ctx.send('role `{}` removed'.format(role_name))
        except discord.Forbidden:
            await ctx.send("Sorry I don't have the permission to remove that role")

    @commands.command(aliases=["color","colour"])
    @channel_only(582894980436328449, 208765039727869954)
    async def random_colors(self, ctx, hexcode : typing.Optional[str]):
        if hexcode:
            hexcode = hexcode.strip("#")
            value = int(hexcode, 16)
            color = discord.Colour(value)
        else:
            value = [int(x * 255) for x in colorsys.hls_to_rgb(random.random(), 0.8, 1.0)]
            color = discord.Color.from_rgb(*value)
        await ctx.send(embed=discord.Embed(color=color, description=str(color)))


def setup(bot: commands.Bot):
    bot.add_cog(Roles(bot))
