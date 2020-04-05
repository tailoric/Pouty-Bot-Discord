import discord
from discord.ext import commands
from .utils import checks, paginator
from typing import Optional


class Payday(commands.Cog):
    """
    commands for getting your hourly salary
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.loop.create_task(self.setup_payday_table())
        self.start_amount = 1000
        self.salary = 150

    async def setup_payday_table(self):
        query = ("CREATE TABLE IF NOT EXISTS payday ("
                 "user_id BIGINT PRIMARY KEY,"
                 "money BIGINT)")
        await self.bot.db.execute(query)

    async def fetch_money(self, user_id):
        async with self.bot.db.acquire() as connection:
            query = ("SELECT money from payday WHERE user_id = $1")
            statement = await connection.prepare(query)
            async with connection.transaction():
                return await statement.fetchrow(user_id)

    async def insert_new_user(self, user_id, start_amount):
        async with self.bot.db.acquire() as connection:
            query = ("INSERT INTO payday VALUES ($1, $2)")
            statement = await connection.prepare(query)
            async with connection.transaction():
                return await statement.fetch(user_id, start_amount)

    async def add_money(self, user_id, amount):
        async with self.bot.db.acquire() as connection:
            get_money = ("SELECT money from payday WHERE user_id = $1")
            set_money = ("UPDATE payday SET money = $2 WHERE user_id = $1 "
                         "RETURNING money")
            statement_get = await connection.prepare(get_money)
            statement_set = await connection.prepare(set_money)
            async with connection.transaction():
                money = await statement_get.fetchval(user_id)
                money += amount
                return await statement_set.fetchval(user_id, money)

    async def subtract_money(self, user_id, amount):
        async with self.bot.db.acquire() as connection:
            get_money = ("SELECT money from payday WHERE user_id = $1")
            set_money = ("UPDATE payday SET money = $2 WHERE user_id = $1 "
                         "RETURNING money")
            statement_get = await connection.prepare(get_money)
            statement_set = await connection.prepare(set_money)
            async with connection.transaction():
                money = await statement_get.fetchval(user_id)
                money -= amount
                if money < 0:
                    raise commands.CommandError("Sorry you don't have enough money for this transfer")
                return await statement_set.fetchval(user_id, money)

    async def get_leaderboards(self):
        return await self.bot.db.fetch("SELECT * from payday order by money desc limit 10")

    @commands.command(name="payday", aliases=["pd"])
    @checks.channel_only("bot-shenanigans", "test", 336912585960194048)
    @commands.cooldown(rate=1, per=3600, type=commands.BucketType.user)
    async def payday_command(self, ctx):
        """claim your salary once every hour or open a new account with start capital"""
        member = ctx.author
        entry = await self.fetch_money(member.id)
        if not entry:
            await self.insert_new_user(member.id, self.start_amount)
            return await ctx.send(f"New user with starting capital of {self.start_amount}")
        new_balance = await self.add_money(member.id, self.salary)
        await ctx.send(f"added {self.salary} to your account your balance is now {new_balance:,}")

    @payday_command.error
    async def payday_error(self, ctx, error):

        if isinstance(error, commands.CommandOnCooldown):
            minutes, seconds = divmod(error.retry_after, 60)
            error.handled = True
            await ctx.send(f"On cooldown retry after {int(minutes)} min and {int(seconds)} sec")

    @commands.command(name="transfer")
    async def transfer_money(self, ctx, amount: int, receiver: discord.Member):
        """send money to someone"""
        entry = await self.fetch_money(receiver.id)
        if not entry:
            await self.insert_new_user(receiver.id, self.start_amount)
        spender = ctx.author
        spender_money = await self.subtract_money(spender.id, amount)
        receiver_money = await self.add_money(receiver.id, amount)

        await ctx.send(f"{spender.mention} transferred {amount} to {receiver.mention}\n"
                       f"{spender.mention} balance: {spender_money:,} \n"
                       f"{receiver.mention} balance: {receiver_money:,}")

    @commands.command(aliases=["bal"])
    async def balance(self, ctx, member: Optional[discord.Member]):
        """see your account balance"""
        account_user = ctx.author
        if member: 
            account_user = member
        entry = await self.fetch_money(account_user.id)
        if not entry and account_user == ctx.author:
            await self.insert_new_user(account_user.id, self.start_amount)
            return await ctx.send(f"Registered a new user with starting capital of {self.start_amount}")
        if not entry and account_user != ctx.author:
            return await ctx.send("This user has no balance value yet")
        balance = await self.fetch_money(account_user.id)
        await ctx.send(f"**{account_user.display_name}'s** account balance is {balance.get('money'):,}")
        


    @commands.command(name="leaderboards", aliases=["lb"])
    async def leaderboards_command(self, ctx):
        """see who is the biggest earner on the server"""
        leaderboards = await self.get_leaderboards()
        pages = []
        for idx, entry in enumerate(leaderboards):
            user = ctx.guild.get_member(entry.get("user_id"))
            if not user:
                user = await self.bot.fetch_user(entry.get("user_id"))
                pages.append((f"**{idx+1}**. {user.name}#{user.discriminator}", f"{entry['money']:,}"))
                continue
            pages.append((f"**{idx+1}**. {user.display_name}", f"{entry['money']:,}"))

        f_pages = paginator.FieldPages(ctx, entries=pages)
        await f_pages.paginate()


def setup(bot):
    bot.add_cog(Payday(bot))
