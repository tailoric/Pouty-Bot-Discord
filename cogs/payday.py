import discord
from discord.ext import commands
from .utils import checks, paginator
from typing import Optional
from datetime import datetime, timedelta
from discord.ext import menus
from asyncpg import Record

class LeaderBoardSource(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=10)

    async def format_page(self, menu, entries : Record):
        offset = menu.current_page * self.per_page
        embed = discord.Embed(title="Leaderboards", colour=discord.Colour.blurple())
        for idx,entry in enumerate(entries, start=offset):
            user = await self.get_user(entry.get('user_id'), menu.ctx)
            embed.add_field(name=f"{idx+1}. {user.display_name}", value=f"{entry.get('money'):,}", inline=False)
        return embed

    async def get_user(self, user_id, ctx):
        user = ctx.guild.get_member(user_id)
        if not user:
            user = ctx.bot.get_user(user_id)
        if not user:
            user = await ctx.bot.fetch_user(user_id)
        return user




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
                new_amount = await statement_set.fetchval(user_id, money)
                return new_amount

    async def subtract_money(self, user_id, amount):
        async with self.bot.db.acquire() as connection:
            if amount < 0:
                raise commands.CommandError("No negative amounts allowed")
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
        return await self.bot.db.fetch("SELECT * from payday order by money desc")

    @commands.command(name="payday", aliases=["pd"])
    @commands.guild_only()
    @checks.channel_only("bot-shenanigans", "test", 336912585960194048)
    @commands.cooldown(rate=1, per=3600, type=commands.BucketType.user)
    async def payday_command(self, ctx):
        """claim your salary once every hour or open a new account with start capital"""
        member = ctx.author
        entry = await self.fetch_money(member.id)
        salary = self.salary
        is_boost = ctx.author in ctx.guild.premium_subscribers
        if is_boost:
            salary += 50
        if not entry:
            await self.insert_new_user(member.id, self.start_amount)
            return await ctx.send(f"New user with starting capital of {self.start_amount}")
        new_balance = await self.add_money(member.id, salary)
        line_len = max(len(f"{entry['money']:,}"), len(f'+{salary,}'), len(f'{new_balance:,}'))
        new_bal_str = f"{new_balance:,}".rjust(line_len + 1)
        old_bal = f"{entry['money']:,}".rjust(line_len + 1)
        salary_str = "+" + f"{salary:,}".rjust(line_len)
        if ctx.guild and ctx.guild.me.colour:
            colour = ctx.guild.me.colour
        else:
            colour = discord.Colour.blurple()
        embed = discord.Embed(title="Payday!", description=f"```\n{old_bal}\n{salary_str}\n{'_' * (line_len+1)}\n{new_bal_str}\n```", colour=colour)
        if is_boost:
            embed.add_field(name=f"Bonus for {ctx.guild.premium_subscriber_role.name}", value=50)
        embed.timestamp = (datetime.utcnow() + timedelta(hours=1))
        embed.set_footer(text="Next payday at:")
        await ctx.send(embed=embed)

    @payday_command.error
    async def payday_error(self, ctx, error):

        if isinstance(error, commands.CommandOnCooldown):
            minutes, seconds = divmod(error.retry_after, 60)
            error.handled = True
            if ctx.guild and ctx.guild.me.colour:
                colour = ctx.guild.me.colour
            else:
                colour = discord.Colour.blurple()
            await ctx.send(embed=discord.Embed(title="Payday!",
                description=f"On cooldown retry after {int(minutes)} min and {int(seconds)} sec",
                timestamp=datetime.utcnow() + timedelta(seconds=error.retry_after),
                colour=colour
                ))

    @commands.command(name="transfer")
    async def transfer_money(self, ctx, amount: int, *, receiver: discord.Member):
        """send money to someone"""
        if amount <= 0:
            return await ctx.send("invalid amount please only transfer more than 0.")
        entry = await self.fetch_money(receiver.id)
        if not entry:
            await self.insert_new_user(receiver.id, self.start_amount)
        spender = ctx.author
        spender_money = await self.subtract_money(spender.id, amount)
        receiver_money = await self.add_money(receiver.id, amount)

        if ctx.guild and ctx.guild.me.colour:
            colour = ctx.guild.me.colour
        else:
            colour = discord.Colour.blurple()
        embed = discord.Embed(title="Money transfer", description=f"{spender.mention} \N{RIGHTWARDS ARROW} {amount:,} \N{RIGHTWARDS ARROW} {receiver.mention}", colour=colour)
        embed.add_field(name=f"{spender} balance", value=f"{spender_money+amount:,} \N{RIGHTWARDS ARROW} {spender_money:,}")
        embed.add_field(name=f"{receiver} balance", value=f"{receiver_money-amount:,} \N{RIGHTWARDS ARROW} {receiver_money:,}")
        await ctx.send(embed=embed)

    @commands.command(aliases=["bal"])
    async def balance(self, ctx, *, member: Optional[discord.Member]):
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
        await ctx.send(f"**{account_user.display_name}'s** account balance is {entry.get('money'):,}")
        


    @commands.command(name="leaderboards", aliases=["lb"])
    @commands.guild_only()
    async def leaderboards_command(self, ctx):
        """see who is the biggest earner on the server"""
        leaderboards = await self.get_leaderboards()
        pages = menus.MenuPages(source=LeaderBoardSource(leaderboards), clear_reactions_after=True)
        await pages.start(ctx)


def setup(bot):
    bot.add_cog(Payday(bot))
