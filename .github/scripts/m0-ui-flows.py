"""Account-free UI checks on disposable GitHub Actions Android emulators only."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


PACKAGE = "com.huanchengfly.tieba.post"
NOTIFICATIONS = "android.permission.POST_NOTIFICATIONS"


def center(bounds):
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not match:
        raise ValueError(f"Invalid UI bounds: {bounds}")
    left, top, right, bottom = map(int, match.groups())
    if right <= left or bottom <= top:
        raise ValueError(f"Invisible UI node: {bounds}")
    return (left + right) // 2, (top + bottom) // 2


def node_with(root, **attributes):
    for node in root.iter("node"):
        if all(node.get(key) == value for key, value in attributes.items()):
            try:
                center(node.get("bounds", ""))
            except ValueError:
                continue
            return node
    return None


def notification_granted(package_dump):
    match = re.search(re.escape(NOTIFICATIONS) + r":\s+granted=(true|false)", package_dump)
    if not match:
        raise AssertionError("Notification runtime permission missing from package state")
    return match.group(1) == "true"


def require_disposable_emulator(environment, is_emulator, actual_api, requested_api):
    if environment.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("UI flows may reset app data; only GitHub Actions is allowed")
    if not re.fullmatch(r"emulator-\d+", environment.get("ANDROID_SERIAL", "")):
        raise RuntimeError("An explicit emulator serial is required")
    if is_emulator.strip() != "1" or actual_api.strip() != str(requested_api):
        raise RuntimeError("Device must be an emulator with the requested API level")


class Flows:
    def __init__(self, api, apk, evidence):
        self.api = api
        self.apk = apk.resolve(strict=True)
        self.evidence = evidence
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.serial = os.environ.get("ANDROID_SERIAL", "")
        self.results = []
        self.folder = evidence
        self.decision = None
        self.permission_clicked = False

    def adb(self, *args, binary=False):
        print("adb", *args, flush=True)
        result = subprocess.run(
            ["adb", "-s", self.serial, *args], check=True, capture_output=True,
            timeout=30 if args[:1] != ("install",) else 120,
        )
        return result.stdout if binary else result.stdout.decode("utf-8", errors="replace").strip()

    def validate_device(self):
        # Fail closed before even contacting a device outside the intended CI.
        if os.environ.get("GITHUB_ACTIONS") != "true" or not re.fullmatch(r"emulator-\d+", self.serial):
            raise RuntimeError("Refusing to reset an app outside a dedicated CI emulator")
        require_disposable_emulator(
            os.environ, self.adb("shell", "getprop", "ro.kernel.qemu"),
            self.adb("shell", "getprop", "ro.build.version.sdk"), self.api,
        )

    def raw_ui(self):
        self.adb("shell", "uiautomator", "dump", "--compressed", "/sdcard/m0-window.xml")
        return ET.fromstring(self.adb("shell", "cat", "/sdcard/m0-window.xml"))

    def tap(self, node):
        x, y = center(node.get("bounds", ""))
        self.adb("shell", "input", "tap", str(x), str(y))
        time.sleep(0.6)

    def ui(self):
        root = self.raw_ui()
        permission_nodes = [n for n in root.iter("node") if "permissioncontroller" in n.get("package", "")]
        if permission_nodes:
            message = " ".join(n.get("text", "") for n in permission_nodes).lower()
            if self.api < 33 or not any(word in message for word in ("notifications", "通知")):
                raise AssertionError("Unexpected runtime permission dialog")
            suffix = ":id/permission_allow_button" if self.decision == "allow" else ":id/permission_deny_button"
            button = next((n for n in permission_nodes if n.get("resource-id", "").endswith(suffix)), None)
            if button is None:
                raise AssertionError("Expected notification decision button not found")
            (self.folder / "notification-prompt.png").write_bytes(self.adb("exec-out", "screencap", "-p", binary=True))
            self.tap(button)
            self.permission_clicked = True
            root = self.raw_ui()
        return root

    def wait_node(self, seconds=35, **attributes):
        deadline = time.monotonic() + seconds
        last_error = None
        while time.monotonic() < deadline:
            try:
                node = node_with(self.ui(), **attributes)
                if node is not None:
                    return node
            except (subprocess.SubprocessError, ET.ParseError) as error:
                last_error = error
            time.sleep(1)
        raise AssertionError(f"UI node not found: {attributes}; last error: {last_error}")

    def click(self, **attributes):
        self.tap(self.wait_node(**attributes))

    def title(self, text):
        self.wait_node(**{"resource-id": f"{PACKAGE}:id/title", "text": text})

    def next_page(self, title):
        self.click(**{"resource-id": f"{PACKAGE}:id/button_next"})
        self.title(title)

    def capture(self, name):
        root = self.ui()
        ET.ElementTree(root).write(self.folder / f"{name}.xml", encoding="utf-8")
        (self.folder / f"{name}.png").write_bytes(self.adb("exec-out", "screencap", "-p", binary=True))

    def record(self, name, status="passed", **details):
        self.results.append({"scenario": self.decision, "check": name, "status": status, **details})
        print(json.dumps(self.results[-1], ensure_ascii=False), flush=True)

    def preference(self, file, key):
        root = ET.fromstring(self.adb("shell", "run-as", PACKAGE, "cat", f"shared_prefs/{file}.xml"))
        node = next((node for node in root if node.get("name") == key), None)
        if node is None:
            raise AssertionError(f"Preference {file}/{key} is missing")
        return node.get("value") if node.tag == "boolean" else node.text

    def select_theme(self, label, value):
        for _ in range(8):
            root = self.ui()
            node = node_with(root, **{"resource-id": f"{PACKAGE}:id/theme_name", "text": label})
            if node is not None:
                self.tap(node)
                self.wait_node(**{"resource-id": f"{PACKAGE}:id/theme_list"})
                if self.preference("settings", "theme") != value:
                    raise AssertionError(f"Theme {value} was not persisted")
                self.capture(f"theme-{value}")
                self.record(f"theme-{value}")
                return
            listing = node_with(root, **{"resource-id": f"{PACKAGE}:id/theme_list"})
            if listing is None:
                raise AssertionError("Theme list not visible")
            left, top, right, bottom = map(int, re.findall(r"\d+", listing.get("bounds")))
            x = (left + right) // 2
            self.adb("shell", "input", "swipe", str(x), str(bottom - 60), str(x), str(top + 60), "300")
        raise AssertionError(f"Theme option not found: {label}")

    def launch(self):
        self.adb("shell", "am", "start", "-W", "-a", "android.intent.action.MAIN", "-c",
                 "android.intent.category.LAUNCHER", "-f", "0x10200000", "-n", f"{PACKAGE}/.activities.MainActivity")

    def wait_activity(self, name):
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            self.ui()
            dump = self.adb("shell", "dumpsys", "activity", "activities")
            resumed = [line for line in dump.splitlines() if re.search(r"(?:mResumedActivity:|topResumedActivity=)", line)]
            if any(f"{PACKAGE}/.activities.{name}" in line for line in resumed):
                return
            time.sleep(1)
        raise AssertionError(f"Activity {name} did not resume")

    def scenario(self, decision):
        self.decision = decision
        self.permission_clicked = False
        self.folder = self.evidence / decision
        self.folder.mkdir(parents=True, exist_ok=True)
        # validate_device must run before this reset. Each case starts without
        # account data, permission decisions or settings from the previous case.
        self.adb("uninstall", PACKAGE)
        self.adb("install", "--no-streaming", "-r", str(self.apk))
        self.adb("logcat", "-c")
        self.launch()
        self.title("欢迎使用贴吧 Lite")
        self.capture("welcome")
        self.record("cold-start")
        if self.api >= 33:
            if not self.permission_clicked:
                # The platform may show its target-29 notification prompt late.
                for _ in range(8):
                    self.ui()
                    if self.permission_clicked:
                        break
                    time.sleep(1)
            if not self.permission_clicked:
                raise AssertionError("Notification prompt was never exercised")
            granted = notification_granted(self.adb("shell", "dumpsys", "package", PACKAGE))
            if granted != (decision == "allow"):
                raise AssertionError(f"Notification state does not match {decision}")
            self.record("notification-decision", granted=granted)
        else:
            self.record("notification-decision", "not-applicable", reason="API below 33")
        self.next_page("使用习惯设置")
        self.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        self.title("欢迎使用贴吧 Lite")
        self.capture("system-back")
        self.record("intro-system-back")
        self.next_page("使用习惯设置")
        self.next_page("自定义")
        self.click(text="选择主题")
        self.wait_node(**{"resource-id": f"{PACKAGE}:id/theme_list"})
        self.select_theme("少女粉", "pink")
        self.select_theme("静谧蓝", "dark")
        self.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        self.title("自定义")
        self.next_page("杂项")
        self.next_page("探索更多")
        self.next_page("一切就绪！")
        self.capture("intro-complete")
        self.click(**{"resource-id": f"{PACKAGE}:id/button_next"})
        self.wait_activity("LoginActivity")
        if self.preference("appData", "first") != "false":
            raise AssertionError("Completing intro did not persist first=false")
        self.capture("login-entry")
        self.record("intro-completion")
        before_pid = self.adb("shell", "pidof", PACKAGE)
        self.adb("shell", "input", "keyevent", "KEYCODE_HOME")
        self.launch()
        self.wait_activity("LoginActivity")
        if self.adb("shell", "pidof", PACKAGE) != before_pid:
            raise AssertionError("Hot start did not retain the app process")
        self.capture("hot-start")
        self.record("hot-start", pid=before_pid)
        self.adb("shell", "am", "force-stop", PACKAGE)
        self.launch()
        self.wait_activity("LoginActivity")
        if self.preference("settings", "theme") != "dark" or self.preference("appData", "first") != "false":
            raise AssertionError("Theme or intro completion lost after process restart")
        self.capture("restart-persistence")
        self.record("restart-persistence")

    def run(self):
        self.validate_device()
        failed = False
        for decision in (("deny", "allow") if self.api >= 33 else ("legacy",)):
            try:
                self.scenario(decision)
            except Exception as error:
                failed = True
                self.record("scenario", "failed", error=str(error))
            finally:
                for name, args in (
                    ("logcat.txt", ("logcat", "-d", "-t", "1000")),
                    ("activity.txt", ("shell", "dumpsys", "activity", "activities")),
                ):
                    try:
                        (self.folder / name).write_text(self.adb(*args), encoding="utf-8")
                    except Exception as error:
                        print(f"Could not capture {name}: {error}", flush=True)
                try:
                    self.capture("final")
                except Exception as error:
                    print(f"Could not capture final UI: {error}", flush=True)
                (self.evidence / "results.json").write_text(
                    json.dumps({"api": self.api, "checks": self.results}, ensure_ascii=False, indent=2), encoding="utf-8",
                )
        return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", type=int, choices=(29, 36), required=True)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    sys.exit(Flows(args.api, args.apk, args.evidence).run())
