#!/usr/bin/env python3
"""Run the vendor XMODEM sender with Windows-safe UTF-8 console output."""
import argparse
import os
import pathlib
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sender", required=True, type=pathlib.Path)
    parser.add_argument("--image", required=True, type=pathlib.Path)
    parser.add_argument("--port", default="COM5")
    parser.add_argument("--baudrate", default="921600")
    args = parser.parse_args()
    sender = args.sender.resolve()
    image = args.image.resolve()
    if not sender.is_file():
        raise SystemExit(f"Vendor XMODEM sender not found: {sender}")
    if not image.is_file():
        raise SystemExit(f"Firmware image not found: {image}")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [
            sys.executable,
            str(sender),
            f"--port={args.port}",
            f"--baudrate={args.baudrate}",
            "--protocol=xmodem",
            "--timeout=5",
            f"--file={image}",
        ],
        env=env,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
