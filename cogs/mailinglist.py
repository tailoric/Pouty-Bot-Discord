from discord.ext import commands
import discord
import aiohttp
import json
import os
import datetime
from dateutil import parser
import asyncio
import re
import traceback
from .utils import checks
import logging

"""
Schema of Subs
[
	"subs": {
		"listName": [1112, 32],
		"listName2": [123, 453]
	},
	"users": {
		someUserId: ["listName", listName2"]
	}
]
"""

class Danbooru:
    """
    Danbooru requests and subscription service.
    """
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
		
		# Make sure directory to store json is good, and then read a file if it exists
        self.init_directories()
		self.jsonDir = 'data/mailinglist/data.json'
		with open(self.jsonDir, 'r') as f:
			self.json = json.load(f)

    def __unload(self):
		return

    def init_directories(self):
        if not os.path.exists('data/mailinglist'):
            os.mkdir('data/mailinglist')
        if not os.path.exists('data/mailinglist/subs/'):
            os.mkdir('data/mailinglist/subs')
		if not os.file.exists('data/mailinglist/subs/data.json/'):
		    newJson = open('data.json','w')
			newJson.write('[]');
			file.close()
			
	def writeUpdatedList(self):
		try:
			with open(self.jsonDir, 'w') as f:
				json.dump(self.json, f)
		except Exception as e:
		   await self.bot.say('Error while persisting sub change: `{}`'.format(repr(e)))
		   raise e

    @mlist.command(pass_context=True)
    async def sub(self, ctx, list):
        """
        subscribe to provided list
        list: list that will be subscribed to 
        """
		message = ctx.message
		requesterID = message.author.id
		
		# Make sure list exists
		# If it does add the user only if they are not already in the list
		if list in subs:
			for userID in self.json["subs"][list]:
				if userID == requesterID:
					await self.bot.say('You are already in %(list).' % list)
					return
			
			# Here is where we actually add the user to the list
			self.json["subs"][list].append(requesterID)
			self.json["users"][requesterID].append(list)
			writeUpdatedList()
			await self.bot.say('You have been added to %(list).' % list)
			return
		else:
			await self.bot.say('List %(list) doesn\'t exist. Create it with `mlist create`.' % list)
			return

			

    @mlist.command(pass_context=True)
    async def unsub(self, ctx, list):
        """
        unsubscribe from given list
        list: list that will be unsubscribed from
        """
		message = ctx.message
		requesterID = message.author.id
		
		# Make sure list exists
		# If it does add the user only if they are not already in the list
		if list in subs:
			for index, userID in enumerate(self.json["subs"][list]):
				if userID == requesterID:
					self.json["users"][requesterID].remove(list)
					self.json["subs"][list].remove(requesterID)
					writeUpdatedList()
					await self.bot.say('You have been removed from %(list).' % list)
					return
			
			await self.bot.say('You are not in list %(list).' % list)
			return
		else:
			await self.bot.say('List %(list) doesn\'t exist. Create it with `mlist create`.' % list)
			return
	
	
    @mlist.command(pass_context=True)
    async def broadcast(self, ctx, list, message):
        """
        Send a message to the given list
        list: list that will be broadcasted to
		message: message that will be sent
        """
		message = ctx.message
		requesterID = message.author.id
		
		# Make sure list exists
		# If it does add the user only if they are not already in the list
		if list in subs:
			for userID in self.json["subs"][list]:
				await self.bot.say('<@{}> says {} on list {}.\n{}'.format(requesterID, message, list, pingList(self.json["subs"][list])))
			return
		else:
			await self.bot.say('List %(list) doesn\'t exist. Create it with `mlist create`.' % list)
			return

	# Generate a string with pings for all the userIDs in the list
	def pingList(self, list):
		"""
        Generate a string with pings for all the userIDs in the list
        list: list of usersIDs
		"""
		return ' '.join(list(map(lambda userID: '<@{}>'.format(userID))))

    @mlist.command(pass_context=True)
    async def list(self, ctx):
        """
        list all subscribed lists
        """
        message = ctx.message
		listRequester = message.author.id
		
		subList = ', '.join([str(x) for x in self.json["users"][listRequester]])
		if (subList.length() == 0):
			await self.bot.say(subList);
        else:
            await self.bot.reply('You aren\'t subscribed to any lists')
			
	@mlist.command(pass_context=True)
    @checks.is_owner()
    async def listAll(self, ctx):
        """
        list all subs
        """
        message = ctx.message
		listRequester = message.author.id
		
		subList = ', '.join([str(x) for key in self.json["subs"])
		
		if (subList.length() == 0):
			await self.bot.say(subList);
        else:
            await self.bot.reply('There are no lists')

    @mlist.command()
    async def restart(self):
        """
        ONLY USE WHEN STUCK!
        """
        self.__unload()
        setup(self.bot)

def setup(bot):
    bot.add_cog(Danbooru(bot))
