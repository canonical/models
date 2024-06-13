#!/usr/bin/python3

import os
import re
import json
import requests
import subprocess

from functools import lru_cache

SEED_BASE_URL = "https://ubuntu-archive-team.ubuntu.com/seeds/ubuntu.%s/%s"
MODEL_ASSERTION_JSON = "ubuntu-classic-%s-%s.json"


def get_seed_url(release, seed):
    return SEED_BASE_URL % (release, seed)

def fetch_snaps_from_seed(release, seed, seeded_snaps):
    url = get_seed_url(release, seed)
    response = requests.get(url)
    if response.status_code != 200:
        print("Failed to fetch seed %s" % seed)
        return
    for line in response.text.splitlines():
        line_stripped = line.strip()
        # TODO: This would be better and safer done as a regex.
        if line_stripped.startswith("* snap:"):
            # We can do this as we already make sure that the string starts
            # with only one whitespace.
            seeded_snaps.add(line_stripped[7:].split(" ")[0])

def add_implicitly_seeded_snaps(release, seeded_snaps):
    # Sometimes some snaps are implicitly seeded in the images. Let's add
    # them to the list.
    implicit = {"noble": {"snapd", "bare", "core22"}}
    seeded_snaps.update(implicit.get(release, set()))

def get_latest_series():
    return subprocess.check_output(
        ["distro-info", "--devel"]).decode().strip()

@lru_cache
def get_series_version(release):
    return subprocess.check_output(
        ["distro-info", "--series", release, "-r"]
        ).decode().strip().removesuffix(" LTS")

@lru_cache
def get_model_assertion_name(release, arch="amd64"):
    series = get_series_version(release)
    series = series.split(" ")[0].replace(".", "")
    return MODEL_ASSERTION_JSON % (series, arch)

def fetch_model_assertion(release, repository=".", arch="amd64"):
    model_assertion = get_model_assertion_name(release, arch)
    # Load the model assertion json.
    with open(os.path.join(repository, model_assertion), "r") as f:
        model = json.load(f)
    return model

def save_model_assertion(model, release, repository, arch):
    name = get_model_assertion_name(release, arch)
    with open(os.path.join(repository, name), "w") as f:
        json.dump(model, f, indent=4)
        # We like the final newline.
        f.write("\n")

def fetch_snaps_from_model_assertion(model):
    snaps = set()
    for snap in model["snaps"]:
        snaps.add(snap["name"])
    return snaps

def get_snap_info(snap):
    headers = {"Snap-Device-Series": "16"}
    result_json = requests.get(
        "https://api.snapcraft.io/v2/snaps/info/%s" % snap,
        headers=headers).json()
    if "error-list" in result_json:
        print("Snap %s not found" % snap)
        return None
    return result_json

def is_in_sync_exclude_list(snap, info=None):
    # We don't want to sync gadgets and kernels.
    if not info:
        info = get_snap_info(snap)
    if info:
        snap_type = info["channel-map"][0]["type"]
        if snap_type in ("gadget", "kernel"):
            return True
    return False

def remove_snaps_from_model_assertion(model, snaps):
    for snap in model["snaps"]:
        if (snap["name"] in snaps and
                not is_in_sync_exclude_list(snap["name"])):
            model["snaps"].remove(snap)

def add_snaps_to_model_assertion(model, snaps, release):
    series = get_series_version(release)
    core_regex = re.compile(r"^core(\d\d)?$")
    for snap in snaps:
        entry = {
            "name": snap,
            "type": "app",
            "default-channel": "latest/stable/ubuntu-%s" % series,
            "id": None,
        }
        snap_info = get_snap_info(snap)
        if is_in_sync_exclude_list(snap, snap_info):
            continue
        entry["id"] = snap_info["snap-id"]
        if core_regex.match(snap) or snap == "bare":
            entry["type"] = "base"
            entry["default-channel"] = "latest/stable"
        model["snaps"].append(entry)
        

def check_snap_seeds(release, repository=".", arch="amd64", dry_run=False):
    seeds = ["minimal", "desktop-minimal"]
    seeded_snaps = set()
    model_snaps = set()
    changed = False
    model = fetch_model_assertion(release, repository)
    for seed in seeds:
        fetch_snaps_from_seed(release, seed, seeded_snaps)
    # Some snaps don't apprear in the seeds. Most of the time this needs
    # fixing in the seeds repository.
    add_implicitly_seeded_snaps(release, seeded_snaps)
    # Now snaps contains all the snaps in the seeds. Let's compare it with
    # the model assertion snap list.
    model_snaps = fetch_snaps_from_model_assertion(model)
    # Now we have the list of snaps in the model assertion. Let's compare it
    # with the seeded snaps.
    added_snaps = seeded_snaps - model_snaps
    removed_snaps = model_snaps - seeded_snaps
    # Now, exclude those snaps that are on the exclude list.
    # As there are snaps that we don't actually want to sync automatically.
    added_snaps = {s for s in added_snaps if not is_in_sync_exclude_list(s)}
    removed_snaps = \
        {s for s in removed_snaps if not is_in_sync_exclude_list(s)}
    if removed_snaps:
        print("Removed snaps: %s" % ", ".join(removed_snaps))
        remove_snaps_from_model_assertion(model, removed_snaps)
        changed = True
    if added_snaps:
        print("Added snaps: %s" % ", ".join(added_snaps))
        add_snaps_to_model_assertion(model, added_snaps, release)
        changed = True
    if changed and not dry_run:
        print("Saving updated model assertion")
        save_model_assertion(model, release, repository, arch)
    return changed