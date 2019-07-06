# -*- coding: utf-8 -*-

from discord.ext import commands
import discord
from .utils.paginator import TextPages
from typing import Optional
from random import randint, choice

class Quotes(commands.Cog):
    """Save and get random quotes provided and added by the users"""

    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.initialize_quote_table())

    async def initialize_quote_table(self):
        query = "CREATE TABLE IF NOT EXISTS quotes (" \
                "number SERIAL PRIMARY KEY, " \
                "text varchar(2000)," \
                "user_id BIGINT);"
        async with self.bot.db.acquire() as conn:
            async with conn.transaction():
                await self.bot.db.execute(query)

    async def fetch_quotes(self):
        query = "SELECT * FROM quotes ORDER BY number"
        async with self.bot.db.acquire() as connection:
            return await connection.fetch(query)

    async def add_quote(self, quote, user_id):
        quote = discord.utils.escape_mentions(quote)
        async with self.bot.db.acquire() as conn:
            stmt = await conn.prepare("INSERT INTO quotes (number, text, user_id) VALUES (DEFAULT, $1, $2)\n"
                                      "                                         RETURNING number;")
            async with conn.transaction():
                return await stmt.fetchval(quote, user_id)

    async def remove_quote(self, number):
        async with self.bot.db.acquire() as conn:
            stmt = await conn.prepare("DELETE FROM quotes WHERE number = $1\n "
                                      "RETURNING *")
            async with conn.transaction():
                return await stmt.fetchrow(number)

    async def fetch_single_quote(self, number):
        async with self.bot.db.acquire() as conn:
            stmt = await conn.prepare("SELECT * FROM quotes WHERE number = $1")
            async with conn.transaction():
                return await stmt.fetchrow(number)


    async def fetch_quotes_from_user(self, member_id: int):
        async with self.bot.db.acquire() as conn:
            stmt = await conn.prepare("SELECT * FROM quotes WHERE user_id = $1 ORDER BY number")
            async with conn.transaction():
                return await stmt.fetch(member_id)

    @commands.command(usage="**quoted text** - user, 20XX (for adding quote)\n.quote [number] (for specific quote)\n.quote (for random quote)")
    async def quote(self, ctx, number: Optional[int], *, quote: Optional[commands.clean_content]):
        """add a quote by writing it down or get a random or specific quote """
        quotes = await self.fetch_quotes()

        if number and not quote:
            quote = next(iter(q for q in quotes if q["number"] == number), None)
            if quote:
                await ctx.send(f"{quote['number']}) {quote['text']}")
            else:
                quote = choice(quotes)
                await ctx.send("quote was deleted send random quote instead...")
                await ctx.send(f"{quote['number']}) {quote['text']}")
            return
        elif not quote:
            quote = choice(quotes)
            await ctx.send(f"{quote['number']}) {quote['text']}")
        else:
            if number:
                quote = str(number) + quote
            new_quote_number = await self.add_quote(quote, ctx.author.id)
            await ctx.send(f"quote #{new_quote_number} added")


    @commands.command()
    async def allquotes(self, ctx):
        """will send you all quotes in a DM
        """
        lines = []
        for quote in await self.fetch_quotes():
            lines.append(f"{quote['number']}) {quote['text']}")

        try:
            pages = TextPages(ctx, '\n'.join(lines))
            dm_channel = ctx.author.dm_channel
            if dm_channel:
                pages.channel = ctx.author.dm_channel
            else:
                pages.channel = await ctx.author.create_dm()
            await pages.paginate()
        except discord.Forbidden as e:
            await ctx.send("couldn't send message to user, be sure to have DMs from server members enabled")
            return

    @commands.has_any_role("Discord-Senpai", 379022249962897408, 336382505567387651)
    @commands.command(name="qdel")
    async def del_quote(self, ctx, number: int):
        """deletes the quote specified by number"""
        response = await self.remove_quote(number)
        if response:
            await ctx.send(f"quote #{response['number']} deleted")
        else:
            await ctx.send("quote was already deleted")


    @commands.has_any_role("Discord-Senpai", 379022249962897408, 336382505567387651)
    @commands.command(name="qinfo")
    async def info_quote(self, ctx, number: Optional[int], by_member: Optional[discord.Member]):
        """shows who added what quote(s)"""
        if by_member:
            lines = []
            for quote in await self.fetch_quotes_from_user(by_member.id):
                lines.append(f"{quote['number']}) {quote['text']}")
            if not lines:
                await ctx.send("No quotes added by this user")
                return
            pages = TextPages(ctx, '\n'.join(lines))
            await pages.paginate()
        elif number:
            quote = await self.fetch_single_quote(number)
            if quote:
                added_by_string = f"added by <@{quote['user_id']}>" if quote['user_id'] else ""
                await ctx.send(f"{quote['number']}) {quote['text']} {added_by_string}")
        else:
            await ctx.send("either provide a user or a number")



    @commands.command(name="lquotes")
    @commands.is_owner()
    async def load_quotes(self, ctx):
        with open("data/quotes.txt", 'rb') as f:
            async with self.bot.db.acquire() as con:
                result = await con.copy_to_table(
                    'quotes', columns=['text'], source=f, format="text"
                )
                await ctx.send(result)
                await con.execute("DELETE FROM quotes WHERE text = '[Removed Quote]'")








def setup(bot):
    bot.add_cog(Quotes(bot))
