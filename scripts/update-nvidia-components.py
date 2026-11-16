#!/usr/bin/env python3

"""For a given model, update the pc-kernel definition so that the latest
available desktop nvidia components are listed."""

import argparse
import contextlib
import collections
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
import datetime as dt

import yaml


def current_nvidia_components(candidates) -> list[str]:
    """Return the UDA Nvidia components having the highest version"""
    by_version = collections.defaultdict(list)
    for component in candidates:
        match = re.fullmatch(r"nvidia-(\d+)-uda-(user|ko)", component)
        if not match:
            continue
        version = int(match.group(1))
        by_version[version].append(match.group(0))

    highest_version = sorted(by_version.keys())[-1]

    return by_version[highest_version]


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
            "model", type=Path,
            help="Path to the model to use (the JSON, not the signed YAML)")
    parser.add_argument(
            "--overwrite", action="store_true",
            help="Update the model in place, rather than printing to stdout")

    args = parser.parse_args()

    with args.model.open(encoding="utf-8") as fh:
        data = json.load(fh)

    snaps = data["snaps"]

    for snap in snaps:
        if snap["name"] == "pc-kernel":
            break
    else:
        raise ValueError("there is no pc-kernel snap in the model")

    with tempfile.TemporaryDirectory(delete=True) as tdir:
        subprocess.check_call([
                "snap", "download", "pc-kernel",
                "--channel", snap["default-channel"],
                "--target-directory", tdir,
            ])

        # We need to find the snap that was just downloaded
        # The directory is new so there should only be one
        [kernel_snap] = Path(tdir).glob("pc-kernel*.snap")

        snap_yaml = subprocess.check_output(["unsquashfs", "-cat", kernel_snap, "meta/snap.yaml"])

    snap_definition = yaml.safe_load(snap_yaml)

    # Tells if anything has changed.
    updated = False

    components_names = current_nvidia_components(set(snap_definition["components"].keys()))
    components = {name: {"presence": "optional"} for name in sorted(components_names)}

    if components != snap["components"]:
        snap["components"] = components
        updated = True

    if updated:
        data["timestamp"] = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.0Z")

    if args.overwrite:
        output_cm = args.model.open(mode="w", encoding="utf-8")
    else:
        output_cm = contextlib.nullcontext(enter_result=sys.stdout)

    with output_cm as output:
        print(json.dumps(data, indent=4), file=output)


if __name__ == "__main__":
    main()
