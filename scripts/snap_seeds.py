#!/usr/bin/python3

import os
import re
import json
import requests
import subprocess

from functools import lru_cache

SEED_BASE_URL = "https://ubuntu-archive-team.ubuntu.com/seeds/ubuntu.%s/%s"
MODEL_ASSERTION_JSON = "ubuntu-classic-%s-%s%s.json"


core_regex = re.compile(r"^core(\d\d)?$")


class SeededSnap:
    def __init__(self, series, name, track, channel, branch, is_classic=False):
        self.name = name
        self.track = track if track else "latest"
        self.channel = channel if channel else "stable"
        # If the branch is not set, we default to the series. But if the
        # branch is empty "", we keep it as empty.
        self.branch = branch if branch != None else "ubuntu-%s" % series
        self.is_classic = is_classic
        if (not track and not branch and core_regex.match(name) or
                name in ("bare", "snapd")):
            self.branch = None

    @classmethod
    def from_seed_line(cls, series, line):
        # The format of the seed line is: "name/classic=track/channel/branch"
        # But all elements besides the name are optional.
        # The name is mandatory.
        snap_regex = re.compile(
            r"\s*(?P<name>[a-zA-Z0-9_\-.]+)"
            r"(?:/(?P<classic>classic))?"
            r"(?:=(?:(?P<track>[a-zA-Z0-9_\-.]+))"
            r"(?:/(?P<channel>[a-zA-Z0-9_\-.]+))"
            r"(?:/(?P<branch>[a-zA-Z0-9_\-.]+))?)?")
        match = snap_regex.match(line)
        if not match:
            print("Failed to extract snap data from line: %s" % line)
            return None
        snap_data = match.groupdict()
        if snap_data["channel"] and not snap_data["branch"]:
            # A special case, since the branch is optional, so in that case
            # we do not want to go with the 'defaults', but use no branch
            # instead.
            snap_data["branch"] = ""
        return cls(
            series,
            snap_data["name"],
            snap_data["track"],
            snap_data["channel"],
            snap_data["branch"],
            snap_data["classic"] is not None)

    def snap_default_channel(self):
        return "%s/%s%s" % (
            self.track, self.channel,
            ("/%s" % self.branch) if self.branch else "")

    def seed_format(self):
        return "%s%s=%s" % (
            self.name,
            "/classic" if self.is_classic else "",
            self.snap_default_channel())

    def __str__(self):
        return "%s (%s)" % (
            self.name, self.snap_default_channel())

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        if not isinstance(other, SeededSnap):
            return False
        return self.seed_format() == other.seed_format()

    def __hash__(self):
        return hash(self.seed_format())


def get_seed_url(release, seed):
    return SEED_BASE_URL % (release, seed)

def fetch_snaps_from_seed(release, seed, seeded_snaps):
    series = get_series_version(release)
    url = get_seed_url(release, seed)
    response = requests.get(url)
    if response.status_code != 200:
        print("Failed to fetch seed %s" % seed)
        return
    for line in response.text.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith("* snap:"):
            # We can do this as we already make sure that the string starts
            # with only one whitespace.
            snap = SeededSnap.from_seed_line(series, line_stripped[7:])
            if snap:
                seeded_snaps.add(snap)

def add_implicitly_seeded_snaps(release, seeded_snaps):
    # Sometimes some snaps are implicitly seeded in the images. Let's add
    # them to the list.
    implicit = {"oracular": {"snapd", "bare", "core22", "core24"},
                "noble":    {"snapd", "bare", "core22"},
                "mantic":   {"snapd", "bare", "core22"}}
    series = get_series_version(release)
    for snap in implicit[release]:
        seeded_snaps.add(SeededSnap(series, snap, None, None, None))

def get_supported_model_series():
    all = subprocess.check_output(
        ["distro-info", "--all"]).decode().strip().splitlines()
    supported = set(subprocess.check_output(
        ["distro-info", "--supported"]).decode().strip().splitlines())
    # Get the list of all series from mantic onward.
    mantic_index = all.index("mantic")
    mantic_onward = all[mantic_index:]
    return [s for s in mantic_onward if s in supported]

@lru_cache
def get_series_version(release):
    return subprocess.check_output(
        ["distro-info", "--series", release, "-r"]
        ).decode().strip().removesuffix(" LTS")

@lru_cache
def get_model_assertion_name(release, arch="amd64", dangerous=False):
    series = get_series_version(release)
    series = series.split(" ")[0].replace(".", "")
    return MODEL_ASSERTION_JSON % (
        series, arch, "-dangerous" if dangerous else "")

def fetch_model_assertions(release, repository=".", arch="amd64"):
    model_json = None
    model_json_dangerous = None
    # Main model.
    model_assertion = get_model_assertion_name(release, arch, False)
    if not os.path.exists(os.path.join(repository, model_assertion)):
        print("Model assertion %s for %s not found" % (
            model_assertion, release))
    else:
        # Load the model assertion json.
        with open(os.path.join(repository, model_assertion), "r") as f:
            model_json = json.load(f)
    # Dangerous model.
    model_assertion_dangerous = get_model_assertion_name(release, arch, True)
    if not os.path.exists(os.path.join(
            repository, model_assertion_dangerous)):
        print("Model assertion %s for %s not found" % (
            model_assertion_dangerous, release))
    else:
        # Load the dangerous model assertion json.
        with open(os.path.join(
                repository, model_assertion_dangerous), "r") as f:
            model_json_dangerous = json.load(f)
    return model_json, model_json_dangerous

def save_model_assertion(model, release, repository, arch):
    if not model:
        return
    dangerous = True if "dangerous" in model["grade"] else False
    name = get_model_assertion_name(release, arch, dangerous)
    with open(os.path.join(repository, name), "w") as f:
        json.dump(model, f, indent=4)
        # We like the final newline.
        f.write("\n")

def fetch_snaps_from_model_assertion(release, model):
    series = get_series_version(release)
    snaps = set()
    for snap in model["snaps"]:
        name = snap["name"]
        track = None
        channel = None
        branch = None
        channel_split = snap["default-channel"].split("/")
        if len(channel_split) == 3:
            track, channel, branch = channel_split
        elif len(channel_split) == 2:
            track, channel = channel_split
            branch = ""
        elif len(channel_split) == 1:
            channel = channel_split[0]
        snaps.add(SeededSnap(series, name, track, channel, branch))
    return snaps

def get_snap_info(snap_name):
    headers = {"Snap-Device-Series": "16"}
    result_json = requests.get(
        "https://api.snapcraft.io/v2/snaps/info/%s" % snap_name,
        headers=headers).json()
    if "error-list" in result_json:
        print("Snap %s not found" % snap_name)
        return None
    return result_json

def is_in_sync_exclude_list(snap, info=None):
    # We don't want to sync gadgets and kernels.
    if isinstance(snap, SeededSnap):
        snap = snap.name
    if not info:
        info = get_snap_info(snap)
    if info:
        snap_type = info["channel-map"][0]["type"]
        if snap_type in ("gadget", "kernel"):
            return True
    return False

def remove_snaps_from_model_assertion(model, snaps):
    if not model:
        return
    for snap in model["snaps"]:
        found = False
        for s in snaps:
            if s.name == snap["name"]:
                found = True
                break
        if (found and not is_in_sync_exclude_list(snap["name"])):
            model["snaps"].remove(snap)

def add_snaps_to_model_assertion(model, snaps, release):
    if not model:
        return
    dangerous = True if "dangerous" in model["grade"] else False
    for snap in snaps:
        entry = {
            "name": snap.name,
            "type": "app",
            "default-channel": snap.snap_default_channel(),
            "id": None,
        }
        snap_info = get_snap_info(snap.name)
        if is_in_sync_exclude_list(snap.name, snap_info):
            continue
        entry["id"] = snap_info["snap-id"]
        # If the model is dangerous, we override to edge.
        if dangerous:
            entry["default-channel"] = "latest/edge"
        model["snaps"].append(entry)
        

def check_snap_seeds(release, repository=".", arch="amd64", dry_run=False):
    seeds = ["minimal", "desktop-minimal"]
    seeded_snaps = set()
    model_snaps = set()
    changed = False
    print("Checking updates for %s" % release)
    model, model_dangerous = fetch_model_assertions(release, repository)
    # If the model assertion does not exist yet, skip.
    if not model and not model_dangerous:
        return False
    for seed in seeds:
        fetch_snaps_from_seed(release, seed, seeded_snaps)
    # Some snaps don't apprear in the seeds. Most of the time this needs
    # fixing in the seeds repository.
    add_implicitly_seeded_snaps(release, seeded_snaps)
    # Now snaps contains all the snaps in the seeds. Let's compare it with
    # the model assertion snap list.
    model_snaps = fetch_snaps_from_model_assertion(
        release,
        model if model else model_dangerous)
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
        print("Removed snaps: %s" % ", ".join(
            [str(s) for s in removed_snaps]))
        remove_snaps_from_model_assertion(model, removed_snaps)
        remove_snaps_from_model_assertion(model_dangerous, removed_snaps)
        changed = True
    if added_snaps:
        print("Added snaps: %s" % ", ".join(
            [str(s) for s in added_snaps]))
        add_snaps_to_model_assertion(model, added_snaps, release)
        add_snaps_to_model_assertion(model_dangerous, added_snaps, release)
        changed = True
    if changed and not dry_run:
        print("Saving updated model assertion(s)")
        save_model_assertion(model, release, repository, arch)
        save_model_assertion(model_dangerous, release, repository, arch)
    return changed
