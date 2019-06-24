# -*- coding: utf-8 -*-

from discord.ext import commands
import asyncio
import discord
from typing import Optional
from random import choice
class Quotes(commands.Cog):
    """Save and get random quotes provided and added by the users"""

    def __init__(self, bot):
        self.bot = bot
        with open("data/quotes.txt", "r", encoding="utf-8") as f:
            self.quotes = f.readlines()

    @commands.command(usage="**quoted text** - user, 20XX (for adding quote)\n.quote [number] (for specific quote)\n.quote (for random quote)")
    async def quote(self, ctx, number: Optional[int], *, quote: Optional[commands.clean_content]):
        """add a quote by writing it down or get a random or specific quote """
        if number and not quote and number-1 < len(self.quotes) and number > 0:
            await ctx.send(self.quotes[number-1])
            return
        if not quote:
            mes = None
            if number and (number-1 >= len(self.quotes) or number <= 0):
                mes = await ctx.send("quote number not found sending random quote...")
            if mes:
                await asyncio.sleep(3)
                await mes.edit(content=choice(self.quotes))
            else:
                await ctx.send(choice(self.quotes))
            return
        else:
            with open("data/quotes.txt", "a", encoding="utf-8") as f:
                if number:
                    quote = f"{number} {quote}"
                f.write(f"{quote}\n")
                self.quotes.append(f"{quote}\n")
                await ctx.send("quote added")

    @commands.command()
    async def allquotes(self, ctx):
        """will send you all quotes in a DM
        WILL BE MULTIPLE MESSAGES LONG DEPENDING ON HOW MANY QUOTES THERE ARE
        """
        paginator = commands.Paginator()
        for index, quote in enumerate(self.quotes):
            paginator.add_line(f"{index+1}) {quote}")

        try:
            for page in paginator.pages:
                await ctx.author.send(page)
        except discord.Forbidden:
            await ctx.send("Cannot send message, be sure to enable messages from server members")
            return
    @commands.has_any_role("Discord-Senpai", 379022249962897408, 336382505567387651)
    @commands.command(name="qdel")
    async def del_quote(self, ctx, number: int):
        """deletes the quote specified by number"""
        if number-1 < 1 or number-1 >= len(self.quotes):
            await ctx.send(f"Invalid quote number, this number is either too big or smaller than 1, please use a number"
                           f"smaller or equal to {len(self.quotes)}")
            return
        self.quotes.pop(number-1)
        with open("data/quotes.txt", "w") as f:
            f.writelines(self.quotes)
        await ctx.send(f"quote #{number} deleted")







def setup(bot):
    bot.add_cog(Quotes(bot))
