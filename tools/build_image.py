#!/usr/bin/env python3
"""Build a signed Grove Vision AI V2 image from the SDK's compiled ELF."""
import argparse
import hashlib
import os
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
ELF_REL = pathlib.Path(
    "EPII_CM55M_APP_S/obj_epii_evb_icv30_bdv10/gnu_epii_evb_WLCSP65/"
    "EPII_CM55M_gnu_epii_evb_WLCSP65_s.elf"
)
IMAGE_REL = pathlib.Path("we2_image_gen_local/output_case1_sec_wlcsp/output.img")
INPUT_REL = pathlib.Path(
    "we2_image_gen_local/input_case1_secboot/"
    "EPII_CM55M_gnu_epii_evb_WLCSP65_s.elf"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk", type=pathlib.Path, default=ROOT / "vendor/himax-grove-sdk")
    args = parser.parse_args()
    sdk = args.sdk.resolve()
    elf = sdk / ELF_REL
    if not elf.is_file():
        raise SystemExit(f"Firmware ELF not found: {elf}. Build it first.")

    generator_dir = sdk / "we2_image_gen_local"
    generator = generator_dir / ("we2_local_image_gen.exe" if os.name == "nt" else "we2_local_image_gen")
    if not generator.is_file():
        raise SystemExit(f"Vendor image generator not found: {generator}")

    image = sdk / IMAGE_REL
    image.unlink(missing_ok=True)
    shutil.copy2(elf, sdk / INPUT_REL)
    subprocess.run(
        [str(generator), "project_case1_blp_wlcsp.json"],
        cwd=generator_dir,
        check=True,
    )
    if not image.is_file():
        raise SystemExit(f"Image generator did not create {image}")
    size = image.stat().st_size
    if not 0 < size <= 1024 * 1024:
        raise SystemExit(f"Firmware image has unexpected size: {size} bytes")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    print(f"Firmware image: {image}")
    print(f"Size: {size} bytes")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    main()
