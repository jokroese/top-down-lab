import io
import stat
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import lab


class LabTests(unittest.TestCase):
    def setUp(self):
        self.output = io.StringIO()
        context = redirect_stdout(self.output)
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)

    def test_template_rejects_empty_duplicate_and_unsupported_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "user.js"
            for content in (
                "// No settings",
                'user_pref("x", true);\nuser_pref("x", false);',
                'user_pref("x", "unsupported");',
                'user_pref("x", true)',
            ):
                with self.subTest(content=content):
                    path.write_text(content)
                    with self.assertRaises(ValueError):
                        lab.values(path, strict=True)

    def test_commented_preferences_are_not_reported_as_installed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "user.js"
            path.write_text(
                '// user_pref("disabled", true);\n'
                'user_pref("actual", false); // comment\n'
                'user_pref("unrelated", "string");\n'
            )
            self.assertEqual({"actual": False}, lab.values(path))

    def test_invalid_template_leaves_existing_profile_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "firefox").mkdir()
            (root / "firefox/user.js").write_text("invalid")
            profile = root / "profile"
            profile.mkdir()
            target = profile / "user.js"
            target.write_text("keep me")
            with patch.object(lab, "ROOT", root):
                with self.assertRaises(ValueError):
                    lab.configure(profile)
            self.assertEqual("keep me", target.read_text())
            self.assertEqual([target], list(profile.iterdir()))

    def test_preserves_existing_preferences_and_is_repeatable(self):
        original = '// My preference\nuser_pref("other.setting", true);\n'
        template = 'user_pref("network.trr.mode", 5);\n'
        updated = lab.managed_text(original, template)
        self.assertIn(original.strip(), updated)
        self.assertEqual(updated, lab.managed_text(updated, template))
        replaced = lab.managed_text(updated, 'user_pref("network.trr.mode", 0);')
        self.assertNotIn('"network.trr.mode", 5', replaced)
        self.assertIn(original.strip(), replaced)

    def test_malformed_block_rejected(self):
        with self.assertRaises(RuntimeError):
            lab.managed_text(lab.BEGIN, "template")

    def test_check_does_not_create_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(lab, "ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "not set up"):
                    lab.resolve_profile()
            self.assertFalse((root / "firefox").exists())

    def test_create_and_reuse_profile_without_reading_registry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(lab, "ROOT", root),
                patch.object(
                    Path, "open", side_effect=AssertionError("No file reads expected")
                ),
            ):
                profile = lab.resolve_profile(create=True)
                self.assertEqual((root / "firefox/profile").resolve(), profile)
                self.assertEqual(profile, lab.resolve_profile())
                self.assertEqual(profile, lab.resolve_profile(create=True))
                self.assertEqual(0o700, stat.S_IMODE(profile.stat().st_mode))

    def test_profile_symlinks_cannot_redirect_setup(self):
        for symlink_parent in (False, True):
            with (
                self.subTest(symlink_parent=symlink_parent),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                outside = root / "everyday"
                outside.mkdir()
                if symlink_parent:
                    (root / "firefox").symlink_to(outside, target_is_directory=True)
                else:
                    (root / "firefox").mkdir()
                    (root / "firefox/profile").symlink_to(
                        outside, target_is_directory=True
                    )
                with patch.object(lab, "ROOT", root):
                    with self.assertRaisesRegex(RuntimeError, "symlink"):
                        lab.resolve_profile(create=True)
                self.assertEqual([], list(outside.iterdir()))

    def test_launch_uses_explicit_profile_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="lab with spaces ") as temporary:
            root = Path(temporary)
            (root / "firefox").mkdir()
            (root / "firefox/user.js").write_text(
                (lab.ROOT / "firefox/user.js").read_text()
            )
            with (
                patch.object(lab, "ROOT", root),
                patch.object(
                    lab,
                    "app",
                    side_effect=lambda name: Path("/Applications") / (name + ".app"),
                ),
                patch.object(lab.subprocess, "run") as run,
                patch.object(lab.sys, "platform", "darwin"),
            ):
                self.assertEqual(0, lab.main(["start"]))
            run.assert_any_call(
                [
                    "/usr/bin/open",
                    "-n",
                    "-a",
                    "/Applications/Firefox.app",
                    "--args",
                    "--no-remote",
                    "--profile",
                    str((root / "firefox/profile").resolve()),
                    "about:blank",
                ],
                check=True,
            )
            self.assertEqual(
                lab.expected_preferences(), lab.values(root / "firefox/profile/user.js")
            )

    def test_configure_backup_and_repeat(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary)
            user = profile / "user.js"
            user.write_text('user_pref("other", true);\n')
            lab.configure(profile)
            lab.configure(profile)
            backups = list(profile.glob("user.js.before-*"))
            self.assertEqual(1, len(backups))
            self.assertEqual('user_pref("other", true);\n', backups[0].read_text())
            actual = lab.values(user)
            for key, value in lab.expected_preferences().items():
                self.assertEqual(value, actual[key])
            self.assertTrue(actual["other"])

    def test_symlink_settings_are_not_followed(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary)
            outside = profile / "original.js"
            outside.write_text("keep me")
            (profile / "user.js").symlink_to(outside)
            with self.assertRaises(RuntimeError):
                lab.configure(profile)
            self.assertEqual("keep me", outside.read_text())

    def test_safe_archive_and_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "traces.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("traces/intro.pcap", b"fixture")
            lab.extract_archive(archive, root / "good")
            self.assertEqual(b"fixture", (root / "good/traces/intro.pcap").read_bytes())
            for bad in (
                "../escaped",
                "/absolute",
                "traces/../../escaped",
                "traces\\evil",
            ):
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr(bad, b"bad")
                with self.assertRaises(RuntimeError):
                    lab.extract_archive(archive, root / "bad")
            self.assertFalse((root / "escaped").exists())

    def test_archive_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "traces.zip"
            item = zipfile.ZipInfo("link")
            item.create_system = 3
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr(item, "../elsewhere")
            with self.assertRaises(RuntimeError):
                lab.extract_archive(archive, root / "out")


if __name__ == "__main__":
    unittest.main()
