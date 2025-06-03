# How rarity works

Rarity works differently for ball spawning and specials, but in general a higher number means more likely to happen, and 0 means disabled. Negative numbers are undefined behavior.

## Countryball spawning rarity

The ball rarity is independent from the spawn algorithm's logic, meaning that a ball will spawn when it has to, even if you only have balls with a rarity of 0.00001. In reality, the rarity depends on the other balls you have in your bot. To better illustrate how this work, look at the different situations:

### With one countryball

When you have a single countryball with a rarity higher than 0, then no matter what that rarity is, it will always spawn.
![image](https://github.com/user-attachments/assets/6087e643-2383-4b9d-8762-3248247c3644)

### With two countryballs

Now let's add Germany with a rarity of 0.4:
![image](https://github.com/user-attachments/assets/dad3a42a-127b-479b-8508-c4e16c361fc8)

Germany has 2/3 chances of spawning, and France has 1/3 chance of spawning. What's interesting is that you will have the exact same result if you change the numbers proportionally:
![image](https://github.com/user-attachments/assets/5a30ed5a-0f59-4e30-8404-adb73fcf88e6)

I doubled the rarity of both countries, yet they still exactly have the same odds of spawning. At this point you're starting to get how this works. The general probability for a countryball is this:  
$$
P = \dfrac{\text{ball rarity}}{\sum\text{rarities}}
$$

### With more countryballs

Finally, let's add Italy with a rarity of 0.2:
![image](https://github.com/user-attachments/assets/65116811-684d-4ffa-8b25-a0403005936b)

Italy now can spawn, but in reality, it decreased Germany and France's probability of spawning to 4/7 and 3/7 respectively, Italy taking that final 1/7.

## Special rarity

Specials are a bit similar to the system above, but while taking into account the existence of the "common" state, aka when no special should be assigned.

!!! warning
    Unlike countryballs that allow any rarity above 0, it is important that specials have a rarity between 0 and 1. Going outside this range will most likely result in errors.

### With one special

When you decide the rarity of your special event, you are deciding the percentage of chances it has to appear against the common state.

- If your rarity is **0**, the special has **0%** chances of appearing, all balls will be common
- If your rarity is **1**, the special has **100%** chances of appearing, completely disabling commons
- If your rarity is **0.4**, the special has **40%** chances of appearing, the other 60% will be common

### With two or more specials

Things get more interesting if you have multiple active specials at once. The logic above is applied, but then they are "blended" together, with the common state accumulating odds from other specials.

Let's imagine we have one special "Birthday" with a rarity of 0.4:
![image](https://github.com/user-attachments/assets/da141a52-9c3a-4d16-84ca-a1d39279e05d)

Now we want to add another special "Winter" with a rarity of 0.6:
![image](https://github.com/user-attachments/assets/259e2786-af26-4184-8192-1027acb2f304)

Now there is 50% chances of spawning a common, and 50% chances of spawning a special. If it's a special, 40% chances of being "Birthday" and 60% chances of being "Winter".

Let's add a third event "Chinese New Year" with a rarity of 0.2:
![image](https://github.com/user-attachments/assets/eec19583-dcd7-4cac-aae5-7a806d8634b8)

This time, it reduced the odd of getting any kind of special at all, with balls now having 60% chances of being "common" and 40% chances of being special.

The way you can see this is this:
- We get the opposite odd (having a common) of every special and make the average of that: $\dfrac{\frac{3}{5}+\frac{2}{5}+\frac{4}{5}}{3}=\dfrac{3}{5}$
- The opposite of that ($\frac{2}{5}$) is then shared to the specials, which follow the same rule as ball spawning
