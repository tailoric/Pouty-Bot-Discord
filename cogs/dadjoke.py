import re
class Dadjoke:
    def __init__(self, bot):
        self.bot = bot
        self.result = None
        self.user = None

    def check_for_dadjoke(self, message):
        return message.content.lower().startswith("hi") and self.result.group(2) in message.content and message.author.id != self.user.id

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
            new_name = msg.content[2:30]
            if len(msg.content) > 32:
                new_name += "..."
            await self.bot.change_nickname(msg.author, new_name)



def setup(bot):
    bot.add_cog(Dadjoke(bot))
