from discord.ext import commands
from discord import Embed
from enum import Enum, auto
from .utils import checks
import random


class CardColor(Enum):
    heart = "\N{WHITE HEART SUIT}"
    spade = "\N{WHITE SPADE SUIT}"
    diamond = "\N{WHITE DIAMOND SUIT}"
    club = "\N{WHITE CLUB SUIT}"


class GameState(Enum):
    RUNNING = auto()
    DEALER_PHASE = auto()
    GAME_OVER = auto()


class Card():
    def __init__(self, value, color, face):
        self.value = value
        self.color = color
        self.face = face

    def __str__(self):
        return f"{self.face}{self.color}"


class BlackJackGame():

    def __init__(self, ctx, player, bet):
        self.player = player
        self.ctx = ctx
        self.state = GameState.RUNNING
        self.bet = bet
        self.deck = self.generate_deck()
        self.dealer_hand = [self.deck.pop(0), self.deck.pop(0)]
        self.player_hand = [self.deck.pop(0), self.deck.pop(0)]
        if self.player_value == 21:
            self.state = GameState.DEALER_PHASE

    def __eq__(self, other):
        return self.player == other.player

    def generate_deck(self):
        deck = []
        for color in list(CardColor):
            deck.append(Card(1, color.value, "A"))
            deck.append(Card(10, color.value, "J"))
            deck.append(Card(10, color.value, "Q"))
            deck.append(Card(10, color.value, "K"))
            for i in range(2, 11):
                deck.append(Card(i, color.value, str(i)))
        random.shuffle(deck)
        return deck

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

    def build_embed(self, balance=None):
        winner, is_blackjack = self.get_winner()
        dealer_stop = 1 if self.state == GameState.RUNNING else len(self.dealer_hand)
        player_name = self.player.display_name
        player_hand = (f"{', '.join([str(x) for x in self.player_hand])}\ntotal: {self.player_value}")
        dealer_hand = (f"{', '.join([str(x) for x in self.dealer_hand[:dealer_stop]])}\ntotal: {self.dealer_value}")
        game_embed = Embed(color=self.player.color)
        game_embed.set_author(name=player_name, icon_url=self.player.avatar_url_as(format="png"))
        game_embed.add_field(name="Dealer's Hand", value=dealer_hand, inline=True)
        game_embed.add_field(name=f"{player_name}'s Hand", value=player_hand, inline=True)
        game_embed.add_field(name="Bet", value=f"{self.bet:,}", inline=False)
        if balance:
            game_embed.add_field(name="New Balance:", value=f"{balance:,}", inline=True)
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

class BlackJack(commands.Cog):
    """
    gamble your life away in Blackjack
    """
    def __init__(self, bot):
        self.bot = bot
        self.payday = self.bot.get_cog("Payday")
        self.games = []
        self.folds = []

    def cog_unload(self):
        if not self.payday:
            return
        try:
            for game in self.games:
                self.bot.loop.create_task(self.payday.add_money(game.player.id, game.bet))
                self.games.remove(game)
                del game
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

    async def payout(self, ctx, game):
        """
        add or subtract the bet from the player's account
        """
        self.games.remove(game)
        balance = 0
        if not self.payday:
            balance = game.bet
        winner, is_blackjack = game.get_winner()
        if winner == "dealer":
            winner = "**Dealer** wins!"
            if self.payday:
                balance = (await self.payday.fetch_money(ctx.author.id)).get("money")
        elif winner == "player":
            winner = f"**{game.player.display_name}** wins!" 
            multiplicator = 1.5 if is_blackjack else 1
            if self.payday:
                balance = await self.payday.add_money(ctx.author.id, int(game.bet + game.bet * multiplicator))
        elif winner == "tie":
            winner = f"**Game is a tie!**"
            if self.payday:
                balance = await self.payday.add_money(ctx.author.id, game.bet)
        await ctx.send(embed=game.build_embed(balance))
        self.folds = [p for p in self.folds if p != game.player]
        del game

    @commands.group(name="blackjack",invoke_without_command=True, aliases=["bj"])
    @checks.channel_only("test", "bot-shenanigans", 336912585960194048, 248987073124630528)    
    @commands.guild_only()
    async def blackjack_group(self, ctx, bet:int):
        """
        very basic implementation of black jack:
        Every game/round starts with a full deck
        You can only hit (draw a new card) or stand (let dealer draw)
        If you win with a Blackjack you get 1.5 times of your bet as payout
        otherwise you get the bet as payout.
        """
        if self.payday:
            balance = await self.payday.fetch_money(ctx.author.id)
            if not balance:
                return await ctx.send("No bank account create one with `.payday`")
            if balance.get("money") < bet:
                return await ctx.send("You can't bet more than you own!")
        else:
            await ctx.send("Payday not loaded this game is just for fun")
        if bet < 1:
            return await ctx.send("You can't bet less than 1")
        game = next(iter(x for x in self.games if x.player == ctx.author), None)
        if game:
            return await ctx.send("You already started a game either hit or stand")
        game = BlackJackGame(ctx, ctx.author, bet)
        if self.payday:
            await self.payday.subtract_money(ctx.author.id, bet)
        self.games.append(game)
        if game.state == GameState.DEALER_PHASE:
            game.stand()
            await self.payout(ctx, game)
            return
        return await ctx.send(embed=game.build_embed())

    

    @blackjack_group.command(name="hit", aliases=["draw"])
    async def draw_card(self, ctx):
        """
        draw a new card if you go over 21 you lose!
        """
        game = self.get_game(ctx.author)
        game.player_draw()
        if game.state == GameState.DEALER_PHASE or game.state == GameState.GAME_OVER:
            game.stand()
            await self.payout(ctx, game)
            return
        return await ctx.send(embed=game.build_embed())

    @blackjack_group.command(name="surrender", aliases=["fold"])
    async def surrender(self, ctx):
        """
        If you don't like your initial hand you can discard the game and start new
        only works if you haven't hit yet. Also you pay 20% fee.
        """
        game = self.get_game(ctx.author)
        if len([p for p in self.folds if p == game.player]) > 2:
            return await ctx.send("You already folded thrice, no more allowed finish at least this game!")
        if len(game.player_hand) > 2:
            return await ctx.send("You already drew at least a card, you are now commited to this game")
        if self.payday:
            await self.payday.add_money(ctx.author.id, int(game.bet * 0.8))
            await ctx.send(f"You gave up on this game and got 80% ({int(game.bet * 0.8)}) of your bet back, better luck next time.")
            self.folds.append(ctx.author)
        else:
            await ctx.send("No money was bet but this game still gets stopped, better luck next time.")
        self.games.remove(game) 
        del game

    @blackjack_group.command(name="stand", aliases=["stop"])
    async def stand(self, ctx):
        """
        stop drawing cards and let the dealer draw, game is over after this
        """
        game = self.get_game(ctx.author)
        game.state = GameState.DEALER_PHASE
        game.stand()
        await self.payout(ctx, game)

    @blackjack_group.command(name="double", aliases=["dd"])
    async def double(self, ctx):
        """
        When holding 2 cards double your bet and draw only one more card before standing
        """
        game = self.get_game(ctx.author)       
        if len(game.player_hand) > 2:
            return await ctx.send("You can only double down when holding 2 cards")
        if self.payday:
            balance = (await self.payday.fetch_money(ctx.author.id)).get("money")
            if balance < game.bet:
                return await ctx.send("You don't have enough money for doubling down.")
            await self.payday.subtract_money(ctx.author.id, game.bet)
            game.bet += game.bet
        else:
            game.bet *= 2
        game.player_draw()
        game.state = GameState.DEALER_PHASE
        game.stand()
        await self.payout(ctx, game)
        

    @blackjack_group.command(name="status")
    async def status(self, ctx):
        """
        gives you the status of the currently running game
        """
        game = self.get_game(ctx.author)
        await ctx.send(embed=game.build_embed())


def setup(bot):
    bot.add_cog(BlackJack(bot))
