import asyncio
import logging
import datetime
import discord
import time
from discord.ext import commands, tasks
from .utils.checks import is_owner_or_moderator_check
import youtube_dl
import os
from functools import partial


class SongEntry:
    def __init__(self, message, filename, info):
        self.requester = message.author
        self.channel = message.channel
        self.filename = filename
        self.info = info
        self.link = info.get("webpage_url", None)
        self.duration = info.get("duration", None)
        self.rewinds = []
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
    """Commands to summon the bot into voice and let it play music"""
    def __init__(self, bot):
        self.bot = bot
        self.opts = {
            'default_search': 'auto',
            'quiet': True,
            'extractaudio': True,
            'format': 'bestaudio',
            'buffer-size': 16000,
            'outtmpl': "data/ytdl/%(title)s-%(id)s.%(ext)s",
            'cachedir': False
        }
        self.ytdl = youtube_dl.YoutubeDL(self.opts)
        self.downloads = list()
        self.voice_client = None
        self.enqueued_songs = list()
        self.current = None
        self.skip_votes = set()
        self.play_next_event = asyncio.Event()
        self.next_song_listener.start()
        self.start_time = time.time()
        self.logger = logging.getLogger("PoutyBot")

    def cog_unload(self):
        self.next_song_listener.cancel()
        if self.voice_client:
            self.voice_client.stop()
            self.bot.loop.create_task(self.voice_client.disconnect())
        for song in self.enqueued_songs:
            song.audio_source.cleanup()
            os.remove(song.filename)

    async def connect_to_voice(self, ctx):
        summoned_voice = ctx.message.author.voice
        if summoned_voice is None:
            await ctx.send("join a voice channel, or go into the voice channel I am currently in")
            return
        if not self.bot.voice_clients:
            self.voice_client = await ctx.message.author.voice.channel.connect()
            self.ytdl = youtube_dl.YoutubeDL(self.opts)
            return self.voice_client
        elif summoned_voice.channel not in [x.channel for x in self.bot.voice_clients]:
            await ctx.send("join a voice channel, or go into the voice channel I am currently in")
            return
        else:
            return self.voice_client

    @commands.command()
    async def play(self, ctx, *, song):
        """
        play music from youtube or other websites through the bot, automatically joins the voice channel you are
        currently in.
        works either with a direct link to the song or search phrases
        """
        summoned_voice = await self.connect_to_voice(ctx)
        if not self.voice_client or summoned_voice is None:
            return
        try:
            downloading_message = await ctx.send("Downloading...")
            to_run = partial(self.ytdl.extract_info, url=song, download=False)
            info = await self.bot.loop.run_in_executor(None, to_run)
            info = info.get("entries")[0] if "entries" in info.keys() else info
            if info.get("duration", 0) > 7200:
                await ctx.send("song too long")
                return
            if info.get("is_live", False):
                await ctx.send("live streams can't be queued")
                return
            filename = self.ytdl.prepare_filename(info)
            run_download = partial(self.ytdl.download, [info.get("webpage_url")])
            await self.bot.loop.run_in_executor(None, run_download)
        except youtube_dl.DownloadError as de:
            logger = logging.getLogger("PoutyBot")
            logger.error(de)
            await ctx.send("Download error, could not download the song")
            return
        entry = SongEntry(ctx.message, filename, info)
        if not self.voice_client.is_playing():
            self.current = entry
            await downloading_message.edit(content="Now Playing: " + str(entry))
            self.voice_client.play(entry.audio_source, after=self.toggle_next)
            await self.update_presence()
            self.current.start_time = int(time.time())
        else:
            await downloading_message.edit(content="Enqueued: " + str(entry))
            self.enqueued_songs.append(entry)

    async def disconnect_when_not_playing(self):
        """
        disconnects the bot when not playing music for 2 minutes
        """
        await self.bot.change_presence(activity=None)
        await asyncio.sleep(120)
        if len(self.enqueued_songs) == 0 and not self.voice_client.is_playing():
            await self.voice_client.disconnect()

    def toggle_next(self, error):
        """
        function that always triggers after playback of current song stopped
        """
        try:
            self.skip_votes.clear()
            self.current.audio_source.cleanup()
            os.remove(self.current.filename)
        except Exception:
            self.logger.error("could not remove file: " + self.current.filename)
        if len(self.enqueued_songs) > 0:
            self.bot.loop.call_soon_threadsafe(self.play_next_event.set)
        else:
            self.bot.loop.create_task(self.disconnect_when_not_playing())

    async def update_presence(self):
        """updates the status message of the bot to the current song"""
        activity = discord.Game(
            name=self.current.title
        )
        await self.bot.change_presence(activity=activity)

    @tasks.loop(seconds=0.0)
    async def next_song_listener(self):
        """
        event listener that activates whenever toggle_next fires the even to play the next song
        """
        await self.play_next_event.wait()
        self.current = self.enqueued_songs.pop(0)
        self.current.start_time = int(time.time())
        await self.current.channel.send("Now playing: " + str(self.current))
        self.voice_client.play(self.current.audio_source, after=self.toggle_next)
        await self.update_presence()
        self.play_next_event.clear()

    @commands.command()
    async def stop(self, ctx):
        """
        disconnects the bot from voice channel and deletes the current playlist
        only allowed when only one or no members remaining
        """
        if not ctx.message.author.voice:
            await ctx.send("Not in my voice channel")
            return
        user_voice = ctx.message.author.voice.channel
        my_voice = ctx.guild.me.voice.channel
        if not is_owner_or_moderator_check(ctx.message) and not len(self.voice_client.channel.members) <= 2:
            if user_voice != my_voice and not is_owner_or_moderator_check(ctx.message):
                await ctx.send("You are not in my voice channel, not allowed")
                return
            await ctx.send("only allowed when no or only one member remaining in voice")
            return
        if self.voice_client:
            self.enqueued_songs.clear()
            try:
                for song in self.enqueued_songs:
                    song.audio_source.cleanup()
                    os.remove(song.filename)
            except PermissionError as e:
                self.logger.error(e)
            self.voice_client.stop()
            await self.bot.change_presence(activity=None)
            await self.voice_client.disconnect()

    @commands.command()
    async def skip(self, ctx):
        """
        skips the current song after enough people voted to skip on it (more than 50%)
        or if the person requesting the song wants to skip it.
        """
        if not ctx.message.author.voice:
            await ctx.send("Not in my voice channel")
            return
        user_voice = ctx.message.author.voice.channel
        my_voice = ctx.guild.me.voice.channel
        if self.voice_client.is_playing():
            if user_voice != my_voice:
                await ctx.send("You are not in my voice channel, not allowed")
                return
            if ctx.message.author == self.current.requester:
                await ctx.send("requester skipped")
                self.voice_client.stop()
                await self.bot.change_presence(activity=None)
            else:
                self.skip_votes.add(ctx.message.author)
                needed_votes = (len(self.voice_client.channel.members) - 1)//2
                if len(self.skip_votes) > needed_votes:
                    await ctx.send("skip vote passed ")
                    self.voice_client.stop()
                    await self.bot.change_presence(activity=None)
                else:
                    await ctx.send("voted to skip [{0}/{1}]".format(len(self.skip_votes), len(self.voice_client.channel.members) -1))

    @commands.command(aliases=["ff"])
    async def fast_forward(self, ctx, seconds=0):
        """
        fast forwards the current song by x seconds only allowed by the requester
        example: .ff 50 (to fast forward the song by 50 seconds)
        """
        if self.current.requester != ctx.message.author or not is_owner_or_moderator_check(message=ctx.message):
            await ctx.send("only requester or moderator is allowed to fast forward")
            return
        filename = self.current.filename
        playtime = int(time.time() - self.current.start_time)
        if playtime+seconds >= self.current.duration:
            self.voice_client.stop()
            return
        before_options = "-ss "+ str(playtime+seconds)
        old_source = self.voice_client.source
        new_source = discord.FFmpegPCMAudio(source=filename, before_options=before_options)
        self.voice_client.source = new_source
        self.current.start_time -= seconds
        old_source.cleanup()

    @commands.command(aliases=["rw"])
    async def rewind(self, ctx, seconds=0):
        """
        rewinds the current song by x seconds only allowed by the requester
        example: .rw 50 (to rewind the song by 50 seconds)
        """
        if self.current.requester != ctx.message.author or not is_owner_or_moderator_check(message=ctx.message):
            await ctx.send("only requester or moderator is allowed to rewind")
            return
        if len(self.current.rewinds) + 1 > 3 or sum(self.current.rewinds) + seconds > 600:
            await ctx.send("too many rewinds")
            return
        filename = self.current.filename
        playtime = int(time.time() - self.current.start_time)
        if seconds < playtime:
            before_options = "-ss "+ str(playtime - seconds)
            self.current.start_time += seconds
            self.current.rewinds.append(seconds)
        else:
            before_options = "-ss 0"
            self.current.start_time = int(time.time())
            self.current.rewinds.append(playtime)
        old_source = self.voice_client.source
        new_source = discord.FFmpegPCMAudio(source=filename, before_options=before_options)
        self.voice_client.source = new_source
        old_source.cleanup()


    @commands.command()
    async def playing(self, ctx):
        """
        lists the currently playing and enqueued songs
        """
        playlist_message = "Currently Playing: {0} {1}\n<{2}>\n".format(self.current, self.current.playtime, self.current.link)

        for index, song in enumerate(self.enqueued_songs):
            if index == 0:
                playlist_message += "Upcoming songs:\n"
            if len(playlist_message) + len(str(song)) > 2000:
                playlist_message += "and {0} more".format(len(self.enqueued_songs) - (index+1))
                break
            playlist_message += str(song) + "\n"
        await ctx.send(playlist_message)



def setup(bot):
    bot.add_cog(Music(bot))
