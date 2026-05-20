from datetime import date, timedelta

from agent.config import load_config
from agent.blocks.cycling import build_cycling_block
from agent.render import render_cycling_block


def main():
    cfg = load_config()

    # Evening run always prepares tomorrow's forecast
    tomorrow = date.today() + timedelta(days=1)
    print(f"Fetching cycling forecast for {tomorrow} …\n")

    block = build_cycling_block(cfg, tomorrow)
    print(render_cycling_block(block))


if __name__ == "__main__":
    main()