# tier_config.py

# Tier Table: (min_pop, max_pop, min_jaccard_threshold, min_size_ratio)
POPULATION_TIER_CONFIG = [
    (1, 3, 0.65, 0.65),
    (4, 8, 0.74, 0.74),
    (9, 14, 0.82, 0.82),
    (15, 20, 0.85, 0.85),
    (21, 30, 0.87, 0.87),
    (31, 50, 0.89, 0.89),
    (51, 75, 0.91, 0.91),
    (76, 100, 0.93, 0.93),
    (101, 150, 0.94, 0.94),
    (151, 225, 0.95, 0.95),
    (226, 300, 0.96, 0.96),
    (301, float("inf"), 0.97, 0.97),
]


def get_tier_parameters(pop_size):
  """Returns (min_jaccard_threshold, min_size_ratio) based on population size."""
  for min_p, max_p, threshold, ratio in POPULATION_TIER_CONFIG:
    if min_p <= pop_size <= max_p:
      return threshold, ratio
  return 0.75, 0.75  # Fallback default
