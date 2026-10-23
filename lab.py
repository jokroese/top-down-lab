#!/usr/bin/env python3
"""Set up Firefox and Wireshark on macOS for the Kurose–Ross labs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = "https://www-net.cs.umass.edu/wireshark-labs/wireshark-traces-9e.zip"
BEGIN = "// BEGIN top-down-lab managed preferences"
END = "// END top-down-lab managed preferences"
PREF_PATTERN = re.compile(
    r'user_pref\("([^"\\]+)",\s*(true|false|-?\d+)\s*\);(?:\s*//.*)?'
)


def app(name: str) -> Path:
    for parent in (Path("/Applications"), Path.home() / "Applications"):
        path = parent / (name + ".app")
        if path.is_dir():
            return path
    raise RuntimeError(f"{name} is not installed in /Applications or ~/Applications.")


def resolve_profile(*, create: bool = False) -> Path:
    """Use only the repository's dedicated profile, without reading Firefox's registry."""
    parent = ROOT / "firefox"
    profile = parent / "profile"
    if parent.is_symlink() or profile.is_symlink():
        raise RuntimeError(
            "The dedicated profile path must not be a symlink; leaving it untouched."
        )
    if create:
        profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not profile.is_dir():
        raise RuntimeError(
            "The dedicated lab profile is not set up. Run ./start-lab.command "
            "or python3 lab.py setup first."
        )
    return profile.resolve()


def managed_text(existing: str, template: str) -> str:
    if existing.count(BEGIN) != existing.count(END) or existing.count(BEGIN) > 1:
        raise RuntimeError(
            "Malformed managed block in user.js; leaving the file untouched."
        )
    if BEGIN in existing:
        start, end = existing.index(BEGIN), existing.index(END)
        if end < start:
            raise RuntimeError(
                "Malformed managed block in user.js; leaving the file untouched."
            )
        existing = existing[:start] + existing[end + len(END) :]
    return (
        existing.rstrip()
        + ("\n\n" if existing.strip() else "")
        + BEGIN
        + "\n"
        + template.rstrip()
        + "\n"
        + END
        + "\n"
    )


def configure(profile: Path) -> None:
    expected_preferences()  # Reject malformed configuration before touching the profile.
    target = profile / "user.js"
    if target.is_symlink():
        raise RuntimeError(
            "The profile user.js is a symlink; leaving it untouched. Install the lab preferences manually."
        )
    old = target.read_text(encoding="utf-8") if target.exists() else ""
    new = managed_text(old, (ROOT / "firefox/user.js").read_text(encoding="utf-8"))
    if old == new:
        print("Lab browser settings are up to date.")
        return
    if target.exists():
        backup = profile / f"user.js.before-top-down-lab-{time.time_ns()}"
        shutil.copy2(target, backup)
        print(f"Backed up previous settings: {backup}")
    fd, temporary = tempfile.mkstemp(prefix=".top-down-lab-", dir=profile)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(new)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    print("Updated lab browser settings. They apply when the lab Firefox starts.")


def values(path: Path, *, strict: bool = False) -> dict[str, bool | int]:
    """Read bool/integer user_pref lines without evaluating JavaScript.

    The template is deliberately limited to these types and // comments. Ordinary
    Firefox files may contain other preference types, which the checker ignores.
    """
    if not path.exists() and not strict:
        return {}
    result = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        match = PREF_PATTERN.fullmatch(line)
        if match:
            key, value = match.groups()
            if strict and key in result:
                raise ValueError(f"Duplicate preference in {path}:{number}: {key}")
            result[key] = json.loads(value)
        elif strict:
            raise ValueError(f"Invalid preference in {path}:{number}: {line}")
    if strict and not result:
        raise ValueError(f"No preferences found in {path}")
    return result


def expected_preferences() -> dict[str, bool | int]:
    return values(ROOT / "firefox/user.js", strict=True)


def check() -> int:
    failures = 0
    for name in ("Firefox", "Wireshark"):
        try:
            location = app(name)
            with (location / "Contents/Info.plist").open("rb") as stream:
                version = plistlib.load(stream).get("CFBundleShortVersionString")
            if not version:
                raise RuntimeError(f"Missing version information for {name}.")
            print(f"OK: {name} {version} — {location}")
        except (
            RuntimeError,
            OSError,
            ValueError,
            plistlib.InvalidFileException,
        ) as exc:
            print(f"FAIL: {exc}")
            failures += 1
    try:
        profile = resolve_profile()
        print(f"Profile: {profile}")
        installed = values(profile / "user.js")
        for key, value in expected_preferences().items():
            correct = (
                type(installed.get(key)) is type(value) and installed.get(key) == value
            )
            print(
                f"{'OK' if correct else 'FAIL'}: {key} = {json.dumps(value)} in user.js"
            )
            failures += not correct
        print(
            "user.js verifies next-start settings. Confirm the values in about:config after launching."
        )
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        failures += 1
    try:
        dumpcap = app("Wireshark") / "Contents/MacOS/dumpcap"
        result = subprocess.run(
            [str(dumpcap), "-D"], capture_output=True, text=True, timeout=15
        )
        if result.returncode or not result.stdout.strip():
            raise RuntimeError(
                result.stderr.strip() or "No capture interfaces available."
            )
        print(
            "OK: capture interfaces can be enumerated (this does not prove packet capture works)."
        )
        devices = list(Path("/dev").glob("bpf*"))
        if not any(os.access(p, os.R_OK | os.W_OK) for p in devices):
            raise RuntimeError(
                "No accessible /dev/bpf devices in this process. Retry from Terminal; if still blocked, check Wireshark’s ChmodBPF installation."
            )
        print("OK: at least one BPF device is accessible.")
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL: {exc}")
        failures += 1
    archive = ROOT / "traces/wireshark-traces-9e"
    print(
        f"{'OK' if archive.is_dir() else 'OPTIONAL'}: reference traces {'present' if archive.is_dir() else 'not downloaded; run python3 lab.py fetch'}."
    )
    return 1 if failures else 0


def extract_archive(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if sum(item.file_size for item in members) > 500_000_000:
            raise RuntimeError("Archive expands beyond the 500 MB safety limit.")
        for item in members:
            path = Path(item.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename:
                raise RuntimeError(f"Unsafe archive path: {item.filename}")
            if stat.S_ISLNK(item.external_attr >> 16):
                raise RuntimeError(f"Archive contains a symlink: {item.filename}")
        bad = bundle.testzip()
        if bad:
            raise RuntimeError(f"Corrupt archive member: {bad}")
        bundle.extractall(destination)


def fetch() -> None:
    traces = ROOT / "traces"
    traces.mkdir(exist_ok=True)
    destination = traces / "wireshark-traces-9e"
    if destination.exists():
        print(
            f"Reference traces already exist: {destination}\nKept existing files. Rename that directory to download a fresh copy."
        )
        return
    with tempfile.TemporaryDirectory(prefix=".download-", dir=traces) as temporary:
        temporary = Path(temporary)
        archive = temporary / "traces.zip"
        subprocess.run(
            [
                "curl",
                "--fail",
                "--location",
                "--show-error",
                "--proto",
                "=https",
                "--proto-redir",
                "=https",
                "--connect-timeout",
                "20",
                "--max-time",
                "300",
                "--retry",
                "2",
                "--max-filesize",
                "100000000",
                "--output",
                str(archive),
                URL,
            ],
            check=True,
        )
        contents = temporary / "contents"
        contents.mkdir()
        extract_archive(archive, contents)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (contents / "DOWNLOAD.json").write_text(
            json.dumps(
                {
                    "source": URL,
                    "downloaded_utc": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    ),
                    "archive_sha256": digest,
                    "note": "Local download fingerprint; the authors do not supply a verified checksum here.",
                },
                indent=2,
            )
            + "\n"
        )
        contents.rename(destination)
    print(f"Official traces extracted to {destination}\nSHA-256: {digest}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("setup", "start", "check", "fetch"),
        help="configure the profile, launch the lab, check prerequisites, or fetch official traces",
    )
    action = parser.parse_args(argv).action
    if sys.version_info < (3, 11):
        parser.error("Python 3.11 or newer is required.")
    if action in ("start", "check") and sys.platform != "darwin":
        parser.error(
            "Launching the lab and checking capture prerequisites require macOS."
        )
    if action == "fetch":
        fetch()
    elif action == "check":
        return check()
    else:
        if action == "start":
            firefox = app("Firefox")
            wireshark = app("Wireshark")
        profile = resolve_profile(create=True)
        configure(profile)
        if action == "start":
            (ROOT / "captures").mkdir(exist_ok=True)
            subprocess.run(["/usr/bin/open", "-a", str(wireshark)], check=True)
            # -n gives the requested profile a separate application instance.
            subprocess.run(
                [
                    "/usr/bin/open",
                    "-n",
                    "-a",
                    str(firefox),
                    "--args",
                    "--no-remote",
                    "--profile",
                    str(profile),
                    "about:blank",
                ],
                check=True,
            )
            print(
                "Opened the lab Firefox and Wireshark.\n\n"
                "Follow your worksheet using the lab Firefox window and Wireshark.\n"
            )
            print("Quit the Firefox lab profile with ⌘Q")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (
        RuntimeError,
        OSError,
        ValueError,
        zipfile.BadZipFile,
        subprocess.SubprocessError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
