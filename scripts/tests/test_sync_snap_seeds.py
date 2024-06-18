#!/usr/bin/python3

import unittest
import json

from unittest.mock import patch

from snap_seeds import fetch_model_assertion, fetch_snaps_from_model_assertion, fetch_snaps_from_seed, add_snaps_to_model_assertion


def mock_get_snap_info(snap):
    if snap.endswith("-kernel"):
        return {"channel-map": [{"type": "kernel"}], "snap-id": "1234"}
    elif snap in ("pc", "pi"):
        return {"channel-map": [{"type": "gadget"}], "snap-id": "1234"}
    else:
        return {"channel-map": [{"type": "app"}], "snap-id": "1234"}


class TestSnapSeeds(unittest.TestCase):
    def test_fetch_model_assertion_no_model(self):
        model = fetch_model_assertion("xenial", "tests/testdata/", "amd64")
        self.assertIsNone(model)

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
        self.assertSetEqual(seeded_snaps,
                            set(("firefox", "gnome-42-2204",
                                "gtk-common-themes", "snap-store",
                                "snapd-desktop-integration",
                                "firmware-updater")))
        
    def test_fetch_snaps_from_model_assertion(self):
        """This tests both the fetching and parsing of the model assertion."""
        model = fetch_model_assertion("noble", "tests/testdata/", "amd64")
        snaps = fetch_snaps_from_model_assertion(model)
        self.assertSetEqual(snaps, set(
            ('gtk-common-themes',
             'pc-kernel',
             'pc',
             'firefox',
             'snapd',
             'firmware-updater',
             'gnome-42-2204',
             'bare',
             'snap-store',
             'snapd-desktop-integration',
             'core22',
            )))

    @patch('snap_seeds.get_snap_info', side_effect=mock_get_snap_info)
    def test_add_snaps_to_model_assertion(self, mock_get):
        model = fetch_model_assertion("noble", "tests/testdata/", "amd64")
        snaps = set(("hello", "pi-kernel"))
        add_snaps_to_model_assertion(model, snaps, "noble")
        with open("tests/testdata/ubuntu-classic-2404-amd64-new.json") as f:
            new_model = json.load(f)
        self.assertDictEqual(model, new_model)
        

if __name__ == '__main__':
    unittest.main()