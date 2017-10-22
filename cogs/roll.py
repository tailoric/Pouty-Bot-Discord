from discord.ext import commands
import random


class Roll:
    """
    Roll dice command
    """

    def __init__(self, bot):
        self.bot = bot
        self.char_limit = 2000

    @commands.command()
    async def roll(self, roll:str):
        """
        roll one or multiple die
        example: .roll 1d6 for a 6-sided die
        """
        if 'd' not in roll:
            await self.bot.say('not correct format\nexample: `.roll 1d6` to roll one 6-sided die.')
        else:
            number, sides = roll.split('d')
            modifier = 0
            is_plus = False
            if '+' in sides:
                sides, modifier = sides.split('+')
                modifier = int(modifier)
                is_plus = True
            elif '-' in sides:
                sides, modifier = sides.split('-')
                modifier = -1 * int(modifier)
            try:
                sides = int(sides)
                if number:
                    number = int(number)
                else:
                    number = 1
            except ValueError as ve:
                await self.bot.say('not correct format\nexample: `.roll 1d6` to roll one 6-sided die.''')
                return

            results = []
            sum = 0
            for i in range(number):
                throw_result = random.randint(1, sides)
                sum += throw_result
                results.append(str(throw_result))

        answer_text = 'you have rolled the following results:\n\n' + ', '.join(results)
        if is_plus:
            answer_text += '\nSum: '+str(sum + modifier) + ' ({}+{})'.format(sum, modifier)
        else:
            if modifier == 0:
                answer_text += '\nSum: '+str(sum + modifier)
            else:
                answer_text += '\nSum: '+str(sum + modifier) + ' ({}{})'.format(sum, modifier)
        if len(answer_text) > self.char_limit:
            last_pos = answer_text[:2000].rfind(',')
            await self.bot.say(answer_text[0:last_pos])
            await self.bot.say('character limit reached, stopping dice throws to reduce spam')
        else:
            await self.bot.say(answer_text)


def setup(bot):
    bot.add_cog(Roll(bot))
