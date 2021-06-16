# -*- coding: utf-8 -*-

from discord.ext import commands, tasks
import discord
import logging
import colorsys

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
    @commands.command(name="mycolor", aliases=["mc", "my_color"])
    @is_boost()
    async def set_boost_color(self, ctx: commands.Context, colour : discord.Colour):
        """
        Set your own colour (Boost exclusive) 
        Will create a role for you 
        """
        h, s ,v = colorsys.rgb_to_hsv(colour.r, colour.g, colour.b)
        if v < 70 and v > 45 and s < .20:
            return await ctx.send(f"Colour too dark/too close to discord grey.")
        elif v > 229 and s < 0.10:
            return await ctx.send(f"Colour too bright/too close to discord white.")
        color_role_entry = await self.bot.db.fetchrow('''
        SELECT * FROM boost_color WHERE user_id = $1
        ''', ctx.author.id)
        if color_role_entry:
            role = ctx.guild.get_role(color_role_entry.get('role_id'))
            await role.edit(colour=colour)
        else:
            top_role : discord.Role = ctx.author.top_role
            new_role = await ctx.guild.create_role(name=ctx.author.name, colour=colour)
            if top_role < ctx.guild.me.top_role:
                await new_role.edit(position=top_role.position)
            else:
                top_color_role = sorted(filter(lambda r: r.color != discord.Colour.default() ,ctx.author.roles)).pop()
                await new_role.edit(position=top_color_role.position)
            await ctx.author.add_roles(new_role)
            await self.bot.db.execute('''
            INSERT INTO boost_color (user_id, role_id, guild_id, color_val)
            VALUES ($1, $2, $3, $4)
            ''', ctx.author.id, new_role.id, ctx.guild.id, colour.value)
        await ctx.send("New color assigned")
    
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
