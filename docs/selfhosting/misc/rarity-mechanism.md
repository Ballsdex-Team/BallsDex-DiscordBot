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

Specials are a bit similar to the system above

!!! warning
    Unlike countryballs that allow any rarity above 0, it is important that specials have a rarity between 0 and 1. Going outside this range will most likely result in strange behavior.

Special rarity has changed as of 2.27.0, and is now simpler than it was before.

Set each special rarity to the rarity that you want it to have. Eg, if you want a special to have a 20% chance of spawning, set its rarity to 0.2. If you want it to have a 1% chance of spawning, set its rarity to 0.01.

If the special rarities sum to 1 or over 1, then commons will not spawn. Also, rarities will be "squashed" down to 100%, so if you have a Special A with a rarity set as 2, and Special B set as 3, then Special A will have a 2/5 chance of spawning (40%), Special B will have a 60% chance of spawning (60%), and commons will have a 0% chance of spawning (since the rarities sum to over one)
