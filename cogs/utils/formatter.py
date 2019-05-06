from discord.ext.commands import DefaultHelpCommand

class CustomHelpCommand(DefaultHelpCommand):

    async def send_bot_help(self, mapping):
        prefix = self.context.prefix
        self.paginator.add_line(self.context.bot.description)
        self.paginator.add_line(empty=True)
        self.paginator.add_line("Command categories:")
        for cog in mapping:
            filtered = await self.filter_commands(mapping.get(cog))
            if cog is None or len(filtered) == 0:
                continue
            if cog.qualified_name:
                self.paginator.add_line("\t* {0}".format(cog.qualified_name))
            if cog.description:
                self.paginator.add_line("\t\t\"{0}\"".format(cog.description))
        self.paginator.add_line("To see more information about the commands of a category use .help <CategoryName>")
        self.paginator.add_line("ATTENTION: The categories are case sensitive")
        await self.send_pages()

