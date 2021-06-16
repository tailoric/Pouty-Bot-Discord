import discord
from discord.utils import get, find
from discord.ext import commands,tasks
from typing import Optional
from .utils.dataIO import DataIO
import datetime
import logging

def has_birthday_role():
    async def predicate(ctx):
        if not ctx.guild:
            raise commands.CommandError("You can't use this command in a DM")
        bday_roles = [role for role in ctx.author.roles if "birthday" in role.name.lower()]
        if bday_roles:
            return True
        else:
            raise commands.CommandError("You are not allowed to use this command since you don't have"
                                        "the birthday role")
    return commands.check(predicate)


class Birthday(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_io = DataIO()
        self.bot.loop.create_task(self.setup_database())
        self.remove_birthday.start()

    def cog_unload(self):
        self.remove_birthday.stop()

    async def insert_new_birthday(self, user_id, guild_id, role_removal_date, changed_color):
        """
        Insert a new birthday entry into the database
        """
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare('''
                INSERT INTO birthday VALUES ($1, $2, $3, $4)
            ''')
            async with connection.transaction():
                await statement.fetch(user_id, guild_id, role_removal_date, changed_color)

    async def fetch_user_bday_status(self, user_id):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare('''
                SELECT * 
                FROM birthday 
                WHERE user_id = $1
            ''')
            async with connection.transaction():
                return await statement.fetchrow(user_id)
    async def fetch_all_birthdays(self):
        """
        get all birthdays from the database
        """
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare('''
                SELECT user_id, guild_id, role_removal_date
                FROM birthday
            ''')
            async with connection.transaction():
                return await statement.fetch()

    async def remove_birthday_entry(self, user_id):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare('''
                DELETE FROM birthday WHERE user_id = $1
            ''')
            async with connection.transaction():
                return await statement.fetch(user_id)
    async def update_birthday_entry_color_change(self, user_id, change_color):
        async with self.bot.db.acquire() as connection:
            statement = await connection.prepare('''
                UPDATE birthday
                SET changed_color = $1
                WHERE user_id = $2
            ''')
            async with connection.transaction():
                return await statement.fetch(change_color, user_id)


    async def setup_database(self):
        query = '''
                        CREATE TABLE IF NOT EXISTS birthday(
                            user_id BIGINT,
                            guild_id BIGINT,
                            role_removal_date timestamp,
                            changed_color boolean
                        );
                '''
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await con.execute(query)

    @commands.has_permissions(manage_roles=True)
    @commands.command(aliases=['bday'])
    async def birthday(self, ctx: commands.Context, member: discord.Member, color: Optional[discord.Color]):
        """assigns the birthday role to the user and removes it after 24 hours"""
        if get(member.roles, name="HUPPIE BIRTHDAY"):
            return await ctx.send("user already has birthday role")
        hoisted_bday_role = next(iter(role for role in ctx.guild.roles
                                      if role.hoist
                                      and role.name == "HUPPIE BIRTHDAY"
                                      ), None)
        bday_role = next(iter(role for role in ctx.guild.roles
                              if role.name == "HUPPIE BIRTHDAY"
                              and not role.members
                              and not role == hoisted_bday_role
                              ), None)
        if not hoisted_bday_role:
            return await ctx.send("no default hoisted birthday role")
        elif bday_role:
            await bday_role.edit(color=color if color else discord.Color.default())
            await member.add_roles(hoisted_bday_role, bday_role)
        else:
            new_role = await ctx.guild.create_role(color=color if color else discord.Color.default(),
                                                name="HUPPIE BIRTHDAY")
            await new_role.edit(position=hoisted_bday_role.position)
            await member.add_roles(new_role, hoisted_bday_role)
        role_removal_date = datetime.datetime.utcnow() + datetime.timedelta(days=1)
        await self.insert_new_birthday(user_id=member.id,
                                       guild_id=ctx.guild.id,
                                       role_removal_date=role_removal_date,
                                       changed_color=False)
        await ctx.send("birthday role assigned successfully")


    @tasks.loop(seconds=5)
    async def remove_birthday(self):
        to_remove = []
        bday_entries = await self.fetch_all_birthdays()
        for entry in bday_entries:
            if entry["role_removal_date"] <= datetime.datetime.utcnow():
                try:
                    guild = get(self.bot.guilds, id=entry["guild_id"])
                    member = get(guild.members, id=entry["user_id"])
                    bday_roles = [role for role in member.roles if role.name == "HUPPIE BIRTHDAY"]
                    if member and guild and bday_roles:
                        await member.remove_roles(*bday_roles)
                except (discord.errors.Forbidden, discord.errors.NotFound):
                    logger = logging.getLogger("PoutyBot")
                    logger.error(e)
                    to_remove.append(entry)
                except discord.errors.HTTPException as e:
                    logger = logging.getLogger("PoutyBot")
                    logger.error(e)
                else:
                    to_remove.append(entry)
        for removal in to_remove:
            await self.remove_birthday_entry(removal["user_id"])

    @commands.command(name="bdc", aliases=["bdaycolor", "my_colour", "bdaycolour"])
    @has_birthday_role()
    async def bday_color_change(self, ctx, color: discord.Color):
        """
        change your own birthday role color once
        """
        bday_entry = await self.fetch_user_bday_status(ctx.author.id)
        if bday_entry["changed_color"]:
            return await ctx.send("you already changed your color once")
        bday_role = [role for role in ctx.author.roles if "HUPPIE BIRTHDAY" in role.name
                     and not role.hoist]
        bday_role.sort(key=lambda elem: elem.position, reverse=True)
        await bday_role[0].edit(color=color)
        await ctx.send(f"your birthday color has been changed to {color}")
        await self.update_birthday_entry_color_change(ctx.author.id, True)

def setup(bot: commands.Bot):
    bot.add_cog(Birthday(bot))
