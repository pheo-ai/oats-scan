"""Read what the agent skills on this machine tell an agent to do.

Prose is ignored. "This skill can delete your notes" is a sentence, not an
action. Only fenced shell content counts, which is why these numbers are a
floor rather than an estimate.

The extraction here is the one from the published measurement study, so a
number printed by this tool and a number printed in that paper mean the
same thing.
"""
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from oats_scan.gateway import Resolver, ScanError

DATA = Path(__file__).resolve().parent / "data" / "action-classes.json"

# Files that instruct an agent: skill and rule files by name, plus ordinary
# markdown, which is where install instructions actually live.
INSTRUCTION_NAMES = {
    "skill.md", "agents.md", "claude.md", "gemini.md", "agent.md",
    ".cursorrules", ".windsurfrules", ".clinerules", ".aiderrules",
}

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist",
    "build", "target", ".tox", ".mypy_cache", ".pytest_cache", "vendor",
    ".next", ".nuxt", "site-packages", ".cargo", ".rustup", ".gradle",
}

MAX_FILES = 4000

# Where agents keep the skills a person has installed. With no path given,
# these are what oats-scan reads. The question worth answering is not
# "what is in this repository" but "what did I install, and what does it
# tell my agent to run".
INSTALLED_SKILL_DIRS = [
    "~/.claude/skills", "~/.claude/plugins", "~/.claude/commands",
    "~/.cursor", "~/.codex", "~/.openclaw", "~/.aider", "~/.windsurf",
    "~/.config/claude", "~/.gemini", "~/.continue",
]

SHELL_LANGS = {"bash", "sh", "shell", "zsh", "console", "terminal", "shell-session"}

COMMAND_START = re.compile(
    r"^\s*(?:sudo\s+)?(?:curl|wget|git|npm|npx|pnpm|yarn|pip[0-9.]*|python[0-9.]*|node|go|cargo|"
    r"brew|apt|apt-get|docker|kubectl|gh|aws|gcloud|az|rm|cp|mv|mkdir|cat|echo|export|source|"
    r"chmod|chown|ssh|scp|rsync|tar|unzip|make|bash|sh|zsh|open|osascript|security|defaults|jq)\b"
)

SEP = re.compile(r"(?:\s|\\[nrt])+")


def installed_skill_roots():
    """Agent skill directories that exist on this machine."""
    return [p for p in (Path(d).expanduser() for d in INSTALLED_SKILL_DIRS) if p.is_dir()]


def _strip_leading_sep(text):
    match = SEP.match(text)
    return text[match.end():] if match else text


def fenced_blocks(text):
    """Executable regions of an instruction file, as raw strings.

    Odd-indexed segments of a ```-split are fence bodies. Whether a fence
    carried a language tag shows up in the character following the opening
    ```: a newline when untagged, the tag otherwise. A body opening with
    whitespace therefore had no tag and must itself open like a command,
    because bare fences also carry sample output, JSON and file listings.
    """
    out = []
    parts = text.split("```")
    for i in range(1, len(parts), 2):
        raw = parts[i]
        body = raw.strip()
        if not body:
            continue
        if SEP.match(raw):
            body = _strip_leading_sep(body)
            if not COMMAND_START.match(body):
                continue
        else:
            head = SEP.split(body, 1)
            first, rest = head[0], (head[1] if len(head) > 1 else "")
            if first.lower() not in SHELL_LANGS:
                # Some other language. Whatever its tag spells, the content
                # is not a shell command string.
                continue
            body = rest.strip()
        if not body or not COMMAND_START.search(body):
            continue
        out.append(body[:2000])
    return out


def instruction_files(root):
    """Files under root that instruct an agent."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".egg")
        ]
        for name in filenames:
            lowered = name.lower()
            if lowered in INSTRUCTION_NAMES or lowered.endswith(".md"):
                found.append(Path(dirpath) / name)
                if len(found) >= MAX_FILES:
                    return found
    return found


def collect(roots):
    """Every command block under every root, with the file it came from."""
    files, work = [], []
    for root in roots:
        for path in instruction_files(root):
            files.append(path)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for block in fenced_blocks(text):
                work.append((path, block))
    return files, work


def run(args):
    if args.path:
        root = Path(args.path).expanduser().resolve()
        if not root.is_dir():
            raise ScanError("Not a directory: {}".format(root))
        roots, where = [root], str(root)
    else:
        roots = installed_skill_roots()
        here = Path.cwd()
        if here not in roots:
            roots.append(here)
        where = "{} installed skill location{} and {}".format(
            len(roots) - 1, "" if len(roots) == 2 else "s", here.name
        )

    classes = json.loads(DATA.read_text())
    label_to_key = {c["label"]: c["key"] for c in classes}
    by_key = {c["key"]: c for c in classes}

    def status(line=""):
        print(line, file=sys.stderr if args.json else sys.stdout)

    files, work = collect(roots)

    status("")
    status("  Scanning {}".format(where))
    status("")

    if not work:
        if args.json:
            print(json.dumps({
                "roots": [str(r) for r in roots], "files": len(files),
                "blocks": 0, "unresolved": 0, "classes": {},
                "review_actions": 0, "review_classes": 0,
            }, indent=2))
            return 0
        print("  {} files read, no commands found.".format(len(files)))
        print("")
        print("  Nothing here instructs an agent to run anything. That is a")
        print("  normal result for a machine without agent skills installed.")
        print("")
        return 0

    status("  {} files, {} command blocks. Classifying ...".format(
        len(files), len(work)))

    with Resolver() as resolver:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(
                lambda item: resolver.classify(item[1], label_to_key), work
            ))

    return report(args, roots, files, work, results, by_key)


def report(args, roots, files, work, results, by_key):
    counts, per_file, unresolved = {}, {}, 0
    for (path, _block), key in zip(work, results):
        if key is None:
            unresolved += 1
            continue
        counts[key] = counts.get(key, 0) + 1
        per_file.setdefault(path, set()).add(key)

    review = {k: n for k, n in counts.items() if not by_key[k]["graduates"]}
    review_total = sum(review.values())

    if args.json:
        print(json.dumps({
            "roots": [str(r) for r in roots],
            "files": len(files),
            "blocks": len(work),
            "unresolved": unresolved,
            "classes": {
                k: {"count": n, "label": by_key[k]["label"],
                    "severity": by_key[k]["severity"],
                    "graduates": by_key[k]["graduates"]}
                for k, n in counts.items()
            },
            "review_actions": review_total,
            "review_classes": len(review),
        }, indent=2))
        return 1 if (args.strict and review_total) else 0

    print("")
    print("  What these instruct an agent to do")
    print("")
    for key, n in sorted(counts.items(),
                         key=lambda kv: (-by_key[kv[0]]["severity"], -kv[1])):
        meta = by_key[key]
        flag = "always needs a person" if not meta["graduates"] else ""
        print("    {:<28} {:>5}   {}".format(meta["label"][:28], n, flag))
    if unresolved:
        print("    {:<28} {:>5}   (counted separately)".format("unresolved", unresolved))
    print("")

    if review_total:
        print("  {} of {} actions, in {} class{}, can never run unattended.".format(
            review_total, len(work), len(review),
            "" if len(review) == 1 else "es"))
        print("  Those are the ones worth your attention.")
    else:
        print("  Every action here belongs to a class that can become routine.")
    print("")

    interesting = [
        (p, ks) for p, ks in per_file.items()
        if any(not by_key[k]["graduates"] for k in ks)
    ] if args.files else []
    if interesting:
        print("  Where")
        print("")
        for path, keys in sorted(interesting)[:30]:
            shown = sorted((k for k in keys if not by_key[k]["graduates"]),
                           key=lambda k: -by_key[k]["severity"])
            rel = path
            for r in roots:
                try:
                    rel = path.relative_to(r)
                    break
                except ValueError:
                    continue
            print("    {}".format(rel))
            print("      {}".format(", ".join(by_key[k]["label"] for k in shown)))
        if len(interesting) > 30:
            print("    ... and {} more".format(len(interesting) - 30))
        print("")

    print("  Everything here is normal software doing normal things. This is")
    print("  what your agent is instructed to do, made visible. Nothing was")
    print("  sent anywhere and nothing was changed.")
    print("")
    print("  These counts are a floor. Only fenced shell content is read, and")
    print("  a block is skipped unless its first command is a recognised one,")
    print("  so the real number is this or higher.")
    print("")

    return 1 if (args.strict and review_total) else 0
