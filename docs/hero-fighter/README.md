# The Soulforger

The Soulforger is the named Fighter hero. The stable spawn and save variant remains
`hero_fighter`; the canonical implementation is
`dungeons_desktops.game.heroes.hero_fighter.HeroFighter`.

He shares the ordinary Fighter's skeleton, proportions, helmet, gait, navigation,
climbing, interruption, and terrain recovery. His body uses 5-pixel lines beneath
fitted full plate, and he carries a held divine-silver trident and full shield. He
has 60 HP, normal Fighter movement speed, 38-pixel melee reach, a 0.8-second basic
attack cadence, and immunity to Mind Flayer stun.

When standard Fighter targeting first finds an enemy, a 0.25-second gesture places
a visible Death Mark. The mark remains until that enemy dies or leaves the world.
The Soulforger prioritizes it, moves at twice normal speed while pursuing it, and
adds 1 damage to every hit against it. After the target disappears, another enemy
can be marked after two seconds.

- **Spectral Trident Throw:** an 8-second cooldown, 0.35-second windup, and
  90-to-360-pixel range. The spectral copy pierces enemies once each for 4 damage,
  or 5 against the mark; the physical trident stays in his hand. Inside that
  minimum range he closes for melee instead of throwing at point-blank range.
- **Combat Leap:** a 10-second cooldown ground hop used within 160 pixels on the
  same clear walkable surface. The arc ignores the desktop's ceiling boundary but
  still respects solid windows. He lands about 30 pixels away and performs six
  alternating trident-and-shield hits over 0.8 seconds for 2 marked damage each.
  The trident strikes mix broad slashes with direct stabs. He stays at the landing
  point, so a moving target can make later hits miss.
- **Spectral Shield Retaliation:** after accepted nonfatal damage, a spectral
  shield can strike the marked target within 50 pixels for 3 total damage and
  knockback. It has a 4-second cooldown and does not interrupt his current attack.
- **Trident melee:** when no special is valid, consecutive attacks alternate
  between a broad slash and a direct stab. Each deals 1 damage, or 2 to the marked
  enemy.

Released spectral projectiles resolve independently. Unreleased actions cancel on
death, enthrallment, lure, reel, engulfment, terrain interruption, or ordinary
stuns.
