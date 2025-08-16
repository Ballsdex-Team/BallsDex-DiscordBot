from dataclasses import dataclass, field
import random


@dataclass
class BattleBall:
    name: str
    owner: str
    health: int
    attack: int
    emoji: str = ""
    dead: bool = False


@dataclass
class BattleInstance:
    p1_balls: list = field(default_factory=list)
    p2_balls: list = field(default_factory=list)
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
