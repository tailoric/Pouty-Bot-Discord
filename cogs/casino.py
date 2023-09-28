from discord.ext import commands
from discord import Embed, Member
import discord
from enum import Enum, auto
from .utils import checks
from typing import Optional
import copy
import random
import asyncio

class BetConversionError(commands.BadArgument):
    pass
class Bet(commands.Converter):

    async def convert(self, ctx: commands.Context, argument: str):
        if not argument.endswith("%"):
            try:
                return int(argument)
            except ValueError as ve:
                raise BetConversionError("argument was not an integer or percentage.")
        payday = ctx.bot.get_cog("Payday")
        amount = None
        if payday:
            row = await payday.fetch_money(ctx.author.id)
            amount = row.get('money')
        if not amount:
            raise BetConversionError("couldn't fetch money")
        try:
            percentage = int(argument.rstrip("%"))
            return int(amount * (percentage * 0.01))
        except ValueError:
            raise BetConversionError("argument was not an integer or percentage")



class CardColor(Enum):
    """
    simple enum for getting emoji
    """
    heart = "\N{WHITE HEART SUIT}"
    spade = "\N{WHITE SPADE SUIT}"
    diamond = "\N{WHITE DIAMOND SUIT}"
    club = "\N{WHITE CLUB SUIT}"


class GameState(Enum):
    """
    BlackJack Game states
    """
    RUNNING = auto()
    DEALER_PHASE = auto()
    GAME_OVER = auto()


class Card():
    """
    A card Object with card value (numerical)
    color (or suit) 
    and a face [eg number or A(ce), Q(ueen), J(ack), K(ing)]
    """
    def __init__(self, value, color, face):
        self.value = value
        self.color = color
        self.face = face

    def __str__(self):
        return f"{self.face}{self.color}"


def generate_deck():
    deck = []
    for color in list(CardColor):
        deck.append(Card(1, color.value, "A"))
        deck.append(Card(10, color.value, "J"))
        deck.append(Card(10, color.value, "Q"))
        deck.append(Card(10, color.value, "K"))
        for i in range(2, 11):
            deck.append(Card(i, color.value, str(i)))
    return deck

deck = generate_deck()

class BlackJackGame(discord.ui.View):
    """
    one game of blackjack
    """
    def __init__(self, player, bet, payday=None):
        super().__init__(timeout=None)
        self.payday = payday
        self.player = player
        self.message = None
        self.displaying_help = False
        self.state = GameState.RUNNING
        self.bet = bet
        self.deck = copy.copy(deck)
        self.folded = False
        random.shuffle(self.deck)
        self.dealer_hand = [self.deck.pop(0), self.deck.pop(0)]
        self.player_hand = [self.deck.pop(0), self.deck.pop(0)]
        if self.player_value == 21:
            self.state = GameState.GAME_OVER

    def __eq__(self, other):
        return self.player == other.player

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user is not None and self.player.id == interaction.user.id:
            return True
        else:
            await interaction.response.send_message("Not your game", ephemeral=True)
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def button_hit(self, interaction, button):
        await self.handle_hit(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.primary)
    async def button_stand(self, interaction, button):
        self.stand()
        await self.payout()

    @discord.ui.button(label="Double", style=discord.ButtonStyle.primary)
    async def button_double(self, interaction, button):
        await self.handle_double()

    @discord.ui.button(label="Fold", style=discord.ButtonStyle.danger)
    async def button_fold(self, interaction, button):
        await self.handle_fold(interaction)

    @property
    def player_value(self):
        total = sum(c.value for c in self.player_hand)
        if any(c.face == "A" for c in self.player_hand) and total <= 11:
            total += 10
        return total

    @property
    def dealer_value(self):
        dealer_stop = 1 if self.state == GameState.RUNNING else len(self.dealer_hand)
        total = sum(c.value for c in self.dealer_hand[:dealer_stop])
        if any(c.face == "A" for c in self.dealer_hand[:dealer_stop]) and total <= 11:
            total += 10
        return total

    
    def get_winner(self):

        if self.state in (GameState.DEALER_PHASE, GameState.RUNNING):
            return "running", False

        dealer_has_bj = len(self.dealer_hand) == 2 and self.dealer_value == 21
        player_has_bj = len(self.player_hand) == 2 and self.player_value == 21
        if self.player_value > 21:
            return "dealer", False
        elif self.dealer_value > 21 or self.player_value > self.dealer_value:
            return "player", player_has_bj
        elif self.player_value < self.dealer_value:
            return "dealer", False
        elif self.player_value == self.dealer_value:
            if player_has_bj and dealer_has_bj:
                return "tie", False
            if player_has_bj and not dealer_has_bj:
                return "player", True
            return "tie", False

    def player_draw(self):
        card = self.deck.pop(0)
        self.player_hand.append(card)
        if self.player_value == 21:
            self.state = GameState.DEALER_PHASE
            self.stand()
        elif self.player_value > 21:
            self.state = GameState.GAME_OVER
        return card

    def dealer_draw(self):
        card = self.deck.pop(0)
        self.dealer_hand.append(card)
        if self.dealer_value > 21:
            self.state = GameState.GAME_OVER
        return card
    
    def stand(self):
        if self.state == GameState.GAME_OVER:
            return
        self.state = GameState.DEALER_PHASE
        while(self.dealer_value < 17):
            self.dealer_draw()
        self.state = GameState.GAME_OVER

    def __str__(self):
        dealer_hand = ""
        player_hand = (f"**{self.player.display_name}** hand:"
                       f" {', '.join([str(x) for x in self.player_hand])}"
                       f" total: {self.player_value}")
        if self.state == GameState.RUNNING:
            dealer_hand = (f"**dealer** hand: {self.dealer_hand[0]}, "
                           f"? total: {self.dealer_hand[0].value}\n")
        else:
            dealer_hand = (f"**dealer** hand:"
                           f" {', '.join([str(x) for x in self.dealer_hand])}"
                           f" total: {self.dealer_value}")
        return f"{dealer_hand}\n{player_hand}"

    def build_embed(self, balance=None, buttons=None):
        winner, is_blackjack = self.get_winner()
        dealer_stop = 1 if self.state == GameState.RUNNING else len(self.dealer_hand)
        hidden_card = ", ?" if self.state == GameState.RUNNING else ""
        player_name = self.player.display_name
        player_hand = (f"{', '.join([str(x) for x in self.player_hand])}\ntotal: {self.player_value}")
        dealer_hand = (f"{', '.join([str(x) for x in self.dealer_hand[:dealer_stop]])}{hidden_card}\ntotal: {self.dealer_value}")
        game_embed = Embed(color=self.player.color)
        game_embed.set_author(name=player_name, icon_url=self.player.avatar.replace(format="png"))
        game_embed.add_field(name="Dealer's Hand", value=dealer_hand, inline=True)
        game_embed.add_field(name=f"{player_name}'s Hand", value=player_hand, inline=True)
        game_embed.add_field(name="Bet", value=f"{self.bet:,}", inline=False)
        if balance is not None:
            game_embed.add_field(name="New Balance:", value=f"{balance:,}", inline=True)
        if buttons is not None:
            description = ""
            for name, emoji in buttons.items():
                description += f"{name}:{emoji} | "
            description = description[:-2]
            game_embed.description = description
        if winner != "running":
            if winner == "player":
                winner = f"The Winner is **{player_name}**!"
            elif winner == "dealer":
                winner = "The Winner is **the dealer**!"
            else:
                winner = "Game is a **tie!**"
            black_jack = "with a Blackjack! (1.5 times the payout)" if is_blackjack else ""
            game_embed.title = f"{winner} {black_jack}"
        return game_embed

    async def payout(self, ctx=None):
        """
        add or subtract the bet from the player's account
        """
        balance = 0
        if not self.payday:
            balance = self.bet
        winner, is_blackjack = self.get_winner()
        if winner == "dealer":
            winner = "**Dealer** wins!"
            if self.payday:
                balance = (await self.payday.fetch_money(self.player.id)).get("money")
        elif winner == "player":
            winner = f"**{self.player.display_name}** wins!" 
            multiplicator = 1.5 if is_blackjack else 1
            if self.payday:
                balance = await self.payday.add_money(self.player.id, int(self.bet + self.bet * multiplicator))
        elif winner == "tie":
            winner = f"**Game is a tie!**"
            if self.payday:
                balance = await self.payday.add_money(self.player.id, self.bet)
        if self.message:
            self.clear_items()
            self.stop()
            await self.message.edit(embed=self.build_embed(balance), view=self)
        else:
            self.clear_items()
            self.stop()
            await ctx.send(embed=self.build_embed(balance), view=self)

    async def handle_hit(self, interaction: discord.Interaction = None):
        self.player_draw()
        if self.state == GameState.RUNNING:
            fold_button = discord.utils.get(self.children, label="Fold")
            double_button = discord.utils.get(self.children, label="Double")
            fold_button.disabled = True
            double_button.disabled = True
            if interaction:
                await interaction.response.edit_message(embed=self.build_embed(), view=self)
            else:
                await self.message.edit(embed=self.build_embed(), view=self)
        elif self.state == GameState.DEALER_PHASE:
            self.stand()
            await self.payout();
        elif self.state == GameState.GAME_OVER:
            await self.payout()

    async def handle_double(self):
        if len(self.player_hand) > 2:
            embed = self.build_embed()
            embed.description = "You can only double when holding 2 cards"
            await self.message.edit(embed=embed, view=self)
            return
        if self.payday:
            balance = (await self.payday.fetch_money(self.player.id)).get("money")
            if balance < self.bet:
                embed = self.build_embed()
                embed.description = "You don't have enough money for doubling down"
                return await self.message.edit(embed=embed, view=self)
            await self.payday.subtract_money(self.player.id, self.bet)
            self.bet += self.bet
        else:
            self.bet *= 2
        self.player_draw()
        self.stand()
        await self.payout()

    async def handle_fold(self, interaction: Optional[discord.Interaction] = None):
        if len(self.player_hand) > 2:
            embed = self.build_embed()
            embed.description = "You can only fold when holding 2 cards"
            if interaction:
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await self.message.edit(embed=embed, view=self)
            return
        if self.payday:
            new_amount = await self.payday.add_money(self.player.id, int(self.bet * 0.8))
            embed = self.message.embeds[0]
            embed.title="Fold" 
            embed.description=f"You gave up on this game and got 80% ({int(self.bet * 0.8):,}) of your bet back, better luck next time."
            embed.clear_fields()
            embed.add_field(name="New Balance", value=f"{new_amount:,}")
            self.clear_items()
            self.stop()
            if interaction:
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await self.message.edit(embed=embed, view=self)
        else:
            self.clear_items()
            if interaction:
                await interaction.response.edit_message(content="No money was bet but this game still gets stopped, better luck next time.", embed=None, view=self)
            else:
                await self.message.edit(content="No money was bet but this game still gets stopped, better luck next time.", embed=None, view=self)
            self.state = GameState.GAME_OVER
            self.stop()

class BlackJack(commands.Cog):
    """
    gamble your life away in Blackjack
    """
    def __init__(self, bot):
        self.bot = bot
        self.payday = self.bot.get_cog("Payday")
        self.games = []
        self.folds = []

    async def cog_unload(self):
        if not self.payday:
            return
        try:
            for game in self.games:
                await self.payday.add_money(game.player.id, game.bet)
                game.clear_items()
                game.stop()

        except Exception as e:
            import logging
            logger = logging.getLogger("PoutyBot")
            logger.error("Exception while giving back blackjack bets", exc_info=1)
            owner = self.bot.get_user(self.bot.owner_id)
            pending_payouts = "Some BlackJack payouts are still pending\n"
            for game in self.games:
                pending_payouts += f"{game.player.mention}: {game.bet:,}"
            self.bot.loop.create_task(owner.send(pending_payouts))

    async def cog_before_invoke(self, ctx):
        # try to ensure that payday is loaded everytime we invoke a command
        self.payday = self.bot.get_cog("Payday")

    def get_game(self, player):
        """
        helper function to get the currently running game of a player
        """
        game = next(iter(x for x in self.games if x.player == player), None)
        if not game:
            raise commands.CommandError("No game running start one with `.bj`")
        return game


    @commands.group(name="blackjack",invoke_without_command=True, aliases=["bj"])
    @checks.channel_only("test", "bot-shenanigans", 336912585960194048, 248987073124630528)    
    @commands.guild_only()
    async def blackjack_group(self, ctx, bet:Bet):
        """
        very basic implementation of black jack:
        Every game/round starts with a full deck
        You can only hit (draw a new card) or stand (let dealer draw)
        If you win with a Blackjack you get 1.5 times of your bet as payout
        otherwise you get the bet as payout.
        """
        balance = None
        if self.payday:
            balance = await self.payday.fetch_money(ctx.author.id)
            if not balance:
                return await ctx.send("No bank account create one with `.payday`")
            if balance.get("money") < bet:
                return await ctx.send("You can't bet more than you own!")
            content = None
        else:
            content = "Payday not loaded this game is just for fun"
        if bet < 1:
            return await ctx.send("You can't bet less than 1")
        game = next(iter(x for x in self.games if x.player == ctx.author), None)
        if game:
            return await ctx.send("You already started a game either hit or stand")
        game = BlackJackGame(ctx.author, bet, self.payday)
        if self.payday:
            balance = await self.payday.subtract_money(ctx.author.id, bet)
        self.games.append(game)
        if game.state == GameState.GAME_OVER:
            await game.payout(ctx=ctx)
            self.games.remove(game)
            return

        game.message = await ctx.send(content=content, embed=game.build_embed(), view=game)
        await game.wait()
        self.games.remove(game)

    @blackjack_group.command(name="hit", aliases=["draw"])
    async def draw_card(self, ctx):
        """
        draw a new card if you go over 21 you lose!
        """
        game = self.get_game(ctx.author)
        await game.handle_hit()

    @blackjack_group.command(name="surrender", aliases=["fold"])
    async def surrender(self, ctx):
        """
        If you don't like your initial hand you can discard the game and start new
        only works if you haven't hit yet. Also you pay 20% fee.
        """
        game = self.get_game(ctx.author)
        await game.handle_fold()

    @blackjack_group.command(name="stand", aliases=["stop"])
    async def stand(self, ctx):
        """
        stop drawing cards and let the dealer draw, game is over after this
        """
        game = self.get_game(ctx.author)
        game.stand()
        await game.payout()

    @blackjack_group.command(name="double", aliases=["dd"])
    async def double(self, ctx):
        """
        When holding 2 cards double your bet and draw only one more card before standing
        """
        game = self.get_game(ctx.author)       
        await game.handle_double()

    @blackjack_group.command(name="status")
    async def status(self, ctx):
        """
        gives you the status of the currently running game
        """
        game = self.get_game(ctx.author)
        await ctx.send(game.message.jump_url)


class DeathrollStates(Enum):
    WAITING = auto()
    PLAYING = auto()
    GAME_OVER = auto()


class DeathrollGame():

    def __init__(self, player, bet):
        self.game_state = DeathrollStates.WAITING
        self.bet = bet
        self.roll_amount = bet * 10
        self.start_player = player
        self.challenger = None
        self.current_player = None
        self.message = None
        self.winner = None
        self.timer = None

    def add_player(self, member):
        if self.challenger:
            return 
        self.challenger = member
        return member

    def roll(self, player):
        if self.current_player != player:
            return
        if self.game_state in (DeathrollStates.WAITING, DeathrollStates.GAME_OVER):
            return
        self.roll_amount = random.randint(1, self.roll_amount)
        if self.roll_amount == 1:
            self.winner = self.start_player if self.current_player.id == self.challenger.id else self.challenger
            self.game_state = DeathrollStates.GAME_OVER
            return
        self.current_player = self.start_player if self.current_player.id == self.challenger.id else self.challenger

    def __eq__(self, other):
        return self.start_player == other.start_player

    def __str__(self):
        if self.game_state == DeathrollStates.WAITING:
            return f"WAITING FOR PLAYERS\nREACT WITH \N{SKULL} TO JOIN"
        if self.game_state == DeathrollStates.PLAYING:
            return f"Game in progress:\nCurrent Player: **{self.current_player.mention}**\nCurrent Roll amount: {self.roll_amount}\N{GAME DIE}"
        if self.game_state == DeathrollStates.GAME_OVER:
            return f"GAME OVER!\nWINNER: **{self.winner.mention}**"

class Deathroll(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.games = []
        self.join_reaction = "\N{SKULL}"
        self.roll_reaction = "\N{GAME DIE}"
        self.resolve_reaction = "\N{ROCKET}"
        self.accept_reaction = "\N{WHITE HEAVY CHECK MARK}"
        self.reject_reaction = "\N{NEGATIVE SQUARED CROSS MARK}"
        self.payday = self.bot.get_cog("Payday")

    async def cog_unload(self):
        if not self.payday:
            return
        try:
            await self.pay_back_all_games()
        except Exception as e:
            import logging
            logger = logging.getLogger("PoutyBot")
            logger.error("Exception while giving back deathroll bets", exc_info=1)
            owner = self.bot.get_user(self.bot.owner_id)
            pending_payouts = "Some DeathRoll payouts are still pending\n"
            for game in self.games:
                pending_payouts += f"{game.start_player.mention}: {game.bet:,}\n"
                pending_payouts += f"{game.challenger.mention}: {game.bet:,}\n"
            self.bot.loop.create_task(owner.send(pending_payouts))

    async def pay_back_all_games(self):
        while len(self.games) > 0:
            game =self.games.pop(0)
            await self.payday.add_money(game.start_player.id, game.bet)
            await self.payday.add_money(game.challenger.id, game.bet)
            await game.message.clear_reactions()
            del game

    def get_game(self, player):
        """
        helper function to get the currently running game of a player
        """
        game = next(iter(x for x in self.games if x.start_player == player), None)
        if not game:
            raise commands.CommandError("No game running start one with `.dr`")
        return game

    def get_game_by_message(self, message):
        game = next(iter(x for x in self.games if x.message is not None and x.message.id == message.id), None)
        if not game:
            raise commands.CommandError("No game running start one with `.dr`")
        return game

    async def payout(self, game):
        await self.payday.add_money(game.winner.id, game.bet * 2)

    async def notify_player(self, game):
        await asyncio.sleep(30)
        await game.message.channel.send(f"{game.current_player.mention} your turn to roll.")

    async def resolve_game(self,game):
        await game.message.clear_reactions()
        embed = game.message.embeds[0]
        embed.description = str(game)
        if self.payday:
            await self.payout(game)
            start_pl_money = await self.payday.fetch_money(game.start_player.id)
            challenger_money = await self.payday.fetch_money(game.challenger.id)
            embed.add_field(name=f"{game.start_player.display_name}'s balance:", value=f"{start_pl_money['money']:,}")
            embed.add_field(name=f"{game.challenger.display_name}'s balance:", value=f"{challenger_money['money']:,}")
        await game.message.edit(embed=embed)
        self.games.remove(game)

    @commands.Cog.listener("on_reaction_add")
    async def button_reaction(self, reaction, user):
        try:
            game = self.get_game_by_message(reaction.message)
        except commands.CommandError:
            return
        if user.id == self.bot.user.id:
            return
        if game.message.id != reaction.message.id:
            return
        if game.game_state == DeathrollStates.GAME_OVER:
            return
        await game.message.remove_reaction(reaction.emoji, user)
        if game.game_state == DeathrollStates.PLAYING and user.id != game.start_player.id and user.id != game.challenger.id:
            return
        if game.start_player.id == user.id and reaction.emoji not in (self.roll_reaction, self.resolve_reaction):
            return
        if reaction.emoji == self.join_reaction:
            if not game.add_player(user):
                await game.message.channel.send("Game is already full")
                return
            if self.payday:
                try:
                    await self.payday.subtract_money(game.challenger.id, game.bet)
                except commands.CommandError as e:
                    await game.message.channel.send(f"{game.challenger.mention} {e}")
                    game.challenger = None
                    return
            await game.message.clear_reactions()
            await game.message.add_reaction(self.roll_reaction)
            await game.message.add_reaction(self.resolve_reaction)
            embed = game.message.embeds[0]
            embed.add_field(name="Start Player:", value=f"{game.start_player.mention}")
            embed.add_field(name="Challenger", value=f"{game.challenger.mention}")
            game.game_state = DeathrollStates.PLAYING
            game.current_player = game.start_player
            embed.description = str(game)
            await game.message.edit(embed=embed)
            game.timer = asyncio.create_task(self.notify_player(game))
            return
        if reaction.emoji == self.roll_reaction and game.game_state == DeathrollStates.PLAYING:
            game.timer.cancel()
            game.roll(user)
            embed = game.message.embeds[0]
            embed.description = str(game)
            if game.game_state == DeathrollStates.GAME_OVER:
                await self.resolve_game(game)
            if game.game_state == DeathrollStates.PLAYING:
                game.timer = asyncio.create_task(self.notify_player(game))
            await game.message.edit(embed=embed)
            return
        if reaction.emoji == self.resolve_reaction and game.game_state == DeathrollStates.PLAYING:
            game.timer.cancel()
            while(game.game_state != DeathrollStates.GAME_OVER):
                game.roll(game.current_player)
            embed = game.message.embeds[0]
            embed.description = str(game)
            await self.resolve_game(game)
            await game.message.edit(embed=embed)
            return
        if reaction.emoji == self.accept_reaction and user.id == game.challenger.id:
            if self.payday:
                try:
                    await self.payday.subtract_money(game.challenger.id, game.bet)
                except commands.CommandError as e:
                    await ctx.send(f"{game.challenger.mention} {e}")
            game.game_state = DeathrollStates.PLAYING
            game.current_player = game.start_player
            embed = game.message.embeds[0]
            embed.description = str(game)
            await game.message.clear_reactions()
            await game.message.add_reaction(self.roll_reaction)
            await game.message.add_reaction(self.resolve_reaction)
            await game.message.edit(embed=embed)
            game.timer = asyncio.create_task(self.notify_player(game))
            return 
        if reaction.emoji == self.reject_reaction and user.id == game.challenger.id and game.game_state != DeathrollStates.PLAYING:
            await game.message.channel.send(f"{game.challenger.display_name} rejected the match.")
            await game.message.delete()
            if self.payday:
                await self.payday.add_money(game.start_player.id, game.bet)
            self.games.remove(game)
            del game
            return



    @commands.group(name="deathroll", aliases=['dr'], invoke_without_command=True)
    async def deathroll(self, ctx, amount: Bet, challenger: Optional[Member]):
        """
        Starts a game of deathroll
        Rules:
        Players take turns and roll a dice for values between 1 and 10 times the betting amount (1st Round)
        Next round the possible roll result is between 1 and the previous result
        This continues until someone rolls a 1. In that case the player rolling 1 loses.
        reactions: 
        * \N{SKULL} is for joining a game
        * \N{GAME DIE} is for rolling the dice
        * \N{ROCKET} is for auto resolving the game
        """
        if amount < 1: 
            return await ctx.send("can't bet less than 1")
        try:
            game = self.get_game(ctx.author)
            return await ctx.send("Game is already running finish that one first.\n"
                                  f"{game.message.jump_url}")
        except commands.CommandError as e:
            if self.payday:
                try:
                    await self.payday.subtract_money(ctx.author.id, amount)
                except commands.CommandError as cme:
                    return await ctx.send(cme)
            game = DeathrollGame(ctx.author, amount)
            embed = Embed(title="\N{SKULL} Deathroll \N{SKULL}", description=str(game),
                              color=ctx.author.colour)
            embed.add_field(name="Bet", value=game.bet)
            self.games.append(game)
            if challenger:
                if self.payday:
                    money_challenger = await self.payday.fetch_money(challenger.id)
                    if not money_challenger:
                        await self.payday.add_money(ctx.author.id, game.bet)
                        self.games.remove(game)
                        del game
                        return await ctx.send("The player you challenged doesn't have an account they first need to start one with the `.payday` command")
                    if not money_challenger or money_challenger['money'] < game.bet:
                        await self.payday.add_money(ctx.author.id, game.bet)
                        self.games.remove(game)
                        del game
                        return await ctx.send("The player you challenged has not enough money.")
                game.add_player(challenger)
                embed.description = f"{game.start_player.mention} challenged {game.challenger.mention} react with {self.accept_reaction} to accept or {self.reject_reaction} to reject"
                message = await ctx.send(embed=embed)
                game.message = message
                await message.add_reaction(self.accept_reaction)
                await message.add_reaction(self.reject_reaction)
                return
            message = await ctx.send(embed=embed)
            game.message = message
            await message.add_reaction(self.join_reaction)

    @deathroll.command(name="cancel")
    async def cancel(self, ctx):
        """
        cancel a game unless it already started.
        """
        try:
            game = self.get_game(ctx.author)
            if game.game_state == DeathrollStates.PLAYING:
                return await ctx.send("You can't cancel a game that is already in progress!")
            if self.payday:
                await self.payday.add_money(ctx.author.id, game.bet)
            self.games.remove(game)
            await game.message.delete()
            await ctx.send("Game was cancelled")
            del game
        except commands.CommandError as e:
            return await ctx.send(e)


async def setup(bot):
    await bot.add_cog(BlackJack(bot))
    await bot.add_cog(Deathroll(bot))
