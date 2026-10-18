"""Regression tests for selectors, permission assertions and the device reset guard."""

import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


spec = importlib.util.spec_from_file_location("m0_ui_flows", Path(__file__).with_name("m0-ui-flows.py"))
flows = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flows)


class SelectorTests(unittest.TestCase):
    def test_tap_point_comes_from_visible_control_bounds(self):
        self.assertEqual(flows.center("[10,20][50,100]"), (30, 60))

    def test_malformed_or_invisible_bounds_are_rejected(self):
        for bounds in ("", "[0,0][0,0]", "[50,20][10,100]", "10,20,50,100"):
            with self.subTest(bounds=bounds), self.assertRaises(ValueError):
                flows.center(bounds)

    def test_offscreen_duplicate_title_does_not_satisfy_a_page_assertion(self):
        root = ET.fromstring('''<hierarchy>
          <node text="自定义" bounds="[0,0][0,0]" />
          <node text="使用习惯设置" bounds="[0,0][100,100]" />
        </hierarchy>''')
        self.assertIsNone(flows.node_with(root, text="自定义"))

    def test_selector_requires_both_resource_id_and_text(self):
        root = ET.fromstring('''<hierarchy>
          <node resource-id="wrong" text="自定义" bounds="[0,0][100,100]" />
          <node resource-id="title" text="自定义" bounds="[0,100][100,200]" />
        </hierarchy>''')
        self.assertEqual(flows.node_with(root, **{"resource-id": "title", "text": "自定义"}).get("bounds"), "[0,100][100,200]")


class NotificationTests(unittest.TestCase):
    def test_both_granted_and_denied_permissions_are_distinguished(self):
        for granted in (True, False):
            with self.subTest(granted=granted):
                dump = f"android.permission.POST_NOTIFICATIONS: granted={str(granted).lower()}, flags=[ USER_SET ]"
                self.assertEqual(flows.notification_granted(dump), granted)

    def test_other_granted_permissions_cannot_mask_denied_notifications(self):
        dump = "android.permission.INTERNET: granted=true\nandroid.permission.POST_NOTIFICATIONS: granted=false"
        self.assertFalse(flows.notification_granted(dump))

    def test_missing_runtime_state_is_not_assumed_to_mean_granted(self):
        with self.assertRaises(AssertionError):
            flows.notification_granted("requested permissions: android.permission.POST_NOTIFICATIONS")


class ResetGuardTests(unittest.TestCase):
    def test_matching_ci_emulator_is_accepted(self):
        environment = {"GITHUB_ACTIONS": "true", "ANDROID_SERIAL": "emulator-5554"}
        flows.require_disposable_emulator(environment, "1\n", "36\n", 36)

    def test_personal_devices_and_mismatched_targets_are_rejected(self):
        cases = (
            ({}, "1", "36", 36),
            ({"GITHUB_ACTIONS": "false", "ANDROID_SERIAL": "emulator-5554"}, "1", "36", 36),
            ({"GITHUB_ACTIONS": "true", "ANDROID_SERIAL": "physical-device"}, "1", "36", 36),
            ({"GITHUB_ACTIONS": "true", "ANDROID_SERIAL": "emulator-5554"}, "0", "36", 36),
            ({"GITHUB_ACTIONS": "true", "ANDROID_SERIAL": "emulator-5554"}, "1", "29", 36),
        )
        for environment, emulator, actual_api, expected_api in cases:
            with self.subTest(environment=environment, emulator=emulator, api=actual_api):
                with self.assertRaises(RuntimeError):
                    flows.require_disposable_emulator(environment, emulator, actual_api, expected_api)


if __name__ == "__main__":
    unittest.main()
