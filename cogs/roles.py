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
            await self.view.show_page(interaction, self.view.current_page)
            
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

    async def show_page(self, interaction: discord.Interaction, page: int):
        left = page * self.page_size
        right = (page + 1) * self.page_size 
        self.displayed_roles = self.role_list[left:right]
        self.remove_item(self.dropdown)
        self.dropdown = RoleSelect(self.displayed_roles)
        self.add_item(self.dropdown)
        embed = await self.embed()
        await interaction.response.edit_message(embed=embed, view=self)


    @discord.ui.button(emoji='\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}', row=2)
    async def page_back(self, interaction, button):
        if self.current_page < 1:
            return
        self.current_page -= 1
        await self.show_page(interaction, self.current_page)


    @discord.ui.button(emoji='\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}', row=2)
    async def page_forward(self, interaction, button):
        if self.current_page >= self.max_page-1:
            return
        self.current_page += 1
        await self.show_page(interaction, self.current_page)

class CustomRoleConverter(commands.RoleConverter):
    """
    This converter is for removing
    """
    async def convert(self, ctx, argument):
        modified_arg = argument.strip('"')
        modified_arg = argument.replace("@","")
        for role in ctx.guild.roles:
            if modified_arg.lower() == role.name.lower():
                return role
        return await super().convert(ctx, argument)

class Roles(commands.Cog):
    """role managing commands"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.file_path = 'data/roles.json'
        self.lockdown = False

    async def cog_load(self):
        self.bot.loop.create_task(self.create_role_table())

    async def create_role_table(self):
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await con.execute("""
                    CREATE TABLE IF NOT EXISTS role_info(
                        role_id BIGINT PRIMARY KEY,
                        description TEXT,
                        pingable boolean DEFAULT false
                        ) """)
                await con.execute("""
                    ALTER TABLE role_info
                    ADD COLUMN IF NOT EXISTS pingable boolean DEFAULT false;
                """)
                await con.execute("""
                ALTER TABLE role_info
                ADD COLUMN IF NOT EXISTS assignable boolean DEFAULT false;
                """)
                await con.execute("""
                ALTER TABLE role_info
                ADD COLUMN IF NOT EXISTS guild_id BIGINT;
                """)

    async def _fetch_assignable_roles(self, ctx: commands.Context):
        role_ids = await self.bot.db.fetch("SELECT role_id FROM role_info WHERE guild_id = $1 AND assignable = true", ctx.guild.id)
        roles = []
        for record in role_ids:
            if role := ctx.guild.get_role(record["role_id"]):
                roles.append(role)
        return roles

    async def fetch_role_info(self, role_id):
        async with self.bot.db.acquire() as con:
            statement = await con.prepare("""
                SELECT description, pingable, assignable from role_info
                WHERE role_id = $1
            """)
            return await statement.fetchrow(role_id)

    async def create_role_description(self, role_id, desc, guild):
        async with self.bot.db.acquire() as con:
            statement = await con.prepare("""
                INSERT INTO role_info (role_id, description, guild_id) VALUES
                ($1, $2, $3)
                ON CONFLICT (role_id) DO UPDATE SET description = EXCLUDED.description 
            """)
            await statement.fetch(role_id, desc, guild.id)

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

    @commands.guild_only()
    @commands.command(name="iam")
    async def assign_role(self, ctx, * , role: CustomRoleConverter):
        """
        assigns you a role
        """
        settable_role = await self._fetch_assignable_roles(ctx)
        if role not in settable_role:
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
        settable_role = await self._fetch_assignable_roles(ctx)
        if not settable_role:
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
    @channel_only("bot-shenanigans",191536772352573440,390617633147453444, 208765039727869954)
    @commands.guild_only()
    async def get_assignable_roles(self, ctx):
        """
        Creates an interactive menu of assignable roles which you can use to assign or remove roles from yourself
        \N{WHITE HEAVY CHECK MARK} indicates you already have that role.
        """
        assignable_roles = await self._fetch_assignable_roles(ctx)
        if assignable_roles:
            role_menu = RoleMenu(assignable_roles, ctx, timeout=180)
            await role_menu.start(ctx)
        else:
            await ctx.send("No roles are assignable for you")



    @commands.command()
    @commands.guild_only()
    async def roleinfo(self, ctx: commands.Context, * ,role: typing.Optional[CustomRoleConverter]):
        """shows information about the server roles or a certain role"""
        server = ctx.message.guild
        roles = server.roles
        embed = discord.Embed()
        command_invoke_str = ctx.message.content.removeprefix(f"{ctx.clean_prefix}{ctx.invoked_with}")
        if command_invoke_str and not role:
            return await ctx.send("Role not found.")
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
                embed.add_field(name='assignable', value="yes" if info.get('assignable', False) else 'no')
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
        await self.create_role_description(role.id, description, ctx.guild)
        return await ctx.send("Role description set.")


    @commands.command(name="mention", cooldown_after_parsing=True)
    @commands.check_any(commands.has_any_role(189594836687519744, 514884001417134110), checks.is_owner_or_moderator())
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    @commands.cooldown(rate=1, per=60, type=commands.BucketType.member)
    async def roles_ping(self, ctx, *, role: CustomRoleConverter):
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
            INSERT INTO role_info (role_id, pingable, guild_id) VALUES ($1, $2, $3)
            ON CONFLICT (role_id) DO 
                UPDATE SET pingable = $2
            """, new_role.id, mentionable, ctx.guild.id)
            await ctx.send("role `{}` created".format(new_role.name))
        except discord.Forbidden:
            await ctx.send("Sorry I don't have the permission add a role")

    @roles.command(name="remove")
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def _remove_role(self, ctx, role: discord.Role):
        """
        Remove a role from the database and the server
        """
        await ctx.bot.db.execute("""
        DELETE FROM role_info WHERE role_id = $1
        """, role.id)
        try:
            await role.delete()
            await ctx.message.add_reaction("\N{WHITE HEAVY CHECK MARK}")
        except discord.Forbidden:
            await ctx.send("Sorry, I don't have the permission to delete that role")

    @roles.command(name="mentionable", aliases=["pingable"])  
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def _set_role_pingable(self, ctx, role: discord.Role, pingable: bool):
        """
        set whether a role is pingable or for users 
        """
        ret = await self.bot.db.execute("""
        INSERT INTO role_info (role_id, pingable, guild_id) VALUES ($1, $2, $3)
        ON CONFLICT (role_id) DO 
            UPDATE SET pingable = $2
        """, role.id, pingable, ctx.guild.id)
        await ctx.send(f"role updated to {'pingable' if pingable else 'unpingable'}")

    @roles.command(name="assignable")
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def _set_role_assignable(self, ctx: commands.Context, role: discord.Role, assignable: bool):
        """
        set whether a role should be self assignable
        """
        ret = await self.bot.db.execute("""
        INSERT INTO role_info (role_id, assignable, guild_id) VALUES ($1, $2, $3)
        ON CONFLICT (role_id) DO 
            UPDATE SET assignable = $2
        """, role.id, assignable, ctx.guild.id)
        await ctx.send(f"role updated to {'self-assignable' if assignable else 'not self-assignable'}")


        


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


async def setup(bot: commands.Bot):
    await bot.add_cog(Roles(bot))
