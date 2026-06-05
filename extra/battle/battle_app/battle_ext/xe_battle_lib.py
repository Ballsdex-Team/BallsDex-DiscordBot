import random
from dataclasses import dataclass, field

# --- Message Templates ---
ATTACK_MESSAGES = [
    "🤺 | {a_owner}'s {a_name} shoves into {d_owner}'s {d_name}, dealing {dmg} DMG!",
    "🤺 | {a_name} hoards a massive blow to {d_name}, lowering {dmg} DMG!",
    "🤺 | {a_owner}'s {a_name} slices {d_name} Fruit Ninja style! ({dmg} DMG)",
    "🤺 | {a_name} launches a Haki-infused attack straight towards {d_name} for {dmg} DMG",
]

DEFEAT_MESSAGES = [
    "💀 | {a_name} has easily crushed {d_name}!",
    "💀 | {d_owner}'s {d_name} has fallen to {a_owner}'s {a_name}.",
    "💀 | {a_name} knocks out {d_name}!",
    "💀 | {d_name} has been defeated!",
]

DODGE_MESSAGES = [
    "❌ | *{a_name} shimmys through {d_name} swing!*",
    "❌ | *{d_owner}'s {d_name} quickly evades {a_name}'s attack!*",
    "❌ | *{d_name} uses Future Sight to dodge!*",
]

HEAL_MESSAGES = [
    "❤️‍🩹 | {a_owner}'s {a_name} uses a recovery move and heals {heal} HP!",
    "❤️‍🩹 | {a_name} shines brightly and regains {heal} health!",
    "❤️‍🩹 | {a_name} patches itself up for {heal} HP!",
    "❤️‍🩹 | {a_owner}'s {a_name} eats some meat and restores {heal} HP!",
]


def format_random(msg_list, **kwargs):
    return random.choice(msg_list).format(**kwargs)


@dataclass
class BattleBall:
    name: str
    owner: str
    health: int
    attack: int
    emoji: str = ""
    dead: bool = False
    max_health: int = field(init=False)

    def __post_init__(self):
        self.max_health = self.health


@dataclass
class BattleInstance:
    p1_balls: list = field(default_factory=list)
    p2_balls: list = field(default_factory=list)
    winner: str = ""
    turns: int = 0
    deck_size: int = 4


def get_damage(ball):
    base = ball.attack * random.uniform(0.5, 1)
    is_super = random.random() < 0.20
    if is_super:
        return int(base * 1.5), True
    return int(base), False


def attack(current_ball, enemy_balls):
    alive_balls = [ball for ball in enemy_balls if not ball.dead]
    enemy = random.choice(alive_balls)
    damage, is_super = get_damage(current_ball)
    enemy.health -= damage

    if enemy.health <= 0:
        enemy.health = 0
        enemy.dead = True

    if enemy.dead:
        text = format_random(
            DEFEAT_MESSAGES,
            a_owner=current_ball.owner,
            a_name=current_ball.name,
            d_owner=enemy.owner,
            d_name=enemy.name,
            dmg=damage,
        )
    else:
        text = format_random(
            ATTACK_MESSAGES,
            a_owner=current_ball.owner,
            a_name=current_ball.name,
            d_owner=enemy.owner,
            d_name=enemy.name,
            dmg=damage,
        )

    if is_super:
        text += "\n💥 **CRITICAL HIT!**"

    return text


def heal(current_ball):
    if current_ball.health >= current_ball.max_health * 0.7:
        return f"**{current_ball.name}** tries to heal, but their health is already replenished!"

    missing_hp = current_ball.max_health - current_ball.health
    heal_amount = int(missing_hp * random.uniform(0.3, 0.6))
    old_health = current_ball.health
    current_ball.health = min(current_ball.health + heal_amount, current_ball.max_health)
    actual_heal = current_ball.health - old_health

    text = format_random(HEAL_MESSAGES, a_owner=current_ball.owner, a_name=current_ball.name, heal=actual_heal)
    return text


def random_events(p1_ball, p2_ball):
    if random.randint(1, 100) <= 20:
        msg = format_random(
            DODGE_MESSAGES, a_owner=p2_ball.owner, a_name=p2_ball.name, d_owner=p1_ball.owner, d_name=p1_ball.name
        )
        return True, msg
    return False, ""


def gen_battle(battle: BattleInstance):
    turn = 0
    while any(ball for ball in battle.p1_balls if not ball.dead) and any(
        ball for ball in battle.p2_balls if not ball.dead
    ):
        alive_p1 = [ball for ball in battle.p1_balls if not ball.dead]
        alive_p2 = [ball for ball in battle.p2_balls if not ball.dead]

        for p1_ball, p2_ball in zip(alive_p1, alive_p2):
            if not p1_ball.dead:
                turn += 1

                if random.randint(1, 100) <= 20 and p1_ball.health < p1_ball.max_health * 0.7:
                    yield f"Turn {turn}: {heal(p1_ball)}"
                    continue

                event = random_events(p1_ball, p2_ball)
                if event[0]:
                    yield f"Turn {turn}: {event[1]}"
                    continue

                yield f"Turn {turn}: {attack(p1_ball, battle.p2_balls)}"

                if all(ball.dead for ball in battle.p2_balls):
                    break

            if not p2_ball.dead:
                turn += 1

                if random.randint(1, 100) <= 20 and p2_ball.health < p2_ball.max_health * 0.7:
                    yield f"Turn {turn}: {heal(p2_ball)}"
                    continue

                event = random_events(p2_ball, p1_ball)
                if event[0]:
                    yield f"Turn {turn}: {event[1]}"
                    continue

                yield f"Turn {turn}: {attack(p2_ball, battle.p1_balls)}"

                if all(ball.dead for ball in battle.p1_balls):
                    break

    if all(ball.dead for ball in battle.p1_balls):
        battle.winner = battle.p2_balls[0].owner
    elif all(ball.dead for ball in battle.p2_balls):
        battle.winner = battle.p1_balls[0].owner

    battle.turns = turn
