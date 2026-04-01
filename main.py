#!/usr/bin/env python3
"""linux_flow — Wispr Flow alternative for Linux.

Usage:
  python main.py              # launch the app (tray + settings window)
  python main.py --list-mics  # list available microphones and exit
"""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="linux_flow — voice dictation for Linux"
    )
    parser.add_argument(
        "--list-mics", action="store_true", help="List available microphones"
    )
    args = parser.parse_args()

    if args.list_mics:
        from core.recorder import Recorder

        print("\nAvailable microphones:")
        for dev in Recorder.list_devices():
            print(
                f"  [{dev['index']}] {dev['name']} ({dev['channels']}ch, {dev['sample_rate']}Hz)"
            )
        print("\nSet 'audio.device_index' in linux_flow.toml to pick one.")
        sys.exit(0)

    from ui.app import LinuxFlowApp

    app = LinuxFlowApp()
    try:
        sys.exit(app.run(sys.argv[:1]))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
