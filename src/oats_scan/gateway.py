"""Start a throwaway resolver, ask it questions, shut it down.

`Resolver` is for callers that classify one command at a time over a long
life, as the Pheo space does:

    resolver = Resolver()
    resolver.__enter__()                  # or: with Resolver() as resolver:
    key = resolver.classify("rm -rf ./build", label_to_key)
    resolver.close()

The classifier runs as a local process and answers over HTTP on the
loopback interface. Nothing here reaches the network, and everything it
writes (its database, its working directory, the files the hook keeps)
goes into a temporary directory removed on close, so it never touches
state you rely on.

The binaries are the ones pheo-oats ships, and a command is classified by
pheo-oats' own `classify`, so the space, `oats scan` and `oats-scan` read
every command the same way.
"""
import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


class ScanError(Exception):
    """Something the person running this can act on."""


def pheo_oats_bin():
    """Where pheo-oats keeps the classifier binaries for this platform."""
    import pheo_oats

    return Path(pheo_oats.__file__).resolve().parent / "_bin"


def binary_path(name):
    """The classifier binary: from OATS_SCAN_BIN_DIR or PHEO_OATS_BIN_DIR
    when set, otherwise the one pheo-oats installed."""
    filename = name + (".exe" if os.name == "nt" else "")
    candidates = []
    for variable in ("OATS_SCAN_BIN_DIR", "PHEO_OATS_BIN_DIR"):
        override = os.environ.get(variable)
        if override:
            candidates.append(Path(override) / filename)
    try:
        candidates.append(pheo_oats_bin() / filename)
    except ImportError:
        pass
    for candidate in candidates:
        if candidate.is_file():
            # Only when it cannot already run: chmod needs ownership, and a
            # service running as a non-root user over root-owned packages
            # (the hardened container pheo-context ships) gets EPERM here
            # and boots with no classifier.
            if os.name != "nt" and not os.access(candidate, os.X_OK):
                try:
                    candidate.chmod(candidate.stat().st_mode | 0o111)
                except OSError:
                    pass
            return candidate
    raise ScanError(
        "No classifier for this machine: {} is not where pheo-oats keeps it.\n"
        "\n"
        "The classifier ships compiled inside pheo-oats, one build per\n"
        "platform. Install pheo-oats for this platform (pip install --upgrade\n"
        "oats-scan pulls it in), or point OATS_SCAN_BIN_DIR at a directory\n"
        "holding pheo-action-gateway and oatsctl.".format(filename)
    )


def require_pheo_oats():
    """Fail at start, not one command at a time.

    classify() asks pheo-oats' `classify`, which takes the hook's home
    directory from 0.7.1. Against an older pheo-oats every question would
    fail and read as "no answer" for the life of the resolver; better to
    refuse to start and say which version is needed.
    """
    import inspect

    try:
        from pheo_oats.scan import classify
    except ImportError as error:
        raise ScanError("oats-scan needs pheo-oats 0.7.1 or newer ({}).".format(error)) from None
    if "home" not in inspect.signature(classify).parameters:
        raise ScanError("oats-scan needs pheo-oats 0.7.1 or newer: "
                        "pip install --upgrade pheo-oats")


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
    """A local classifier process, running for as long as it is used.

    Used as a context manager, or with __enter__() and close(). On exit the
    process is terminated and its temporary directory removed, including on
    an exception or a Ctrl-C.
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
        require_pheo_oats()
        self.database = os.path.join(self.workdir, "resolver.db")

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
                "The classifier will not run on this machine ({}).\n"
                "\n"
                "This pheo-oats install was built for a different operating "
                "system or architecture. Install pheo-oats for this "
                "platform.".format(error)
            ) from None

        deadline = time.time() + 30
        while time.time() < deadline:
            if self.process.poll() is not None:
                code = self.process.returncode
                self.close()
                raise ScanError(
                    "The classifier exited during startup (code {}).".format(code)
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

        The question goes through the agent hook, exactly as `oats scan`
        asks it; the hook's own small files go into this resolver's
        temporary directory rather than the home directory.
        """
        from pheo_oats.scan import classify

        try:
            oatsctl = str(binary_path("oatsctl"))
        except ScanError:
            return None
        return classify(oatsctl, self.url, self.room, command, label_to_key,
                        home=self.workdir)

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.database = None
        if getattr(self, "workdir", None):
            shutil.rmtree(self.workdir, ignore_errors=True)
            self.workdir = None

    def __exit__(self, *exc):
        self.close()
        return False
