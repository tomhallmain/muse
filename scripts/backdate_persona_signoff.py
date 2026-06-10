"""Backdate the last_hello_time and last_signoff_time of today's scheduled DJ
persona (or a named one) so that the intro logic triggers on the next run.

determine_intro_type fires IntroType.INTRO when both times are > 6 hours old,
so this script sets them to --hours ago (default 7).

Usage:
    python scripts/backdate_persona_signoff.py
    python scripts/backdate_persona_signoff.py --voice "Ludvig Milivoj"
    python scripts/backdate_persona_signoff.py --hours 12
    python scripts/backdate_persona_signoff.py --clear   # set both to None
"""

import argparse
import os
import pickle
import time
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(script_dir)
os.chdir(root_dir)

from muse.schedules_manager import SchedulesManager
from utils.cache_paths import resolve_cache_file


def get_scheduled_voice() -> str:
    SchedulesManager.set_schedules()
    active = SchedulesManager.get_active_schedule(datetime.now())
    return active.voice


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--voice", help="Voice name of the persona to update (default: today's scheduled DJ)")
    parser.add_argument("--hours", type=float, default=7.0,
                        help="How many hours back to set the times (default: 7, must be >6 to trigger INTRO)")
    parser.add_argument("--clear", action="store_true",
                        help="Set both times to None instead of backdating (also triggers INTRO)")
    args = parser.parse_args()

    memory_path = resolve_cache_file("muse_memory")
    if not os.path.exists(memory_path):
        print(f"Memory file not found: {memory_path}")
        print("Start the app once to create it, then run this script.")
        return

    voice_name = args.voice or get_scheduled_voice()
    print(f"Target voice: {voice_name}")

    with open(memory_path, "rb") as f:
        memory = pickle.load(f)

    persona_manager = memory.persona_manager
    if persona_manager is None:
        print("No persona manager found in memory.")
        return

    persona = persona_manager.personas.get(voice_name)
    if persona is None:
        available = list(persona_manager.personas.keys())
        print(f"Persona '{voice_name}' not found in memory.")
        print(f"Available personas: {available}")
        return

    if args.clear:
        persona.last_hello_time = None
        persona.last_signoff_time = None
        print(f"Cleared last_hello_time and last_signoff_time for '{persona.name}'.")
    else:
        backdate_to = time.time() - args.hours * 3600
        backdate_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(backdate_to))
        persona.last_hello_time = backdate_to
        persona.last_signoff_time = backdate_to
        print(f"Set last_hello_time and last_signoff_time for '{persona.name}' to {backdate_str} ({args.hours}h ago).")

    with open(memory_path, "wb") as f:
        pickle.dump(memory, f)

    print("Memory saved.")


if __name__ == "__main__":
    main()
