import discord
from discord.ext import commands
import random
import re
import textwrap
from dataclasses import dataclass

dice_regex = re.compile(r"(?P<number>\d*)d(?P<sides>\d+)((?P<sign>[+-])(?P<modifier>\d+))?", re.I)

class DiceConversionError(commands.BadArgument):
    pass
@dataclass
class Dice:
    number : int
    sides : int
    sign : str
    modifier: int
class DiceConverter(commands.Converter):
    
    async def convert(self, ctx: commands.Context, argument: str):
        match = dice_regex.match(argument)
        if match:
            modifier = match.group("modifier") or 0
            number = match.group("number") or 1
            if match.group("sign") and match.group("sign") not in ["+", "-"]:
                raise DiceConversionError("Could not parse dice notation the format is `ndm` where n is the amount of dice and m is the amount of sides. Example: `2d20` for two d20\n"
                                          "Modifiers can only contain a `+` or `-`")

            return Dice(
                    number=int(number),
                    sides=int(match.group("sides")),
                    sign=match.group("sign"),
                    modifier=int(modifier)
                    )
        else:
            raise DiceConversionError("Could not parse dice notation the format is `ndm` where n is the amount of dice and m is the amount of sides. Example: `2d20` for two d20 ")

class Roll(commands.Cog):
    """
    Roll dice command
    """

    def __init__(self, bot):
        self.bot = bot
        self.char_limit = 2000

    @commands.command()
    async def roll(self, ctx, dice: DiceConverter):
        """
        roll one or multiple die
        example: .roll 1d6 for a 6-sided die
        """
        results = [random.randint(1,dice.sides) for i in range(dice.number)]
        dice_text = "dice" if dice.number == 1 else "die"
        embed = discord.Embed(title=f"Rolling {dice.number} {dice_text} with {dice.sides} sides", colour=ctx.guild.me.colour)
        sum_results = sum(results)
        if dice.modifier:
            embed.title += f" with a modifier of {dice.sign}{dice.modifier}"
            sum_results = sum_results + dice.modifier if dice.sign == "+" else sum_results - dice.modifier
        embed.add_field(name="Result", value=f"{sum_results:,}", inline=False)
        embed.add_field(name="Rolls", value=textwrap.shorten(" ".join(f"[{r}]" for r in results), 1024), inline=False)
        await ctx.send(embed=embed)



def setup(bot):
    bot.add_cog(Roll(bot))
