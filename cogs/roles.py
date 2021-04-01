from discord.ext import commands
from discord.utils import find, get
import discord
import json
import os
import cogs.utils.checks as checks
import random
import colorsys
from .utils.checks import channel_only
from .utils.paginator import FieldPages
import typing
import re
from random import randint

class CustomRoleConverter(commands.RoleConverter):
    """
    This converter is for removing
    """
    async def convert(self, ctx, argument):
        argument = argument.strip('"')
        for role in ctx.guild.roles:
            if argument.lower() == role.name.lower():
                return role
        return await super().convert(ctx, argument)

class Roles(commands.Cog):
    """role managing commands"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.file_path = 'data/roles.json'
        self.bot.loop.create_task(self.create_role_table())
        if os.path.exists(self.file_path):
            with open(self.file_path) as f:
                self.settable_roles = json.load(fp=f)
        else:
            self.settable_roles = []
            self.save_roles_to_file()
        self.lockdown = False

    async def create_role_table(self):
        async with self.bot.db.acquire() as con:
            await con.execute("""
                CREATE TABLE IF NOT EXISTS role_info(
                    role_id BIGINT PRIMARY KEY,
                    description TEXT
                    ) """)

    async def fetch_role_description(self, role_id):
        async with self.bot.db.acquire() as con:
            statement = await con.prepare("""
                SELECT description from role_info
                WHERE role_id = $1
            """)
            return await statement.fetchval(role_id)
        
    async def create_role_description(self, role_id, desc):
        async with self.bot.db.acquire() as con:
            statement = await con.prepare("""
                INSERT INTO role_info VALUES
                ($1, $2)
                ON CONFLICT (role_id) DO UPDATE SET description = EXCLUDED.description 
            """)
            await statement.fetch(role_id, desc)

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
                if hasattr(admin_cog, "mute_role") and admin_cog.mute_role == role:
                    return
            member = ctx.message.author
            await member.add_roles(role)
            await ctx.send(f"Assigned you the following role: {role.name}")
        except discord.Forbidden as fb:
            await ctx.send("Sorry I don't have the permission to give you that role")

    @commands.command(name="amnot", aliases=["iamnot"])
    async def remove_role(self, ctx, *, role: CustomRoleConverter):
        """removes a role from you"""
        settable_role = find(lambda r: r.id in self.settable_roles, ctx.guild.roles)
        if role.position > settable_role.position:
            await ctx.send("can't remove that role")
            return
        try:
            member = ctx.message.author
            await member.remove_roles(role)
            chance = randint(0,100)
            if chance >= 90 and "horny" in role.name.lower():
                await ctx.send("https://youtu.be/rlhRQiVeQPY")
            await ctx.send("removed your role: %s " % role.name)
        except discord.Forbidden as fb:
            await ctx.send("You either don't have that role or I am not allowed to remove it")

    @commands.command(name="assignable_roles", aliases=["asroles", "icanbe"])
    async def get_assignable_roles(self, ctx):
        """
        gives you a list with assignable roles and description about these roles
        """
        settable_role = find(lambda r: r.id in self.settable_roles, ctx.guild.roles)
        assignable_roles = [r for r in ctx.guild.roles if r.position <= settable_role.position]
        assignable_roles.remove(ctx.guild.default_role)
        fields = []
        for role in assignable_roles:
            description = await self.fetch_role_description(role.id) or "\u200b"
            fields.append((role.name, description))
        pages = FieldPages(ctx, entries=fields, per_page=10)
        await pages.paginate()



    @commands.command()
    async def roleinfo(self, ctx, * ,role: typing.Optional[CustomRoleConverter]):
        """shows information about the server roles or a certain role"""
        server = ctx.message.guild
        roles = server.roles
        embed = discord.Embed()
        if not role:
            for role in roles:
                if role.name == "@everyone":
                    continue
                embed.add_field(name=role.name, value="{} Member(s)".format(len(role.members)))
        else:
            description = await self.fetch_role_description(role.id)
            embed.title = role.name
            embed.color = role.colour
            embed.add_field(name="ID", value=role.id)
            embed.add_field(name="Member Count", value="{} Member(s)".format(len(role.members)))
            embed.add_field(name="Colour", value=role.colour)
            embed.set_footer(text="Role was created on")
            embed.timestamp = role.created_at
            if description:
                embed.description = description
        await ctx.send(embed=embed)

    @commands.has_permissions(manage_roles=True)
    @commands.group(name="roles", pass_context=True, aliases=['role'])
    async def roles(self, ctx):
        """
        administrative commands for the roles
        """
        pass

    @roles.command(name="description")
    async def _role_description(self, ctx, role : CustomRoleConverter, *, description: str):
        """
        set the description of a certain role
        """
        await self.create_role_description(role.id, description)
        return await ctx.send("Role description set.")


    @checks.is_owner_or_moderator()
    @commands.command(name="mention")
    async def roles_ping(self, ctx, role: discord.Role):
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

    @roles.command(name="add")
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
    @channel_only(582894980436328449, 208765039727869954, 390617633147453444)
    async def random_colors(self, ctx, hexcode : typing.Optional[discord.Color]):
        rng = random.Random()
        if not hexcode:
            invocation_string = f"{ctx.prefix}{ctx.invoked_with}"
            if ctx.message.content != invocation_string:
                rng.seed(ctx.message.content.replace(f"{invocation_string} ", "").lower(), version=2)
            value = [int(x * 255) for x in colorsys.hls_to_rgb(rng.random(), 0.8, 1.0)]
            hexcode = discord.Color.from_rgb(*value)
        await ctx.send(embed=discord.Embed(color=hexcode, description=str(hexcode)))


def setup(bot: commands.Bot):
    bot.add_cog(Roles(bot))
