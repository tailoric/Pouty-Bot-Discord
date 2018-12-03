from discord.ext import commands
from .utils import checks
import discord
import asyncio


class Christmas:
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="christmas", pass_context=True, hidden=True)
    @checks.is_owner_or_moderator()
    async def _christmas(self, ctx):
        """
        starts christmas time
        """
        server = ctx.message.server
        red_role, green_role = await self.get_christmas_roles(server)
        role = discord.utils.get(server.roles, name="Memester")
        if(red_role.position < role.position or green_role.position < role.position):
            await self.bot.move_role(server=server,role=red_role, position=role.position+1)
            await self.bot.move_role(server=server,role=green_role, position=role.position+2)
        padoru = discord.utils.get(self.bot.get_all_emojis(), name="PADORUPADORU")
        padoru_string = "<a:" + padoru.name + ":" + padoru.id + ">"
        christmas_message = await self.bot.say("Christmas time in 3")
        await asyncio.sleep(1)
        await self.bot.edit_message(message=christmas_message, new_content="Christmas time in 2")
        await asyncio.sleep(1)
        await self.bot.edit_message(message=christmas_message, new_content="Christmas time in 1")
        await asyncio.sleep(1)
        await self.bot.edit_message(message=christmas_message,
                                    new_content="%s MERRY CHRISTMAS %s" % (str(padoru_string), str(padoru_string)))
        members = sorted([member for member in server.members if role in member.roles], key=lambda m:m.name.lower())
        for index,member in enumerate(members):
            if index % 2 == 0:
                await self.bot.add_roles(member,red_role)
            else:
                await self.bot.add_roles(member,green_role)

    async def get_christmas_roles(self, server):
        role_red = discord.utils.get(server.roles, name="ChristmasSoviets")
        role_green = discord.utils.get(server.roles, name="PadoruPatrol")
        if not role_red and not role_green:
            role_red = await self.bot.create_role(server=server, name="ChristmasSoviets",color=discord.Color(int("c62f2f",16)))
            role_green = await self.bot.create_role(server=server, name="PadoruPatrol",color=discord.Color(int("157718",16)))
        return role_red, role_green


def setup(bot):
    bot.add_cog(Christmas(bot))
