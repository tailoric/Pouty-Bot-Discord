import asyncio
import logging
import discord
import time
from discord.ext import commands
from .utils.checks import is_owner_or_moderator_check
import youtube_dl
import os


class SongEntry:
    def __init__(self, message, filename, info):
        self.requester = message.author
        self.channel = message.channel
        self.filename = filename
        self.duration = info.get("duration", None)
        if self.duration:
            self.duration = int(self.duration)
        self.audio_source = discord.FFmpegPCMAudio(source=filename)
        self.title = info.get("title", None)
        self.start_time = int(time.time())

    @property
    def playtime(self):
        current_time = int(time.time())
        playtime_str = "`[{0[0]:02d}m {0[1]:02d}s".format(divmod(current_time - self.start_time, 60))
        if self.duration:
            playtime_str += "/{0[0]:02d}m {0[1]:02d}s]`".format(divmod(self.duration, 60))
        else:
            playtime_str += "]`"
        return playtime_str

    def __str__(self):
        fmt = "**{0}** requested by **{1}** "
        if self.duration:
            fmt += "[length: {0[0]:02d}m {0[1]:02d}s]".format(divmod(self.duration, 60))

        return fmt.format(self.title, self.requester.display_name)


class Music(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        opts = {
            'default_search': 'auto',
            'quiet': True,
            'extractaudio': True,
            'format': 'bestaudio',
            'progress_hooks': [self.download_hook],
            'buffer-size': 16000,
            'outtmpl': "data/ytdl/%(id)s.%(ext)s"
        }
        self.ytdl = youtube_dl.YoutubeDL(opts)
        self.downloads = list()
        self.voice_client = None
        self.enqueued_songs = list()
        self.current = None
        self.skip_votes = set()
        self.play_next_event = asyncio.Event()
        self.play_next_event_listener = self.bot.loop.create_task(self.next_song_listener())
        self.start_time = time.time()
        self.logger = logging.getLogger("PoutyBot")

    def download_hook(self, download):
        if download['status'] == 'finished':
            download['filename'] = download['filename'].replace('\\', '/')
            self.downloads.append(download['filename'])

    def __unload(self):
        self.play_next_event_listener.cancel()

    async def connect_to_voice(self, ctx):
        summoned_voice = ctx.message.author.voice
        if summoned_voice is None:
            await ctx.send("join a voice channel, or go into the voice channel I am currently in")
            return
        if not self.bot.voice_clients:
            self.voice_client = await ctx.message.author.voice.channel.connect()
        elif summoned_voice.channel not in [x.channel for x in self.bot.voice_clients]:
            await ctx.send("join a voice channel, or go into the voice channel I am currently in")
            return

    @commands.command()
    async def play(self, ctx, *, song):
        """
        play music from youtube or other websites through the bot, automatically joins the voice channel you are
        currently in.
        works either with a direct link to the song or search phrases
        """
        await self.connect_to_voice(ctx)
        if not self.voice_client:
            return
        try:
            downloading_message = await ctx.send("Downloading...")
            info = self.ytdl.extract_info(song, download=False)
            info = info.get("entries")[0] if "entries" in info.keys() else info
            if info.get("is_live", False):
                await ctx.send("live streams can't be queued")
                return
            self.ytdl.download([song])
        except youtube_dl.DownloadError as de:
            logger = logging.getLogger("PoutyBot")
            logger.error(de)
            await ctx.send("Download error, could not download the song")
            return
        entry = SongEntry(ctx.message, self.downloads.pop(), info)
        if not self.voice_client.is_playing():
            self.current = entry
            await downloading_message.edit(content="Now Playing: " + str(entry))
            self.voice_client.play(entry.audio_source, after=self.toggle_next)
            await self.bot.change_presence(activity=discord.Game(self.current.title))
            self.current.start_time = int(time.time())
        else:
            await downloading_message.edit(content="Enqueued: " + str(entry))
            self.enqueued_songs.append(entry)

    async def disconnect_when_not_playing(self):
        """
        disconnects the bot when not playing music for 2 minutes
        """
        await asyncio.sleep(120)
        if len(self.enqueued_songs) == 0 and not self.voice_client.is_playing():
            await self.voice_client.disconnect()

    def toggle_next(self, error):
        """
        function that always triggers after playback of current song stopped
        """
        os.remove(self.current.filename)
        if len(self.enqueued_songs) > 0:
            self.bot.loop.call_soon_threadsafe(self.play_next_event.set)
        else:
            self.bot.loop.create_task(self.disconnect_when_not_playing())

    async def next_song_listener(self):
        """
        event listener that activates whenever toggle_next fires the even to play the next song
        """
        while True:
            await self.play_next_event.wait()
            self.current = self.enqueued_songs.pop()
            await self.current.channel.send("Now playing: " + str(self.current))
            self.voice_client.play(self.current.audio_source, after=self.toggle_next)
            await self.bot.change_presence(activity=discord.Game(self.current.title))
            self.play_next_event.clear()

    @commands.command()
    async def stop(self, ctx):
        """
        disconnects the bot from voice channel and deletes the current playlist
        only allowed when only one or no members remaining
        """
        if not is_owner_or_moderator_check(ctx.message) and not len(self.voice_client.channel.members) <= 2:
            await ctx.send("only allowed when no or only one member remaining in voice")
            return
        if self.voice_client:
            file_list = [x.filename for x in self.enqueued_songs]
            self.enqueued_songs.clear()
            try:
                for entry in file_list:
                    os.remove(entry.filename)
            except PermissionError as e:
                self.logger.error(e)
            self.voice_client.stop()
            await self.voice_client.disconnect()

    @commands.command()
    async def skip(self, ctx):
        """
        skips the current song after enough people voted to skip on it (more than 50%)
        or if the person requesting the song wants to skip it.
        """
        if self.voice_client.is_playing():
            if ctx.message.author == self.current.requester:
                self.voice_client.stop()
                await self.bot.change_presence(Game=None)
            else:
                self.skip_votes.add(ctx.message.author)
                needed_votes = (len(self.voice_client.channel.members) - 1)//2
                if len(self.skip_votes) > needed_votes:
                    await ctx.send("requester skipped")
                    self.voice_client.stop()
                    await self.bot.change_presence(Game=None)
                else:
                    await ctx.send("voted to skip [{0}/{1}]".format(len(self.skip_votes), len(self.voice_client.channel.members) -1))

    @commands.command()
    async def playing(self, ctx):
        """
        lists the currently playing and enqueued songs
        :param ctx:
        :return:
        """
        playlist_message = "Currently Playing: {0} {1}\n".format(self.current, self.current.playtime)

        for index, song in enumerate(self.enqueued_songs):
            if len(playlist_message) + len(str(song)) > 2000:
                playlist_message += "and {0} more".format(len(self.enqueued_songs) - (index+1))
                break
            playlist_message += str(song) + "\n"

        await ctx.send(playlist_message)



def setup(bot):
    bot.add_cog(Music(bot))
