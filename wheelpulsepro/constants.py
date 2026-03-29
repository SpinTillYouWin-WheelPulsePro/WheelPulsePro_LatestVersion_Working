"""WheelPulsePro – HUD visibility constants.

Single source of truth for the HUD card checkbox defaults used in both
the DE2D tracker and the strategy-cards area.
"""

# Cards shown on fresh load.  (Sniper Strike, Cold Trinity, Ramp/Grind/X-19
# and Non-Repeaters are hidden by default so users must explicitly opt-in to
# those noisy/advanced cards.)
_HUD_DEFAULT_VISIBLE = [
    "Missing Dozen/Col",
    "Even Money Drought", "Trend Reversal", "Streak Attack", "Pattern Match",
    "Voisins/Tiers", "Left/Right Sides", "5DS/Corners/D17", "Zero Guard",
]

# Every available card (used by the "Check All" button).
_HUD_ALL_CHOICES = [
    "Sniper Strike", "Ramp/Grind/X-19", "Cold Trinity", "Missing Dozen/Col",
    "Even Money Drought", "Trend Reversal", "Streak Attack", "Pattern Match",
    "Voisins/Tiers", "Left/Right Sides", "5DS/Corners/D17", "Zero Guard", "Non-Repeaters",
]
