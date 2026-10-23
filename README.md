# Top-down lab

A lightweight macOS companion for the [Wireshark labs](https://gaia.cs.umass.edu/kurose_ross/wireshark.php) in [Computer Networking: A Top-Down Approach](https://gaia.cs.umass.edu/kurose_ross/index.php) by Kurose and Ross. It opens Wireshark and a separate Firefox profile configured for the browser exercises.

## Install once

- Install [Firefox](https://www.mozilla.org/firefox/) and [Wireshark](https://www.wireshark.org/download.html) in `/Applications` or `~/Applications`.
- For live capture, open **Install ChmodBPF.pkg** in the Wireshark disk image. See [Wireshark’s macOS installation guide](https://www.wireshark.org/docs/wsug_html_chunked/ChBuildInstallOSXInstall.html).
- Install [Python 3.11 or newer](https://www.python.org/downloads/macos/). No Python packages are required.

## Start a session

From this folder, run:

```sh
python3 lab.py start
```

Or double-click `start-lab.command` in Finder. This creates the lab browser profile on the first time, and reuses it after.

Follow the [Kurose–Ross worksheet](https://gaia.cs.umass.edu/kurose_ross/wireshark.php) using the lab Firefox window and Wireshark.

## Finish a session

**Quit the Firefox lab profile with ⌘Q.** This clears history and cache, ready for the next session. Note that closing the window alone is not enough.

## If setup fails

Run the setup checker:

```sh
python3 lab.py check
```

It checks applications, saved browser settings and capture access. It does not confirm that a live capture works.

| Problem                                 | What to do                                                                                                 |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Firefox or Wireshark is missing         | Install the application in `/Applications` or `~/Applications`.                                            |
| Python is missing or too old            | Install Python 3.11 or newer, then reopen Terminal and retry.                                              |
| Wireshark cannot access capture devices | Install ChmodBPF as described above. If the checker still reports an access error, rerun it from Terminal. |
| The lab profile is already in use       | Quit the Firefox lab profile with ⌘Q, then launch again.                                                   |

## Optional: recorded traces

Download the authors’ ninth-edition trace files:

```sh
python3 lab.py fetch
```

They are saved in `traces/wireshark-traces-9e/`. Follow your worksheet or course instructions to select the appropriate file.

## Settings and local files

[firefox/user.js](firefox/user.js) disables HTTP/3/QUIC, automatic HTTPS upgrades and Firefox DNS over HTTPS. History and cache clear when you quit with ⌘Q. Edit this file and restart the lab Firefox to change settings.

The profile shares your Mac’s network and VPN; HTTPS traffic remains encrypted.

Save captures in `captures/`. Browser state and downloaded traces are also excluded from Git.

## Development

`lab.py` contains the implementation; `start-lab.command` is only a Finder shortcut.

```sh
python3 lab.py setup   # configure without launching
python3 -m unittest discover -s tests -v
```

Tests use temporary files and mocked launches. CI runs them on macOS with Python 3.11 and the latest stable Python 3.
