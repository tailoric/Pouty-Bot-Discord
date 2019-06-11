from discord.ext import commands
import discord
import regex


import httplib2
import os

from googleapiclient.discovery import build
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow


class Youtube(commands.Cog):
    """Youtube commands"""
    def __init__(self, bot):
        self.bot = bot
        self.status = False
        self.user = None
        self.playlist = "PLz31nXegXIhJDnXGEJlaBgRPEfmEoav6O"
        self.CLIENT_SECRETS_FILE = "data/youtube/client_id.json"
        self.YOUTUBE_READ_WRITE_SCOPE = "https://www.googleapis.com/auth/youtube"
        self.YOUTUBE_API_SERVICE_NAME = "youtube"
        self.YOUTUBE_API_VERSION = "v3"
        self.MISSING_CLIENT_SECRETS_MESSAGE = """
        WARNING: Please configure OAuth 2.0
        To make this sample run you will need to populate the client_secrets.json file
        found at:
           %s
        with information from the {{ Cloud Console }}
        {{ https://cloud.google.com/console }}
        For more information about the client_secrets.json file format, please visit:
        https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
        """ % os.path.abspath(os.path.join(os.path.dirname(__file__),
                                           self.CLIENT_SECRETS_FILE))

    @commands.command(pass_context=True)
    async def start(self, ctx):
        """starts collecting your Youtube links"""
        self.status = True
        await self.bot.change_presence(activity=discord.Game(name="Start"))
        self.user = ctx.message.author
        await ctx.send("Collecting Links")

    @commands.command()
    async def stop(self, ctx):
        """Stops collecting your Youtube links"""
        self.status = False
        await self.bot.change_presence(activity=discord.Game(name="Stop"))
        self.user = None
        await ctx.send("Ignoring Links")

    @commands.command(name="status")
    async def give_status(self, ctx):
        """Gives the current status and user whose links the bot listens to"""
        if self.status:
            await ctx.send("**Current Status:** Start\n" +
                               "**Current User:** {}".format(self.user.mention))

        else:
            await ctx.send("**Current Status:** Stop")



    @commands.command(name="playlist")
    async def post_playlist(self, ctx):
        """links the Radio Touhou Night Playlist"""
        await ctx.send("https://www.youtube.com/playlist?list={}".format(self.playlist))

    @commands.Cog.listener()
    async def on_message(self, message):
        if self.status and message.author == self.user and self.check_if_link(message.content):
            await self.insert_videos_into_playlist(message.content)
        else:
            return

    @staticmethod    
    def check_if_link(content):
        return 'https://www.youtube' in content or 'https://youtu.be' in content


    async def insert_videos_into_playlist(self, link):
        # regex to get the id from a youtube link
        p = regex.compile('(?<=\d\/|\.be\/|v[=\/])([\w\-]{11,})|^([\w\-]{11})$')
        video_ids = regex.findall(p, link)
        flow = flow_from_clientsecrets(self.CLIENT_SECRETS_FILE,
                                       message=self.MISSING_CLIENT_SECRETS_MESSAGE,
                                       scope=self.YOUTUBE_READ_WRITE_SCOPE)
        storage = Storage("data/youtube/pouty_bot-oauth2.json")
        credentials = storage.get()
        if credentials is None or credentials.invalid:
            flags = argparser.parse_args()
            credentials = run_flow(flow, storage, flags)
        youtube = build(self.YOUTUBE_API_SERVICE_NAME, self.YOUTUBE_API_VERSION,
                        http=credentials.authorize(httplib2.Http()))

        for video in video_ids:

            youtube.playlistItems().insert(
                part="snippet,status",
                body=dict(
                    snippet=dict(
                        playlistId=self.playlist,
                        resourceId=dict(
                            kind="youtube#video",
                            videoId=video
                        )
                    ),
                    status=dict(
                        privacyStatus="private"
                    )
                )
            ).execute()
        result = youtube.playlistItems().list(
                    part="id",
                    playlistId=self.playlist
                ).execute()
        channel = self.bot.get_channel(id=248987073124630528)
        message = 'List contains {} songs'.format(result['pageInfo']['totalResults'])
        await channel.send(message)


def setup(bot):
    bot.add_cog(Youtube(bot))
