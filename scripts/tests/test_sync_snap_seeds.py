#!/usr/bin/python3

import unittest
import json

from unittest.mock import patch

from snap_seeds import (
    SeededSnap, fetch_model_assertions, fetch_snaps_from_model_assertion,
    fetch_snaps_from_seed, add_snaps_to_model_assertion,
    get_supported_model_series)


def mock_get_snap_info(snap):
    if snap.endswith("-kernel"):
        return {"channel-map": [{"type": "kernel"}], "snap-id": "1234"}
    elif snap in ("pc", "pi"):
        return {"channel-map": [{"type": "gadget"}], "snap-id": "1234"}
    else:
        return {"channel-map": [{"type": "app"}], "snap-id": "1234"}


class TestSeededSnap(unittest.TestCase):
    def test_seeded_snap(self):
        seeded_snap = SeededSnap("24.04", "snap", "track",
                                 "channel", "branch", True)
        self.assertEqual(seeded_snap.name, "snap")
        self.assertEqual(seeded_snap.track, "track")
        self.assertEqual(seeded_snap.channel, "channel")
        self.assertEqual(seeded_snap.branch, "branch")
        self.assertTrue(seeded_snap.is_classic)

    def test_seeded_snap_defaults(self):
        seeded_snap = SeededSnap("24.04", "snap", None, None, None)
        self.assertEqual(seeded_snap.name, "snap")
        self.assertEqual(seeded_snap.track, "latest")
        self.assertEqual(seeded_snap.channel, "stable")
        self.assertEqual(seeded_snap.branch, "ubuntu-24.04")
        self.assertFalse(seeded_snap.is_classic)

    def test_seeded_snap_core(self):
        seeded_snap = SeededSnap("24.04", "core24", None, None, None)
        self.assertEqual(seeded_snap.name, "core24")
        self.assertEqual(seeded_snap.track, "latest")
        self.assertEqual(seeded_snap.channel, "stable")
        self.assertEqual(seeded_snap.branch, None)
        self.assertFalse(seeded_snap.is_classic)

    def test_seeded_snap_from_seed(self):
        seed_lines = {
            "snap/classic=track/channel/branch":
                ("snap", "track", "channel", "branch", True),
            "snap=track/channel/branch":
                ("snap", "track", "channel", "branch", False),
            "snap/classic=track/channel":
                ("snap", "track", "channel", "", True),
            "snap":
                ("snap", "latest", "stable", "ubuntu-24.04", False),
        }
        for line, expected in seed_lines.items():
            seeded_snap = SeededSnap.from_seed_line("24.04", line)
            self.assertEqual(seeded_snap.name, expected[0])
            self.assertEqual(seeded_snap.track, expected[1])
            self.assertEqual(seeded_snap.channel, expected[2])
            self.assertEqual(seeded_snap.branch, expected[3])
            self.assertEqual(seeded_snap.is_classic, expected[4])

    def test_seeded_snap_default_channel(self):
        seeded_snap = SeededSnap("24.04", "snap", "track", "channel", "branch", True)
        self.assertEqual(seeded_snap.snap_default_channel(), "track/channel/branch")
        seeded_snap = SeededSnap("24.04", "snap", "track", "channel", None)
        self.assertEqual(seeded_snap.snap_default_channel(), "track/channel/ubuntu-24.04")
        seeded_snap = SeededSnap("24.04", "snap", "track", "channel", "")
        self.assertEqual(seeded_snap.snap_default_channel(), "track/channel")


class TestSnapSeeds(unittest.TestCase):
    def test_fetch_model_assertion_no_model(self):
        # No assertions found.
        model, model_dangerous = fetch_model_assertions(
            "xenial", "tests/testdata/", "amd64")
        self.assertIsNone(model)
        self.assertIsNone(model_dangerous)
        # Only normal assertion found.
        model, model_dangerous = fetch_model_assertions(
            "mantic", "tests/testdata/", "amd64")
        self.assertIsNotNone(model)
        self.assertIsNone(model_dangerous)

    @patch('snap_seeds.requests.get')
    def test_fetch_snaps_from_seed(self, mock_get):
        # Mocking the response
        with open("tests/testdata/desktop-minimal-seed-example") as f:
            mock_get.return_value.text = f.read()
        mock_get.return_value.status_code = 200
        # Calling the function under test
        seeded_snaps = set()
        fetch_snaps_from_seed("noble", "desktop-minimal", seeded_snaps)
        # Asserting the expected result
        expected = set((
            SeededSnap("24.04", "gtk-common-themes", "latest", "stable", "ubuntu-24.04", False),
            SeededSnap("24.04", "snap-store", "2", "stable", "ubuntu-24.04", False),
            SeededSnap("24.04", "firmware-updater", "1", "stable", "ubuntu-24.04", False),
            SeededSnap("24.04", "snapd-desktop-integration", "latest", "stable", "ubuntu-24.04", False),
            SeededSnap("24.04", "firefox", "latest", "stable", "ubuntu-24.04", False),
            SeededSnap("24.04", "gnome-42-2204", "latest", "stable", "ubuntu-24.04", False),
            SeededSnap("24.04", "subiquity", "latest", "stable", "ubuntu-24.04", True),
        ))
        self.assertSetEqual(seeded_snaps, expected)
        
    def test_fetch_snaps_from_model_assertion(self):
        """This tests both the fetching and parsing of the model assertion."""
        model, _ = fetch_model_assertions(
            "noble", "tests/testdata/", "amd64")
        snaps = fetch_snaps_from_model_assertion("noble", model)
        expected = set((
            SeededSnap("24.04", "gtk-common-themes", "latest", "stable", "ubuntu-24.04", False),
            SeededSnap("24.04", "snap-store", "latest", "stable", "ubuntu-24.04", False),
            SeededSnap("24.04", "firmware-updater", "latest", "stable", "ubuntu-24.04", False),
            SeededSnap("24.04", "snapd-desktop-integration", "latest", "stable", "ubuntu-24.04", False),
            SeededSnap("24.04", "firefox", "latest", "stable", "ubuntu-24.04", False),
            SeededSnap("24.04", "gnome-42-2204", "latest", "stable", "ubuntu-24.04", False),
            SeededSnap("24.04", "pc-kernel", "24", "stable", "", False),
            SeededSnap("24.04", "pc", "classic-24.04", "stable", "", False),
            SeededSnap("24.04", "bare", "latest", "stable", "", False),
            SeededSnap("24.04", "snapd", "latest", "stable", "", False),
            SeededSnap("24.04", "core22", "latest", "stable", "", False),
        ))
        self.assertSetEqual(snaps, expected)

    @patch('snap_seeds.get_snap_info', side_effect=mock_get_snap_info)
    def test_add_snaps_to_model_assertion(self, mock_get):
        model, _ = fetch_model_assertions(
            "noble", "tests/testdata/", "amd64")
        snaps = set((
            SeededSnap("24.04", "hello", "latest", "stable", "ubuntu-24.04", False),
            SeededSnap("24.04", "pi-kernel", "24", "stable", "", False),
        ))
        add_snaps_to_model_assertion(model, snaps, "noble")
        with open("tests/testdata/ubuntu-classic-2404-amd64-new.json") as f:
            new_model = json.load(f)
        self.assertDictEqual(model, new_model)
    
    @patch('snap_seeds.get_snap_info', side_effect=mock_get_snap_info)
    def test_add_snaps_to_model_assertion_dangerous(self, mock_get):
        _, model_dangerous = fetch_model_assertions(
            "noble", "tests/testdata/", "amd64")
        snaps = set((
            SeededSnap("24.04", "hello", "latest", "stable", "ubuntu-24.04", False),
            SeededSnap("24.04", "pi-kernel", "24", "stable", "", False),
        ))
        add_snaps_to_model_assertion(model_dangerous, snaps, "noble")
        with open("tests/testdata/"
                  "ubuntu-classic-2404-amd64-dangerous-new.json") as f:
            new_model = json.load(f)
        self.assertDictEqual(model_dangerous, new_model)

    @patch('subprocess.check_output')
    def test_get_supported_model_series(self, mock_check_output):
        # The regular, normal case.
        mock_check_output.side_effect = [
            b"jammy\nkinetic\nlunar\nmantic\nnoble\noracular\n",
            b"jammy\nmantic\nnoble\noracular\n"
        ]
        supported = get_supported_model_series()
        self.assertListEqual(supported, ["mantic", "noble", "oracular"])
        # Mantic no longer supported case.
        mock_check_output.side_effect = [
            b"jammy\nkinetic\nlunar\nmantic\nnoble\noracular\n",
            b"jammy\nnoble\noracular\n"
        ]
        supported = get_supported_model_series()
        self.assertListEqual(supported, ["noble", "oracular"])
        

if __name__ == '__main__':
    unittest.main()