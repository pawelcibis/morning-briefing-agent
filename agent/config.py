import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def load_config() -> dict:
    """
    Load config.yaml and inline each workout's clothing bands.

    After this call, cfg["workouts"]["cycling"]["clothing_bands"] is a list
    of band dicts (max_c, dry, wet) loaded from cycling_clothing.yaml.
    The YAML file path stays in config.yaml; the content lives in memory.
    """
    with open(REPO_ROOT / "config.yaml") as f:
        cfg = yaml.safe_load(f)

    for workout_name, workout_cfg in cfg.get("workouts", {}).items():
        table_file = workout_cfg.get("clothing_table")
        if not table_file:
            continue
        table_path = REPO_ROOT / table_file
        if not table_path.exists():
            continue
        # Load THIS workout's own clothing table, anchored at REPO_ROOT so it
        # works regardless of the process's current working directory.
        with open(table_path, encoding="utf-8") as f:
            workout_cfg["clothing_bands"] = yaml.safe_load(f)["bands"]
    return cfg