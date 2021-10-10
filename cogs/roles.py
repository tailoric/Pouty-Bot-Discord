from discord.ext import commands
from discord.utils import find, get
from discord.ext import menus
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
from math import ceil
from random import randint

class RoleSelect(discord.ui.Select):
    def __init__(self, roles: typing.List[discord.Role]):
        self.roles = roles
        options = list(discord.SelectOption(label=role.name, value=str(role.id)) for role in roles)           
        super().__init__(placeholder="Please select a role", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        selection = None
        if not isinstance(interaction.user, discord.Member):
            return
        if self.values:
            selection = self.values[0]
        if selection and self.view:
            user_roles = []
            if interaction.user:
                user_roles = list(r.id for r in interaction.user.roles)
            if int(self.values[0]) in user_roles:
                await interaction.user.remove_roles(discord.Object(int(self.values[0])))
            else:
                await interaction.user.add_roles(discord.Object(int(self.values[0])))
            await self.view.show_page(self.view.current_page)
            
class RoleMenu(discord.ui.View):
    def __init__(self, role_list: typing.List[discord.Role], context: commands.Context, **kwargs):
        super().__init__(**kwargs)
        self.role_list = role_list
        self.ctx = context
        if role_list:
            self.guild = role_list[0].guild
        self.current_page = 0
        self.page_size = 5
        self.max_page = ceil(len(self.role_list) / self.page_size) 

        left = self.current_page * self.page_size
        right = (self.current_page + 1)* self.page_size

        self.displayed_roles = self.role_list[left:right]
        self.dropdown = RoleSelect(self.displayed_roles)
        self.add_item(self.dropdown)

    async def interaction_check(self, interaction: discord.Interaction):
        return self.ctx.author == interaction.user

    async def start(self, ctx):
        self.message = await ctx.send(embed=await self.embed(), view=self)

    async def embed(self):
        description = (f"""
        Assign or remove a role from yourself by selecting the role from the dropdown.
        To change pages use \N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16} and \N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}
        """)
        embed = discord.Embed(title="Assignable Roles", description=description, colour=discord.Colour.blurple())
        embed.set_footer(text=f"Page {self.current_page+1}/{self.max_page}")
        for role in self.displayed_roles:
            checkmark = '\N{WHITE HEAVY CHECK MARK}' if role in self.ctx.author.roles else ''
            role_description = await self.ctx.bot.db.fetchval("SELECT description FROM role_info WHERE role_id = $1", role.id) or '\u200b'
            embed.add_field(name=f"{role.name} {checkmark}", value=role_description, inline=False)
        return embed

    async def show_page(self, page):
        left = page * self.page_size
        right = (page + 1) * self.page_size 
        self.displayed_roles = self.role_list[left:right]
        self.remove_item(self.dropdown)
        self.dropdown = RoleSelect(self.displayed_roles)
        self.add_item(self.dropdown)
        embed = await self.embed()
        await self.message.edit(embed=embed, view=self)


    @discord.ui.button(emoji='\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}', row=2)
    async def page_back(self, button, interaction):
        if self.current_page < 1:
            return
        self.current_page -= 1
        await self.show_page(self.current_page)


    @discord.ui.button(emoji='\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}', row=2)
    async def page_forward(self, button, interaction):
        if self.current_page >= self.max_page-1:
            return
        self.current_page += 1
        await self.show_page(self.current_page)

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
                    description TEXT,
                    pingable boolean DEFAULT false
                    ) """)
            await con.execute("""
                ALTER TABLE role_info
                ADD COLUMN IF NOT EXISTS pingable boolean DEFAULT false
            """)

    async def fetch_role_info(self, role_id):
        async with self.bot.db.acquire() as con:
            statement = await con.prepare("""
                SELECT description, pingable from role_info
                WHERE role_id = $1
            """)
            return await statement.fetchrow(role_id)

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

    @commands.guild_only()
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
    @commands.guild_only()
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
    @channel_only("bot-shenanigans",191536772352573440,390617633147453444)
    @commands.guild_only()
    async def get_assignable_roles(self, ctx):
        """
        Creates an interactive menu of assignable roles which you can use to assign or remove roles from yourself
        \N{WHITE HEAVY CHECK MARK} indicates you already have that role.
        """
        settable_role = find(lambda r: r.id in self.settable_roles, ctx.guild.roles)
        assignable_roles = [r for r in ctx.guild.roles if r.position <= settable_role.position]
        assignable_roles.remove(ctx.guild.default_role)
        role_menu = RoleMenu(assignable_roles, ctx, timeout=180)
        await role_menu.start(ctx)



    @commands.command()
    @commands.guild_only()
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
            info = await self.fetch_role_info(role.id)
            embed.title = role.name
            embed.color = role.colour
            embed.add_field(name="ID", value=role.id)
            embed.add_field(name="Member Count", value="{} Member(s)".format(len(role.members)))
            embed.add_field(name="Colour", value=role.colour)
            embed.set_footer(text="Role was created on")
            embed.timestamp = role.created_at
            if role.icon: 
                embed.set_thumbnail(url=role.icon.url)
            if info:
                embed.description = info.get('description', '\u200b')
                embed.add_field(name='pingable', value='yes' if info.get('pingable', False) else 'no')
        await ctx.send(embed=embed)

    @commands.has_permissions(manage_roles=True)
    @commands.group(name="roles", pass_context=True, aliases=['role'])
    @commands.guild_only()
    async def roles(self, ctx):
        """
        administrative commands for the roles
        """
        pass

    @roles.command(name="description")
    @commands.has_permissions(manage_roles=True)
    async def _role_description(self, ctx, role : CustomRoleConverter, *, description: str):
        """
        set the description of a certain role
        """
        await self.create_role_description(role.id, description)
        return await ctx.send("Role description set.")


    @commands.command(name="mention")
    @commands.check_any(commands.has_any_role(189594836687519744, 514884001417134110), checks.is_owner_or_moderator())
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    @commands.cooldown(rate=1, per=20, type=commands.BucketType.guild)
    async def roles_ping(self, ctx, role: discord.Role):
        """
        ping the role by making it mentionable for the ping and remove
        mentionable again
        """
        can_ping = await self.bot.db.fetchval("""
        SELECT pingable FROM role_info WHERE role_id = $1
        """, role.id)
        if not can_ping:
            return await ctx.send("I am not allowed to ping this role")
        try:
            await role.edit(mentionable=True)
            await ctx.send(role.mention)
            await role.edit(mentionable=False)
        except discord.Forbidden as fb:
            await ctx.send("I am not allowed to edit this role")

    @roles.command(name="add")
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def _add_role(self, ctx, role_name: str, mentionable=False, colour=None):
        """
        add a role the bot can edit
        """
        try:
            server = ctx.message.guild

            set_colour = discord.Colour(value=int(colour, 16)) if colour else discord.Colour.default()
            if find(lambda r: r.name == role_name, server.roles):
                await ctx.send('role already exists.')
                return
            new_role = await server.create_role(name=role_name, colour=set_colour)
            ret = await self.bot.db.execute("""
            INSERT INTO role_info (role_id, pingable) VALUES ($1, $2)
            ON CONFLICT (role_id) DO 
                UPDATE SET pingable = $2
            """, new_role.id, mentionable)
            await ctx.send("role `{}` created".format(new_role.name))
        except discord.Forbidden:
            await ctx.send("Sorry I don't have the permission add a role")

    @roles.command(name="mentionable")
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def _set_role_pingable(self, ctx, role: discord.Role, pingable: bool):
        """
        set wether a role is pingable or for users 
        """
        ret = await self.bot.db.execute("""
        INSERT INTO role_info (role_id, pingable) VALUES ($1, $2)
        ON CONFLICT (role_id) DO 
            UPDATE SET pingable = $2
        """, role.id, pingable)
        print(ret)
        await ctx.send(f"role updated to {'pingable' if pingable else 'unpingable'}")
        


    @roles.command(name="remove")
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
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
    @commands.guild_only()
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
