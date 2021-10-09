# -*- coding: utf-8 -*-

from discord.ext import commands, tasks
from typing import Union
import discord
import logging
import colorsys
import aiohttp

class NotBoostError(commands.CheckFailure):
    pass

def is_boost():
    async def predicate(ctx : commands.Context):
        if ctx.guild:
            if ctx.author.premium_since:
                return True
            else:
                raise NotBoostError("You need to boost the server")
        else:
            raise NotBoostError("This command only works inside a server")

    return commands.check(predicate=predicate)

class Boost(commands.Cog):
    """The description for Boost goes here."""

    def __init__(self, bot: commands.Bot):
        self.bot : commands.Bot = bot
        self.log : logging.Logger = logging.getLogger("PoutyBot")
        self.bot.loop.create_task(self.create_booster_color_table())
        self.clean_non_boost_roles.start()
    
    async def create_booster_color_table(self):
        await self.bot.db.execute('''
        CREATE TABLE IF NOT EXISTS boost_color (
            user_id BIGINT PRIMARY KEY,
            role_id BIGINT,
            guild_id BIGINT,
            color_val INTEGER
        )
        ''')
    @commands.command(name="mycolor", aliases=["mc"])
    @commands.cooldown(rate=1, per=300, type=commands.BucketType.user)
    @is_boost()
    async def set_boost_color(self, ctx: commands.Context, colour : discord.Colour):
        """
        Set your own colour (Boost exclusive) 
        Will create a role for you 
        """
        h, s ,v = colorsys.rgb_to_hsv(colour.r, colour.g, colour.b)
        if v < 20:
            self.set_boost_color.reset_cooldown(ctx)
            return await ctx.send(f"Colour too dark/too close to discord amoled.")
        if v < 70 and s < .20:
            self.set_boost_color.reset_cooldown(ctx)
            return await ctx.send(f"Colour too dark/too close to discord grey.")
        elif v > 229 and s < 0.10:
            self.set_boost_color.reset_cooldown(ctx)
            return await ctx.send(f"Colour too bright/too close to discord white.")
        color_role_entry = await self.bot.db.fetchrow('''
        SELECT * FROM boost_color WHERE user_id = $1
        ''', ctx.author.id)
        top_role = ctx.guild.premium_subscriber_role
        if not top_role:
            top_role = ctx.author.top_role
        if color_role_entry:
            role = ctx.guild.get_role(color_role_entry.get('role_id'))
            await role.edit(colour=colour, position=top_role.position +1)
        else:
            new_role = await ctx.guild.create_role(name=ctx.author.name, colour=colour)
            if top_role < ctx.guild.me.top_role:
                await new_role.edit(position=top_role.position + 1)
            else:
                top_color_role = sorted(filter(lambda r: r.color != discord.Colour.default() ,ctx.author.roles)).pop()
                await new_role.edit(position=top_color_role.position+1)
            await ctx.author.add_roles(new_role)
            await self.bot.db.execute('''
            INSERT INTO boost_color (user_id, role_id, guild_id, color_val)
            VALUES ($1, $2, $3, $4)
            ''', ctx.author.id, new_role.id, ctx.guild.id, colour.value)
        await ctx.send("New color assigned")

    @set_boost_color.error
    async def boost_error(self, ctx, error):
        default = self.bot.get_cog("Default")
        if isinstance(error, commands.CommandOnCooldown):
            await default.cooldown_embed(ctx, error)
        else:
            self.set_boost_color.reset_cooldown(ctx)
            await default.create_and_send_traceback(ctx, error)    

    @commands.group(name="myicon", aliases=['mi', 'icon'], invoke_without_command=True)
    @commands.guild_only()
    @is_boost()
    async def set_role_icon(self, ctx, icon : Union[discord.Emoji, discord.PartialEmoji, str] = None):
        """
        set a role icon for yourself, this will be attached to your boost colour role
        so you need to have that set first, use `.mc purple`
        """
        if 'ROLE_ICONS' not in ctx.guild.features:
            return await ctx.send("Server lacks the guild icon feature")

        role_id = await self.bot.db.fetchval('''
            SELECT role_id FROM boost_color WHERE user_id = $1
        ''', ctx.author.id)
        role = ctx.guild.get_role(role_id)
        if not role:
            await ctx.send("Couldn't get boost colour role, please set one first")
        if isinstance(icon, discord.Emoji):
            await role.edit(icon=await icon.read())
        elif isinstance(icon, discord.PartialEmoji) and icon.is_custom_emoji():
            await role.edit(icon=await icon.read())
        elif isinstance(icon, str) and icon.startswith("http"):
            async with self.bot.session.get(url=icon, raise_for_status=True) as resp:
                await role.edit(icon= await resp.read())
        elif icon is None and ctx.message.attachments:
            icon = ctx.message.attachments[0]
            await role.edit(icon= await icon.read())
        else:
            return await ctx.send("Please upload an attachment or provide a link to an image for your icon")
        await ctx.send("role icon updated")
    @is_boost()
    @commands.guild_only()
    @set_role_icon.command("delete", aliases=["remove", "rm"])
    async def delete_role_icon(self, ctx):
        """
        remove your role icon
        """
        if 'ROLE_ICONS' not in ctx.guild.features:
            return await ctx.send("Server lacks the guild icon feature")

        role_id = await self.bot.db.fetchval('''
            SELECT role_id FROM boost_color WHERE user_id = $1
        ''', ctx.author.id)
        role = ctx.guild.get_role(role_id)
        if not role:
            await ctx.send("Couldn't get boost colour role, please set one first")
        await role.edit(icon=None)
        await ctx.send("role icon removed")



    @tasks.loop(hours=1)
    async def clean_non_boost_roles(self):
        boost_roles = await self.bot.db.fetch("""
        SELECT * from boost_color
        """)
        roles_to_delete = []
        for entry in boost_roles:
            guild : discord.Guild = self.bot.get_guild(entry.get('guild_id'))
            role : discord.Role = guild.get_role(entry.get('role_id'))
            member : discord.Member = guild.get_member(entry.get('user_id'))
            if not member:
                try:
                    member = await guild.fetch_member(entry.get('user_id'))
                except Exception as e:
                    self.log.warn("Could not fetch member ({}) deleting role {} [{}]: {}", entry.get('user_id'), role.name, role.id, e)
                    roles_to_delete.append(role)
            if not member.premium_since:
                roles_to_delete.append(role)

        for role in roles_to_delete:
            self.log.debug(f"Deleting role {role.name} (id: {role.id})")
            await self.bot.db.execute('''
            DELETE FROM boost_color WHERE role_id = $1
            ''', role.id)
            await role.delete()

def setup(bot):
    bot.add_cog(Boost(bot))
