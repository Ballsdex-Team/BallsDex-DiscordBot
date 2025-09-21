from dataclasses import dataclass, field
import random
from typing import Dict, List

@dataclass
class Ability:
    name: str
    description: str  # Add description field
    damage: int
    max_uses: int
    logic: callable  # Custom logic for the ability
    ball_name: str = ""  # Name of the ball this ability belongs to
    uses: int = 0  # Tracks how many times the ability has been used
    is_passive: bool = False  # Whether the ability is passive
    trigger: str = "user_initiated"  # When the ability is triggered
    activation_message: str = ""  # Message displayed when the ability is activated
    ends_turn: bool = False  # Whether using the ability ends the user's turn

def define_abilities() -> Dict[str, Ability]:
    return {
        "pepper_master": Ability(
            name="Pepper Master!",
            description="Dutch Empire can use his spices to boost up ATK stats by 25%. (Uses: 3)",
            damage=0,
            max_uses=3,
            ball_name="Dutch Empire",
            logic=lambda attacker, defender: (
                setattr(attacker, "attack", int(attacker.attack * 1.25)) or attacker.attack
            ),
            is_passive=False,
            trigger="user_initiated",
            activation_message="Dutch Empire's `Pepper Master!` increased Dutch Empire's ATK by 25%!",
            ends_turn=False,  # Does not end the turn
        ),
        "you_cant_swim_bro": Ability(
            name="You can't swim bro?",
            description="This ball can drown the opponent's ball dealing 250 damage each time.",
            damage=250,
            max_uses=5,
            ball_name="Pacific Ocean",
            logic=lambda attacker, defender: setattr(defender, "health", defender.health - 250),
            is_passive=False,
            trigger="user_initiated",
            activation_message="Pacific Ocean's `You can't swim bro?` dealt 250 damage to the opponent!",
            ends_turn=False,  # Ends the turn
        ),
        "extremely_hot": Ability(
            name="Extremely Hot",
            description="When this ball comes to the battlefield, the opponent's ball takes 100 damage each round.",
            damage=100,
            max_uses=-1,  # Unlimited while active
            ball_name="Tumbleweed",
            logic=lambda attacker, defender: setattr(defender, "health", defender.health - 100),
            is_passive=True,
            trigger="on_battlefield",
            activation_message="Tumbleweed's `Extremely Hot` burned the opponent, dealing 100 damage!",
            ends_turn=False,  # Passive abilities do not end the turn
        ),
        "on_the_wind_of_pacific_ocean": Ability(
            name="On the wind of Pacific Ocean!",
            description="On the wind of Pacific Ocean! - If the Pacific Ocean is in your deck, Tokelau gains +300 stats bonus on attack and hp.",
            damage=0,
            max_uses=-1,  # Passive ability
            ball_name="Tokelau",
            logic=lambda attacker, defender: (
                setattr(attacker, "health", attacker.health + 300),
                setattr(attacker, "attack", attacker.attack + 300)
            ) if any(ball.ball_name == "Pacific Ocean" for ball in attacker.deck) else None,
            is_passive=True,
            trigger="on_battlefield",
            activation_message="Tokelau's `On the wind of Pacific Ocean!` boosted HP and ATK by 300!",
            ends_turn=False,  # Passive abilities do not end the turn
        ),
        "broken_seal": Ability(
            name="Broken Seal",
            description="When this ball is half hp it then will regenerate into its full hp and release it's full potential.",
            damage=0,
            max_uses=1,
            ball_name="Sealed Reichtangle",
            logic=lambda attacker, defender: (
                setattr(attacker, "health", attacker.health * 2) if attacker.health <= attacker.max_health // 2 else None,
                setattr(attacker, "attack", attacker.attack * 2) if attacker.health <= attacker.max_health // 2 else None,
            ),
            is_passive=True,
            trigger="on_health",
            activation_message="`Broken Seal` activated, causing Sealed Reichtangle to double its HP and ATK!",
            ends_turn=False,  # Passive abilities do not end the turn
        ),
        "the_only_missing": Ability(
            name="The only missing!",
            description="Missing ball can make the opponent's ball disappear for 5 turns from the Battlefield. (Usable twice)",
            damage=0,
            max_uses=2,
            ball_name="Missing Ball",
            logic=lambda attacker, defender: setattr(defender, "disappeared", 2),
            is_passive=False,
            trigger="user_initiated",
            activation_message="Missing Ball's `The only missing!` made the opponent's ball disappear for 2 turns!",
            ends_turn=True,
        ),
        "black_may": Ability(
            name="Black May",
            description="Thaitangle can boost its attack by 200% for 3 rounds, but if the targeted ball does not die, then it dies immediately.",
            damage=0,
            max_uses=1,
            ball_name="Thaitangle",
            logic=lambda attacker, defender: (
                setattr(attacker, "attack", int(attacker.attack * 2)),
                setattr(attacker, "black_may_turns", 3),
            ),
            is_passive=False,
            trigger="user_initiated",
            activation_message="Thaitangle's `Black May` boosted its attack by 200% for 3 rounds!",
            ends_turn=False,
        ),
        "tangle_time": Ability(
            name="Tangle Time!!!",
            description="Mauritangle can make the opponents dance to the tango for 5 rounds, decreasing their attack by 33%.",
            damage=0,
            max_uses=1,
            ball_name="Mauritangle",
            logic=lambda attacker, defender: setattr(defender, "attack", int(defender.attack * 0.67)),
            is_passive=False,
            trigger="user_initiated",
            activation_message="Mauritangle's `Tangle Time!!!` reduced the opponent's attack by 33% for 5 rounds!",
            ends_turn=True,
        ),
        "randomizer": Ability(
            name="Randomizer!",
            description="When Random Ball gets killed, it chooses a random ball from the opponent's deck and uses its attack and HP. (Usable once)",
            damage=0,
            max_uses=1,
            ball_name="Random Ball",
            logic=lambda attacker, defender: (
                setattr(attacker, "health", random.choice(defender.deck).health),
                setattr(attacker, "attack", random.choice(defender.deck).attack),
            ),
            is_passive=True,
            trigger="on_death",
            activation_message="Random Ball's `Randomizer!` activated, copying stats from a random opponent's ball!",
            ends_turn=False,
        ),
        "ice_berg_crash": Ability(
            name="Ice Berg Crash!",
            description="Arctic Ocean can use its icebergs to stun the opponent for 2 turns and deal 420 damage. (Usable twice)",
            damage=420,
            max_uses=2,
            ball_name="Arctic Ocean",
            logic=lambda attacker, defender: (
                setattr(defender, "health", defender.health - 420),
                setattr(defender, "stunned", 2),
            ),
            is_passive=False,
            trigger="user_initiated",
            activation_message="Arctic Ocean's `Ice Berg Crash!` dealt 420 damage and stunned the opponent for 2 turns!",
            ends_turn=True,
        ),
        "brothers_made_of_snow_and_ice": Ability(
            name="Brothers made of Snow and Ice!",
            description="When Arctic Ocean is in your deck, both Arctic Ocean and Antarctic Empire gain 300 stats.",
            damage=0,
            max_uses=-1,
            ball_name="Antarctic Empire",
            logic=lambda attacker, defender: (
                setattr(attacker, "health", attacker.health + 300),
                setattr(attacker, "attack", attacker.attack + 300),
            ) if any(ball.ball_name == "Arctic Ocean" for ball in attacker.deck) else None,
            is_passive=True,
            trigger="on_battlefield",
            activation_message="Antarctic Empire's `Brothers made of Snow and Ice!` boosted its stats by 300!",
            ends_turn=False,
        ),
    }        


@dataclass
class BattleBall:
    name: str
    owner: str
    health: int = 100
    attack: int = 10
    abilities: List[Ability] = field(default_factory=list)
    used_abilities: Dict[str, int] = field(default_factory=dict)
    emoji: str = ""
    dead: bool = False


@dataclass
class BattleInstance:
    p1_balls: list = field(default_factory=list)
    p2_balls: list = field(default_factory=list)
    battle_log = []  # Log of battle actions
    winner: str = ""
    turns: int = 0


def get_damage(ball):
    return int(ball.attack * random.uniform(0.8, 1.2))


def attack(current_ball, enemy_balls):
    alive_balls = [ball for ball in enemy_balls if not ball.dead]
    enemy = random.choice(alive_balls)

    attack_dealt = get_damage(current_ball)
    enemy.health -= attack_dealt

    if enemy.health <= 0:
        enemy.health = 0
        enemy.dead = True
    if enemy.dead:
        gen_text = f"{current_ball.owner}'s {current_ball.name} has killed {enemy.owner}'s {enemy.name}"
    else:
        gen_text = f"{current_ball.owner}'s {current_ball.name} has dealt {attack_dealt} damage to {enemy.owner}'s {enemy.name}"
    return gen_text


def random_events():
    if random.randint(0, 100) <= 30: # miss
        return 1
    else:
        return 0


def gen_battle(battle: BattleInstance):
    turn = 0  # Initialize turn counter

    # Continue the battle if both players have at least one alive ball.
    # End the battle if all balls do less than 1 damage.

    if all(
        ball.attack <= 0 for ball in battle.p1_balls + battle.p2_balls
    ):
        yield (
            "Everyone stared at each other, "
            "resulting in nobody winning."
        )
        return

    while any(ball for ball in battle.p1_balls if not ball.dead) and any(
        ball for ball in battle.p2_balls if not ball.dead
    ):
        alive_p1_balls = [ball for ball in battle.p1_balls if not ball.dead]
        alive_p2_balls = [ball for ball in battle.p2_balls if not ball.dead]

        for p1_ball, p2_ball in zip(alive_p1_balls, alive_p2_balls):
            # Player 1 attacks first

            if not p1_ball.dead:
                turn += 1

                event = random_events()
                if event == 1:
                    yield f"Turn {turn}: {p1_ball.owner}'s {p1_ball.name} missed {p2_ball.owner}'s {p2_ball.name}"
                    continue
                yield f"Turn {turn}: {attack(p1_ball, battle.p2_balls)}"

                if all(ball.dead for ball in battle.p2_balls):
                    break
            # Player 2 attacks
            
            if not p2_ball.dead:
                turn += 1

                event = random_events()
                if event == 1:
                    yield f"Turn {turn}: {p2_ball.owner}'s {p2_ball.name} missed {p1_ball.owner}'s {p1_ball.name}"
                    continue
                yield f"Turn {turn}: {attack(p2_ball, battle.p1_balls)}"

                if all(ball.dead for ball in battle.p1_balls):
                    break
    # Determine the winner

    if all(ball.dead for ball in battle.p1_balls):
        battle.winner = battle.p2_balls[0].owner
    elif all(ball.dead for ball in battle.p2_balls):
        battle.winner = battle.p1_balls[0].owner
    # Set turns

    battle.turns = turn


# test


if __name__ == "__main__":
    battle = BattleInstance(
        [
            BattleBall("Republic of China", "eggum", 3120, 567),
            BattleBall("German Empire", "eggum", 2964, 784),
            BattleBall("United States", "eggum", 2850, 1309),
        ],
        [
            BattleBall("United Kingdom", "xen64", 2875, 763),
            BattleBall("Israel", "xen64", 1961, 737),
            BattleBall("Soviet Union", "xen64", 2525, 864),
        ],
    )

    print(
        f"Battle between {battle.p1_balls[0].owner} and {battle.p2_balls[0].owner} begins! - {battle.p1_balls[0].owner} begins"
    )
    for attack_text in gen_battle(battle):
        print(attack_text)
    print(f"Winner:\n{battle.winner} - Turn: {battle.turns}")
