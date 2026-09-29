"""Start a throwaway resolver, ask it questions, shut it down.

The classifier runs as a local process and answers over HTTP on the
loopback interface. Nothing here reaches the network, and the database it
writes to is a temporary file that is deleted when the scan finishes, so a
scan never touches state you rely on.

Everything in this module is standard library. `oats-scan` has no
dependencies at all.
"""
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BIN = Path(__file__).resolve().parent / "_bin"

# How the hook says a ruling it gives Claude Code no decision for (Watch)
# on stderr: oatsctl hook pre-tool-use prints {} and this line.
WATCH_PREFIX = "OATS Watch: "


class ScanError(Exception):
    """Something the person running this can act on."""


def platform_slug():
    """Which bundled build belongs to this machine.

    macOS ships one universal binary covering Apple Silicon and Intel, so
    the architecture is not part of its directory name.
    """
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Darwin":
        return "darwin-universal"
    if system == "Linux":
        return "linux-aarch64" if machine in ("aarch64", "arm64") else "linux-x86_64"
    if system == "Windows":
        return "windows-x86_64"
    return "{}-{}".format(system.lower(), machine)


def binary_path(name):
    """The bundled binary for this platform."""
    filename = name + (".exe" if os.name == "nt" else "")
    override = os.environ.get("OATS_SCAN_BIN_DIR")
    candidates = []
    if override:
        candidates.append(Path(override) / filename)
    candidates.append(BIN / platform_slug() / filename)
    # A checkout built for a single platform keeps the binaries flat.
    candidates.append(BIN / filename)
    for candidate in candidates:
        if candidate.is_file():
            # Only when it cannot already run: chmod needs ownership, and a
            # service running as a non-root user over root-owned packages
            # (the hardened container pheo-context ships) gets EPERM here
            # and boots with no classifier.
            if os.name != "nt" and not os.access(candidate, os.X_OK):
                candidate.chmod(candidate.stat().st_mode | 0o111)
            return candidate
    have = sorted(p.name for p in BIN.iterdir() if p.is_dir()) if BIN.is_dir() else []
    raise ScanError(
        "No classifier build for this machine.\n"
        "\n"
        "  your platform:  {} {}  (looking for '{}')\n"
        "  this copy has:  {}\n"
        "\n"
        "The classifier is compiled, so it ships one build per platform.\n"
        "See https://github.com/pheo-ai/oats-scan#install".format(
            platform.system(), platform.machine(), platform_slug(),
            ", ".join(have) or "no builds at all")
    )


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request_json(url, method="GET", body=None, timeout=5):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def ready(gateway):
    try:
        environment = request_json(gateway + "/api/environment", timeout=0.5)
        return isinstance(environment, dict) and "public_gateway" in environment
    except (OSError, urllib.error.URLError, ValueError):
        return False


class Resolver(object):
    """A local classifier process, running only for the length of a scan.

    Used as a context manager. On exit the process is terminated and the
    temporary database removed, including on an exception or a Ctrl-C.
    """

    def __init__(self, cwd=None):
        # Deliberately NOT the directory being scanned. The classifier
        # creates a .pheo-gateway/ working directory beside wherever it is
        # started, and a tool that reports on a folder must not leave
        # anything inside it. It runs in a temporary directory that is
        # removed with everything else.
        self.workdir = tempfile.mkdtemp(prefix="oats-scan-run-")
        self.cwd = str(cwd) if cwd else self.workdir
        self.port = free_port()
        self.url = "http://127.0.0.1:{}".format(self.port)
        self.process = None
        self.database = None
        self.room = None

    def __enter__(self):
        handle = tempfile.NamedTemporaryFile(
            prefix="oats-scan-", suffix=".db", delete=False
        )
        handle.close()
        self.database = handle.name

        environment = os.environ.copy()
        environment.update({
            "PHEO_BIND_HOST": "127.0.0.1",
            "PORT": str(self.port),
            "PHEO_GATEWAY_PROFILE": "local",
            "PHEO_PUBLIC_GATEWAY": self.url,
            "PHEO_REVIEW_BASE": self.url + "/reviews",
            # No file watching and no local model: a scan reads files
            # itself and needs nothing but the classifier.
            "PHEO_WATCH": "0",
            "PHEO_GATEWAY_DB": self.database,
            # The database is discarded, so the key only has to last for
            # this process. Generating one here avoids reading or writing
            # any key material belonging to another install.
            "PHEO_VAULT_KEY": secrets.token_urlsafe(48),
            "PHEO_VAULT_BACKEND": "ephemeral",
        })
        environment.pop("PHEO_EXPLAIN", None)

        executable = binary_path("pheo-action-gateway")
        try:
            self.process = subprocess.Popen(
                [str(executable)],
                cwd=self.cwd, env=environment,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            # A binary built for another operating system is present but
            # cannot exec. The raw OSError is not something a person can
            # act on, so say what actually went wrong.
            self.close()
            raise ScanError(
                "The bundled classifier will not run on this machine.\n"
                "\n"
                "  your platform:  {} {}\n"
                "  error:          {}\n"
                "\n"
                "This install was built for a different operating system or "
                "architecture.\n"
                "See https://github.com/pheo-ai/oats-scan#install".format(
                    platform.system(), platform.machine(), error)
            ) from None

        deadline = time.time() + 30
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise ScanError(
                    "The classifier exited during startup (code {}).".format(
                        self.process.returncode)
                )
            if ready(self.url):
                break
            time.sleep(0.15)
        else:
            self.close()
            raise ScanError("The classifier did not start within 30 seconds.")

        self.room = request_json(
            self.url + "/api/projects", method="POST",
            body={"kind": "repo", "name": "oats-scan", "repo": "local/scan"},
            timeout=30,
        )["id"]
        return self

    def classify(self, command, label_to_key):
        """One command string to one consequence class, or None.

        None means the resolver did not answer, which the caller counts
        separately. A question that failed is not an answer of "harmless".
        """
        try:
            proc = subprocess.run(
                [str(binary_path("oatsctl")), "hook", "pre-tool-use",
                 "--gateway", self.url, "--project", self.room,
                 "--repo", "local/scan", "--agent-id", "scan"],
                input=json.dumps(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                ),
                capture_output=True, text=True, timeout=60,
            )
            lines = proc.stdout.strip().splitlines()
            payload = json.loads(lines[-1]) if lines else {}
            reason = (payload.get("hookSpecificOutput") or {}).get(
                "permissionDecisionReason")
            if not reason:
                # The scan's room is in Watch, where the hook gives Claude
                # Code no decision ({}) and says the ruling on stderr instead.
                reason = next(
                    (line[len(WATCH_PREFIX):] for line in proc.stderr.splitlines()
                     if line.startswith(WATCH_PREFIX)),
                    None,
                )
            if not reason:
                return None
        except Exception:
            return None
        label = reason.split(" to ")[0].split(" at ")[0].strip()
        return label_to_key.get(label)

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.database:
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.unlink(self.database + suffix)
                except OSError:
                    pass
            self.database = None
        if getattr(self, "workdir", None):
            shutil.rmtree(self.workdir, ignore_errors=True)
            self.workdir = None

    def __exit__(self, *exc):
        self.close()
        return False
