from discord.ext import commands
import discord.ext.commands
from discord.utils import find
import json
import os
import cogs.utils.checks as checks
class Roles:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.file_path = 'data/roles.json'
        if os.path.exists(self.file_path):
            with open(self.file_path) as f:
                self.settable_roles = json.load(fp=f)
        else:
            self.settable_roles = {'roles' : []}


    def save_roles_to_file(self):
        with open('data/roles.json', 'w') as file:
            json.dump(self.settable_roles, file)


    @commands.command(name="iam", pass_context=True)
    async def assign_role(self, ctx, role: discord.Role):
        try:
            member = ctx.message.author
            await self.bot.add_roles(member, role)
            await self.bot.say("your role is now: %s " % role.name)
        except discord.Forbidden as fb:
            await self.bot.say("Sorry I don't have the permission to give you that role")

    @commands.command(name="amnot", pass_context=True)
    async def remove_role(self, ctx, role: discord.Role):
        try:
            member = ctx.message.author
            await self.bot.remove_roles(member, role)
            await self.bot.say("removed your role: %s " % role.name)
        except discord.Forbidden as fb:
            await self.bot.say("You either don't have that role or I am not allowed to remove it")

    @checks.is_owner_or_moderator()
    @commands.group(name="roles", pass_context=True)
    async def roles(self, ctx):
        pass

    @roles.command(name="add", pass_context=True)
    async def _add_role(self, ctx, role_name: str, mentionable=True, colour=None):
        try:
            server = ctx.message.server

            set_colour = discord.Colour(value=int(colour, 16)) if colour else discord.Colour(value=None)
            if find(lambda r: r.name == role_name, server.roles):
                await self.bot.say('role already exists.')
                return
            new_role = await self.bot.create_role(server=server, name=role_name, mentionable=mentionable, colour=set_colour)
            await self.bot.say("role `{}` created".format(new_role.name))
        except discord.Forbidden:
            await self.bot.say("Sorry I don't have the permission add a role")

    @roles.command(name="remove", pass_context=True)
    async def _remove_role(self, ctx, role_name: str):
        try:
            server = ctx.message.server
            role = find(lambda r: r.name == role_name, server.roles)
            if not role:
                await self.bot.say('role `{}` not found'.format(role_name))
                return
            await self.bot.delete_role(server, role)
            await self.bot.say('role `{}` removed'.format(role_name))
        except discord.Forbidden:
            await self.bot.say("Sorry I don't have the permission to remove that role")

def setup(bot: commands.Bot):
    bot.add_cog(Roles(bot))
