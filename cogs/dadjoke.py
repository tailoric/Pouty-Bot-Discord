import re
import time
from discord.ext import commands
class Dadjoke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.result = None
        self.user = None

    def check_for_dadjoke(self, message):
        return re.match("^([Hh]i|[hH]ello|[Hh]ey|[Yy]o|[Hh]iya|[Ww]hat'?s up)\s+.*", message.content) and self.result.group(2) in message.content and message.author.id != self.user.id

    async def on_message(self, message):
        if message.content is None:
            return
        result = re.match(".*([Ii]\s?'?a?m)\s*(.*)", message.content)
        if result:
            self.result = result
            self.user = message.author
            msg = await self.bot.wait_for_message(check=self.check_for_dadjoke, timeout=60)
            if msg == None:
                return
            new_name = "  ".join(msg.content.split()[1:])
            if len(msg.content) > 32:
                new_name = new_name[:28] + "..."
            await self._mute_user(msg.author)
            await self.bot.change_nickname(msg.author, new_name)

    async def _mute_user(self, user):
        admin_cog = self.bot.get_cog("Admin")
        if(admin_cog):
            await self.bot.add_roles(user,admin_cog.mute_role)
            admin_cog.mutes.append({"user": user.id, "unmute_ts": int(time.time() + 60)})

def setup(bot):
    bot.add_cog(Dadjoke(bot))
