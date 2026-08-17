"""Pipeline defaults. DEFAULT_CHUNKING_STRATEGY / DEFAULT_EMBEDDING_MODEL are
set from Part 2's measured winner (see run_model_strategy_grid.py and
data/part2_model_strategy_grid.json) -- this is the "hard-code the winning
combination as the pipeline default for all subsequent Q1 weeks" task.
Do not hand-edit these without re-running the benchmark; if you change the
corpus or query set, re-run Part 2 and update both constants + WINNER_NOTE
together so they can't drift out of sync.
"""

# Placeholder until Part 2 finishes -- run_model_strategy_grid.py overwrites
# this file's two constants below via update_defaults().
DEFAULT_CHUNKING_STRATEGY = "recursive"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
WINNER_NOTE = "placeholder -- not yet set from a benchmark run"
