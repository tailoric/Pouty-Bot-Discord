from discord.ext import commands
from discord import app_commands
from typing import Optional, NamedTuple
import discord
import json

class JumpView(discord.ui.View):
    def __init__(self, message: discord.Message, timeout=None):
        super().__init__(timeout=timeout)
        self.add_item(discord.ui.Button(label="Source Message", url=message.jump_url))
class Language(NamedTuple):
    iso : str
    full_name: str
class LangTransformError(app_commands.AppCommandError):
    pass

class LanguageTransformer(app_commands.Transformer):
    
    languages = {
        }
    async def transform(self, interaction, value):
        lang = self.languages[value]
        return Language(iso=value, full_name=lang)

    async def autocomplete(self, interaction: discord.Interaction, value: str):
        choices = []
        if value:
            for iso, lang in self.languages.items():
                if value.lower() in lang.lower():
                    choices.append(app_commands.Choice(name=lang, value=iso))
            return choices[:25]
        return [app_commands.Choice(name=l[1], value=l[0]) for l in list(self.languages.items())[:25]]

class InputTransformer(LanguageTransformer):

    languages = {
    "BG" : "Bulgarian",
    "CS" : "Czech",
    "DA" : "Danish",
    "DE" : "German",
    "EL" : "Greek",
    "EN" : "English",
    "ES" : "Spanish",
    "ET" : "Estonian",
    "FI" : "Finnish",
    "FR" : "French",
    "HU" : "Hungarian",
    "ID" : "Indonesian",
    "IT" : "Italian",
    "JA" : "Japanese",
    "KO" : "Korean",
    "LT" : "Lithuanian",
    "LV" : "Latvian",
    "NB" : "Norwegian (Bokmål)",
    "NL" : "Dutch",
    "PL" : "Polish",
    "PT" : "Portuguese ",
    "RO" : "Romanian",
    "RU" : "Russian",
    "SK" : "Slovak",
    "SL" : "Slovenian",
    "SV" : "Swedish",
    "TR" : "Turkish",
    "UK" : "Ukrainian",
    "ZH" : "Chinese",
    }

class OutputTransformer(LanguageTransformer):
    languages = {
    "BG" : "Bulgarian",
    "CS" : "Czech",
    "DA" : "Danish",
    "DE" : "German",
    "EL" : "Greek",
    "EN" : "English",
    "EN-GB" : "English (British)",
    "EN-US" : "English (American)",
    "ES" : "Spanish",
    "ET" : "Estonian",
    "FI" : "Finnish",
    "FR" : "French",
    "HU" : "Hungarian",
    "ID" : "Indonesian",
    "IT" : "Italian",
    "JA" : "Japanese",
    "KO" : "Korean",
    "LT" : "Lithuanian",
    "LV" : "Latvian",
    "NB" : "Norwegian (Bokmål)",
    "NL" : "Dutch",
    "PL" : "Polish",
    "PT" : "Portuguese",
    "PT-BR": "Portuguese(Brazilian)",
    "PT-PT": "Portuguese",
    "RO" : "Romanian",
    "RU" : "Russian",
    "SK" : "Slovak",
    "SL" : "Slovenian",
    "SV" : "Swedish",
    "TR" : "Turkish",
    "UK" : "Ukrainian",
    "ZH" : "Chinese (simplified)",
    }

class Deepl(commands.Cog):
    """The description for Deepl goes here."""

    def __init__(self, bot):
        self.bot = bot
        with open("config/deepl.json") as f:
            config = json.load(f)
            self.api_key = config.get("api_key")

        self.ctx_menu = app_commands.ContextMenu(
                name="Translate Message",
                callback=self.translate_message
                )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    @app_commands.command(name="translate")
    @app_commands.rename(output_lang="to", input_lang="from")
    @app_commands.checks.cooldown(1, 60)
    async def deepl_translate(self,
            interaction: discord.Interaction,
            text: app_commands.Range[str, 10, 300],
            output_lang: app_commands.Transform[Language, OutputTransformer],
            input_lang: Optional[app_commands.Transform[Language, InputTransformer]]
            ):
        """
        Translate some text via DeepL

        Parameters
        -----------
        text: str
            the text to translate
        output_lang: str
            the language to translate to
        input_lang: Optional[str]
            optionally the input language, DeepL will guess when this is omitted
        """
        await interaction.response.defer()
        params = {
                "text": text,
                "target_lang": output_lang.iso,
            }
        headers = {
                "Authorization": f"DeepL-Auth-Key {self.api_key}"
                }
        if input_lang:
            params["source_lang"] = input_lang.iso
        async with self.bot.session.post("https://api-free.deepl.com/v2/translate", params=params, headers=headers, raise_for_status=True) as resp:
            data = await resp.json()
            translation = data.get("translations")
            if not translation:
                return await interaction.followup.send("No translation found.")
            translation = translation[0]
            if not input_lang:
                iso = translation.get("detected_source_language")
                input_lang = Language(full_name=InputTransformer.languages[iso], iso=iso)
            response_message = (
                    f'**{input_lang.full_name}**: \n\t{text}\n'
                    f'**{output_lang.full_name}**: \n\t{translation.get("text")}'
                )
            await interaction.followup.send(response_message)

    @app_commands.checks.cooldown(1, 180)
    async def translate_message(self, interaction: discord.Interaction, message: discord.Message) -> None:
        await interaction.response.defer()
        if message.embeds:
            source_text = message.embeds[0].description
        else:
            source_text = discord.utils.remove_markdown(message.content)
            source_text = source_text[:295] + '[...]' if len(source_text) >= 300 else source_text
        params = {
                "text": source_text,
                "target_lang": "EN"
            }
        headers = {
                "Authorization": f"DeepL-Auth-Key {self.api_key}"
                }
        async with self.bot.session.post("https://api-free.deepl.com/v2/translate", params=params, headers=headers, raise_for_status=True) as resp:
            data = await resp.json()
            translation = data.get("translations")
            if not translation:
                return await interaction.followup.send("No translation found.")
            translation = translation[0]
            if interaction.guild and interaction.guild.me.colour.value:
                colour = interaction.guild.me.colour
            else:
                colour = discord.Colour.blurple()
            detected_lang = translation.get('detected_source_language')
            language_name = InputTransformer.languages.get(detected_lang, detected_lang)
            embed = discord.Embed(title=f"Detected Language: {detected_lang}",
                    description=translation.get("text"), colour=colour)
            view = JumpView(message)
            await interaction.followup.send(embed=embed,
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none())

async def setup(bot):
    await bot.add_cog(Deepl(bot))
