import discord
from discord.ext import commands, tasks
from typing import Optional
import re

nintendo_fc_regex = re.compile(r'^(SW)?[- ]?\d{4}[- ]\d{4}[- ]\d{4}$')
slippi_code_regex = re.compile(r'^[A-Z]{2,4}#\d{3}$')
grand_order_regex = re.compile(r'^\d{3}[, ]\d{3}[, ]\d{3}$')
class NintendoCode(commands.Converter):
    async def convert(self, ctx, argument):
        match = nintendo_fc_regex.match(argument)
        if match:
            return match.group(0)
        raise commands.BadArgument('Please provide a valid Friend Code.')

class slippiCode(commands.Converter):
    async def convert(self, ctx, argument):
        match = slippi_code_regex.match(argument)
        if match:
            return match.group(0)
        raise commands.BadArgument('Please provide a valid Slippi Code.')

class GrandOrderCode(commands.Converter):
    async def convert(self, ctx, argument):
        match = grand_order_regex.match(argument)
        if match:
            return match.group(0)
        raise commands.BadArgument('Please provide a valid GrandOrder user id.')

class FriendCodes(commands.Cog):
    """
    Cog for handling friend codes (supports slippi and nintendo codes)
    """
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.build_friend_code_table())
        self.bot.loop.create_task(self.migrations())
    async def migrations(self):
        query = '''
         ALTER TABLE friend_codes ADD COLUMN IF NOT EXISTS grand_order VARCHAR(12)
         '''
        async with self.bot.db.acquire() as con:
            async with con.transaction():
                await self.bot.db.execute(query)
    async def build_friend_code_table(self):
        query = '''
            CREATE TABLE IF NOT EXISTS friend_codes(
                user_id BIGINT PRIMARY KEY NOT NULL,
                nintendo_code varchar(20),
                slippi_code varchar(10)
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
    async def update_slippi_code(self, user_id, slippi_code):
        fetch_query = '''
            SELECT user_id 
            FROM friend_codes 
            WHERE user_id = $1
        '''
        update_query = '''
            UPDATE friend_codes 
            SET slippi_code = $2
            WHERE user_id = $1
        '''
        insert_query = '''
            INSERT INTO friend_codes (user_id, slippi_code) 
            VALUES ($1, $2)
        '''
        result = await self.bot.db.fetchval(fetch_query, user_id)
        async with self.bot.db.acquire() as connection:
            if result:
                statement = await connection.prepare(update_query)
                async with connection.transaction():
                    return await statement.fetch(user_id, slippi_code)
            else:
                statement = await connection.prepare(insert_query)
                async with connection.transaction():
                    return await statement.fetch(user_id, slippi_code)

    async def update_grand_order(self, user_id, grand_order):
        fetch_query = '''
            SELECT user_id 
            FROM friend_codes 
            WHERE user_id = $1
        '''
        update_query = '''
            UPDATE friend_codes 
            SET grand_order = $2
            WHERE user_id = $1
        '''
        insert_query = '''
            INSERT INTO friend_codes (user_id, grand_order) 
            VALUES ($1, $2)
        '''
        result = await self.bot.db.fetchval(fetch_query, user_id)
        async with self.bot.db.acquire() as connection:
            if result:
                statement = await connection.prepare(update_query)
                async with connection.transaction():
                    return await statement.fetch(user_id, grand_order)
            else:
                statement = await connection.prepare(insert_query)
                async with connection.transaction():
                    return await statement.fetch(user_id, grand_order)
    async def update_nintendo_code(self, user_id, nintendo_code):
        fetch_query = '''
            SELECT user_id 
            FROM friend_codes 
            WHERE user_id = $1
        '''
        update_query = '''
            UPDATE friend_codes 
            SET nintendo_code = $2
            WHERE user_id = $1
        '''
        insert_query = '''
            INSERT INTO friend_codes (user_id, nintendo_code) 
            VALUES ($1, $2)
        '''
        result = await self.bot.db.fetchval(fetch_query, user_id)
        async with self.bot.db.acquire() as connection:
            if result:
                statement = await connection.prepare(update_query)
                async with connection.transaction():
                    return await statement.fetch(user_id, nintendo_code)
            else:
                statement = await connection.prepare(insert_query)
                async with connection.transaction():
                    return await statement.fetch(user_id, nintendo_code)

        
    @commands.group(name="friend-codes", aliases=["fc", "friendc"])
    async def friend_codes(self, ctx, user: Optional[discord.Member]):
        """
        Get the friend code of a user
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

    @friend_codes.group(name="nintendo", aliases=["nd"], invoke_without_command=True)
    async def nintendo_code(self, ctx, *, friend_code: NintendoCode):
        """
        for adding/overwriting your nintendo friend code
        """
        if friend_code:
            await self.update_nintendo_code(ctx.author.id, friend_code)
            return await ctx.send(f"Set your nintendo friend code to {friend_code}")

    @nintendo_code.command(name="rm", aliases=["remove"])
    async def nintendo_code_remove(self, ctx):
        """
        remove your slippi code
        """
        await self.update_nintendo_code(ctx.author.id, None)
        await ctx.send("code removed")

    @friend_codes.group(name="slippi", aliases=["sl"], invoke_without_command=True)
    async def slippi_code(self, ctx, slippi_code: slippiCode):
        """
        for adding/overwriting your slippi connect code
        """
        if ctx.invoked_subcommand:
            return
        if slippi_code:
            await self.update_slippi_code(ctx.author.id, slippi_code)
            return await ctx.send(f"Set your slippi connect code to {slippi_code}")

    @slippi_code.command(name="rm", aliases=["remove"])
    async def slippi_code_remove(self, ctx):
        """
        remove your slippi code
        """
        await self.update_slippi_code(ctx.author.id, None)
        await ctx.send("code removed")

    @friend_codes.group(name="grand_order", aliases=["go"], invoke_without_command=True)
    async def grand_order_code(self, ctx, *,grand_order: GrandOrderCode):
        """
        for adding/overwriting your GrandOrder user id
        """
        if ctx.invoked_subcommand:
            return
        if grand_order:
            await self.update_grand_order(ctx.author.id, grand_order)
            return await ctx.send(f"Set your grand order connect code to {grand_order}")

    @grand_order_code.command(name="rm", aliases=["remove"])
    async def grand_order_remove(self, ctx):
        """
        remove your grand order code
        """
        await self.update_grand_order(ctx.author.id, None)
        await ctx.send("code removed")
def setup(bot):
    bot.add_cog(FriendCodes(bot))
