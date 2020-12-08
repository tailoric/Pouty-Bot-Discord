import discord
from discord.ext import commands, tasks
from typing import Optional
import re
import json
from functools import partial

class CodeRegexCheck(commands.Converter):
    async def convert(self, ctx, argument):
        regex_dict = {}
        with open('config/fc_codes.json', 'r') as f:
            for entry in json.load(f):
                regex_dict[entry.get('name')] = entry.get('regex')
        regex = re.compile(regex_dict.get(ctx.command.name))
        match = regex.match(argument)
        if match:
            return match.group(0)
        else:
            raise commands.BadArgument(f"Please provide a valid {ctx.command.name.title()} code\nIt must match the following regex: {regex_dict.get(ctx.command.name)}")


class FriendCodes(commands.Cog):
    """
    Get Friend codes for various games of other users or set your own
    """
    def __init__(self, bot):
        with open("config/fc_codes.json", 'r') as f:
            self.groups = json.load(f)
        self.examples = {}
        for group in self.groups:
            self.examples[group['name']] = group['example']
        self.bot = bot
        self.bot.loop.create_task(self.create_table())
        for group in self.groups:
            callback = partial(self.set_code, column_name=group['name'])
            new_group = commands.Group(name=group['name'],func=callback.func)
            new_group.help = group['help']
            new_group.aliases = group['aliases']
            remove_command = commands.Command(name="remove",aliases=["rm"], func=self.code_remove)
            new_group.add_command(remove_command)
            self.friend_codes.add_command(new_group)


    async def create_table(self):
        await self.build_friend_code_table()
        await self.migrations()

    async def migrations(self):
        query = " ALTER TABLE friend_codes "
        for group in self.groups:
            query += f"ADD COLUMN IF NOT EXISTS {group['name']} varchar({group['charLength']}),"
        query = query[:-1]
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await self.bot.db.execute(query)
    async def build_friend_code_table(self):
        query = '''
            CREATE TABLE IF NOT EXISTS friend_codes(
                user_id BIGINT PRIMARY KEY NOT NULL
            )
        '''
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await self.bot.db.execute(query)

    async def fetch_codes(self, user_id):
        query = '''
        SELECT *
        FROM friend_codes
        WHERE user_id = $1
        '''
        return await self.bot.db.fetchrow(query, user_id)

    async def fetch_game_code(self, user_id, game):
        query = f'''
        SELECT {game}
        FROM friend_codes
        WHERE user_id = $1
        '''
        return await self.bot.db.fetchval(query, user_id)
    async def update_code(self, user_id, code, column_name):
        fetch_query = '''
            SELECT user_id 
            FROM friend_codes 
            WHERE user_id = $1
        '''
        update_query = f"UPDATE friend_codes SET {column_name} = $2 WHERE user_id = $1"
        insert_query = f"INSERT INTO friend_codes (user_id, {column_name}) VALUES ($1, $2)"
        result = await self.bot.db.fetchval(fetch_query, user_id)
        async with self.bot.db.acquire() as connection:
            if result:
                statement = await connection.prepare(update_query)
                async with connection.transaction():
                    return await statement.fetch(user_id, code)
            else:
                statement = await connection.prepare(insert_query)
                async with connection.transaction():
                    return await statement.fetch(user_id, code)
        
    @commands.group(name="friend-codes", aliases=["fc", "friendc"])
    async def friend_codes(self, ctx, user: Optional[discord.Member]):
        """
        Get the friend code of a user or set your own via the sub commands (see below)
        To search the friend code of a specific game use `.fc gameName username`
        """
        message_parts = ctx.message.content.split()
        no_code_message = "This user has no codes set"
        if len(message_parts) == 1 and ctx.invoked_subcommand is None:
            user = ctx.author
        if user:
            row = await self.fetch_codes(user.id)
            if not row:
                return await ctx.send(no_code_message)
            embed = discord.Embed(title=user.display_name, colour=user.colour)
            for k,v in row.items():
                if k != "user_id" and row.get(k, None):
                    embed.add_field(name=k.replace("_"," ").title(),value=row[k], inline=False)

            embed.set_thumbnail(url=user.avatar_url_as())
            return await ctx.send(embed=embed)
        if len(message_parts) > 1 and ctx.invoked_subcommand is None:
            return await ctx.send(f"No user `{message_parts[1]}` found, use `{ctx.prefix}help fc ` for more help.")

    async def set_code(self, ctx, user: Optional[discord.Member],*, code: Optional[CodeRegexCheck]):
        """
        for adding/overwriting 
        """
        if code:
            await self.update_code(ctx.author.id, code, ctx.command.name)
            column = ctx.command.name.replace("_"," ").title()
            return await ctx.send(f"Set your {column} code to {code}")
        if user:
            embed = discord.Embed(title=user.display_name, colour=user.colour)
            embed.set_thumbnail(url=user.avatar_url_as())
            game = await self.fetch_game_code(user.id, ctx.command.name)
            embed.add_field(name=ctx.command.name.replace("_", " ").title(), value=game)
            return await ctx.send(embed=embed)
        else:
            return await ctx.send(f"Could not find valid code or valid user please try again.\n"
                    f"Example of a valid code: `{self.examples.get(ctx.command.name)}`")
        

    async def code_remove(self, ctx):
        """
        remove your code
        """
        await self.update_code(ctx.author.id, None, ctx.command.name)
        await ctx.send("code removed")

def setup(bot):
    bot.add_cog(FriendCodes(bot))
