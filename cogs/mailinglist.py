import aiohttp
import json
import os
from .utils import checks
from discord.ext import commands

"""
Schema of Subs
{
    "subs": {
        "listName": {
          "subbed": [1112, 32],
          "authorized": [1123]
        },
        "listName2": [123, 453]
    },
    "users": {
        someUserId: ["listName", listName2"]
    }
}
"""

class Mailinglist:
    """
    Danbooru requests and subscription service.
    """
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()

        # Make sure directory to store json is good, and then read a file if it exists
        self.init_directories()
        self.jsonDir = 'data/mailinglist/subs/data.json'
        with open(self.jsonDir, 'r') as f:
            self.json = json.load(f)

    def __unload(self):
        return

    def init_directories(self):
        if not os.path.exists('data/mailinglist'):
            os.mkdir('data/mailinglist')
        if not os.path.exists('data/mailinglist/subs/'):
            os.mkdir('data/mailinglist/subs')
        if not os.path.exists('data/mailinglist/subs/data.json'):
            with open('data/mailinglist/subs/data.json', 'w') as newJson:
                newJson.write('{"subs": {}, "users": {}}')

    async def writeUpdatedList(self):
        try:
            with open(self.jsonDir, 'w') as f:
                json.dump(self.json, f)
        except Exception as e:
           await self.bot.say('Error while persisting sub change: `{}`'.format(repr(e)))
           raise e

    @commands.group(pass_context = True)
    async def mlist(self, ctx):
        if ctx.invoked_subcommand is None:
            await self.bot.say("use `.help mlist`")

    @commands.group(pass_context = True)
    async def create(self, ctx, mail_list):
        """
        Create provided list
        mail_list: list that will be created
        """
        message = ctx.message
        requesterID = message.author.id

        # Make sure list exists
        # If it does add the user only if they are not already in the list
        if mail_list in self.json["subs"]:
            await self.bot.say('List %ds(mail_list) already exists.' % mail_list)
            return
        else:
            # Here is where we actually add the user to the list
            self.json["subs"][mail_list] = {"subbed": [], "authorized": [requesterID]}
            self.writeUpdatedList()
            await self.bot.say('%ds(mail_list) has been created. You are not subscribed to it by default, use `mlist '
                               'sub` to subscribe.' % mail_list)
            return
    
    @mlist.command(pass_context=True)
    async def sub(self, ctx, mail_list):
        """
        subscribe to provided list
        mail_list: list that will be subscribed to
        """
        message = ctx.message
        requesterID = message.author.id

        # Make sure list exists
        # If it does add the user only if they are not already in the list
        if mail_list in self.json["subs"]:
            for userID in self.json["subs"][mail_list]["subbed"]:
                if userID == requesterID:
                    await self.bot.say('You are already in %ds(mail_list).' % mail_list)
                    return

            # Here is where we actually add the user to the list
            self.json["subs"][mail_list]["subbed"].append(requesterID)
            self.json["users"][requesterID].append(mail_list)
            self.writeUpdatedList()
            await self.bot.say('You have been added to %ds(mail_list).' % mail_list)
            return
        else:
            await self.bot.say('List %ds(mail_list) doesn\'t exist. Create it with `mlist create`.' % mail_list)
            return

    @mlist.command(pass_context=True)
    async def unsub(self, ctx, mail_list):
        """
        unsubscribe from given list
        mail_list: list that will be unsubscribed from
        """
        message = ctx.message
        requesterID = message.author.id

        # Make sure list exists
        # If it does add the user only if they are not already in the list
        if mail_list in self.json["subs"]:
            for index, userID in enumerate(self.json["subs"][mail_list]["subbed"]):
                if userID == requesterID:
                    self.json["users"][requesterID].remove(mail_list)
                    self.json["subs"][mail_list]["subbed"].remove(requesterID)
                    self.writeUpdatedList()
                    await self.bot.say('You have been removed from %ds(mail_list).' % mail_list)
                    return

            await self.bot.say('You are not in list %ds(mail_list).' % mail_list)
            return
        else:
            await self.bot.say('List %ds(mail_list) doesn\'t exist. Create it with `mlist create`.' % mail_list)
            return
    
    @mlist.command(pass_context=True)
    async def authorize(self, ctx, mail_list):
        """
        Authorizes a user to broadcast to a list
        mail_list: list to add the user too
        userToAdd: user to authorize
        """
        message = ctx.message
        mentioned_user = ctx.message.mentions[0]
        requester_id = message.author.id
        if requester_id in self.json["subs"][mail_list]["authorized"]:
            self.json["subs"][mail_list]["authorized"].append(mentioned_user)
            self.writeUpdatedList()
            await self.bot.say('User has been added to the authorized group for %ds(mail_list).' % mail_list)
            return
        else:
            await self.bot.say('You are not authorized to add authorized users. Ask <@{}> to add you to the '
                               'authorized users.'.format(mail_list, self.json["subs"][mail_list]["authorized"][0]))
            return

    @mlist.command(pass_context=True)
    async def broadcast(self, ctx, mail_list, messageToSend):
        """
        Send a message to the given list
        mail_list: list that will be broadcasted to
        messageToSend: message that will be sent
        """
        message = ctx.message
        requester_id = message.author.id

        # Make sure list exists
        # If it does add the user only if they are not already in the list
        if mail_list in self.json["subs"]:
            if requester_id in self.json["subs"][mail_list]["authorized"]:
                await self.bot.say('<@{}> says {} on list {}.\n{}'.format(requester_id, messageToSend, mail_list, self.pingList(self.json["subs"][mail_list]["subbed"])))
                return
            else:
                await self.bot.say('You are not authorized to broadcast to {}. Ask <@{}> to add you to the authorized '
                                   'users.'.format(mail_list, self.json["subs"][mail_list]["authorized"][0]))
                return
        else:
            await self.bot.say('List %ds(mail_list) doesn\'t exist. Create it with `mlist create`.' % mail_list)
            return

    # Generate a string with pings for all the userIDs in the list
    def pingList(self, mail_list):
        """
        Generate a string with pings for all the userIDs in the list
        list: list of usersIDs
        """
        return ' '.join(mail_list(map(lambda userID: '<@{}>'.format(userID))))

    @mlist.command(pass_context=True)
    async def list(self, ctx):
        """
        list all subscribed lists
        """
        message = ctx.message
        list_requester = message.author.id

        subList = ', '.join([str(x) for x in self.json["users"][list_requester]])
        if len(subList) == 0:
            await self.bot.say(subList)
        else:
            await self.bot.reply('You aren\'t subscribed to any lists')

    @mlist.command()
    async def restart(self):
        """
        ONLY USE WHEN STUCK!
        """
        self.__unload()
        setup(self.bot)

    @mlist.command(pass_context=True)
    @checks.is_owner()
    async def listAll(self, ctx):
        """
        list all subs
        """
        message = ctx.message

        subList = ', '.join([str(x) for x in self.json["subs"]])

        if len(subList) == 0:
            await self.bot.say(subList)
        else:
            await self.bot.reply('There are no lists')


def setup(bot):
    bot.add_cog(Mailinglist(bot))
