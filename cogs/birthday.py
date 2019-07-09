import discord
from discord.utils import get, find
from discord.ext import commands,tasks
from .utils.dataIO import DataIO
import time

class Birthday(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_io = DataIO()
        self.bday_entries = self.data_io.load_json("birthday", as_list=True)
        self.remove_birthday.start()

    def cog_unload(self):
        self.remove_birthday.stop()

    @commands.has_permissions(manage_roles=True)
    @commands.command(aliases=['bday'])
    async def birthday(self, ctx: commands.Context, member: discord.Member):
        """assigns the birthday role to the user and removes it after 24 hours"""
        bday_role = find(lambda r: "birthday" in r.name.lower(), ctx.guild.roles)
        if bday_role in member.roles:
            await ctx.send("user already has birthday role")
            return
        elif bday_role:
            await member.add_roles(bday_role)
            entry = {
                "member": member.id,
                "ts": int(time.time()) + 86400,
                "role": bday_role.id,
                "guild": ctx.guild.id
            }
            self.bday_entries.append(entry)
            self.data_io.save_json("birthday", self.bday_entries)
            await ctx.send("birthday role assigned successfully")
        else:
            await ctx.send("no role with 'Birthday' in the name")


    @tasks.loop(seconds=5)
    async def remove_birthday(self):
        to_remove = []
        for entry in self.bday_entries:
            if entry["ts"] <= int(time.time()):
                try:
                    guild = get(self.bot.guilds, id=entry["guild"])
                    bday_role = get(guild.roles, id=entry["role"])
                    member = get(guild.members, id=entry["member"])
                    if member and guild and bday_role:
                        await member.remove_roles(bday_role)
                except (discord.errors.Forbidden, discord.errors.NotFound):
                    to_remove.append(entry)
                except discord.errors.HTTPException:
                    pass
                else:
                    to_remove.append(entry)
        for removal in to_remove:
            self.bday_entries.remove(removal)
        if to_remove:
            self.data_io.save_json("birthday", self.bday_entries)


def setup(bot: commands.Bot):
    bot.add_cog(Birthday(bot))
