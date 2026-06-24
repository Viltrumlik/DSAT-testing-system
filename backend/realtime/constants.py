"""Realtime delivery hints — not domain truth."""

PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"

PRIORITY_CHOICES = [
    (PRIORITY_HIGH, "High"),
    (PRIORITY_MEDIUM, "Medium"),
    (PRIORITY_LOW, "Low"),
]

# Dedupe applies only to medium/low. High is never suppressed by dedupe window.
# Fine-grained keys use payload fields; high-priority rows use empty dedupe_key.
