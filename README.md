# oats-scan

**See what the agent skills on your machine tell an AI agent to run.**

```bash
pip install oats-scan
oats-scan
```

Thirty seconds. No account, no sign up, no configuration, and nothing leaves
your machine.

**oats-scan is now the same scanner as `oats scan` in
[pheo-oats](https://pypi.org/project/pheo-oats/).** `pip install oats-scan`
installs pheo-oats, and `oats-scan` runs `oats scan` with the flags, defaults
and exit codes it always had, so the two print the same numbers. If you
already use pheo-oats, `oats scan` is all you need.

## You already installed these

Agent skills are markdown files that tell an AI what commands to run on your
computer. You install them the way people installed browser extensions in 2010:
on a recommendation, without reading them.

Your agent reads them. You usually don't.

`oats-scan` reads them for you. On a working laptop it found 1,528 commands
in 4,331 files, and 19 of them in classes that can never run unattended.
Nineteen. In plugins from well known vendors, all of them legitimate. Here is
what a run looks like, on a single skill file:

```
  Scanning /home/you/skills

  1 files, 5 shell blocks. Classifying ...

  What these instruct an agent to do

    Remote code execution             1   never graduates
    Credential access                 1   never graduates
    Shell command                     3

  2 of 5 actions, in 2 classes, can never run unattended.
  Those are the ones a person has to approve, every time.
```

One of the laptop's nineteen is this line, sitting in an installed skill,
waiting for the agent to decide to run it:

```bash
curl -fsSL https://downloads.cursor.com/origin/install.sh | sh
```

Nothing there is an attack. That is the point. **You still want to know.**

```bash
oats-scan --files      # which skill each one came from
```

## Install

```bash
pip install oats-scan
```

Python 3.9 or newer. oats-scan itself is pure Python; it installs pheo-oats,
which carries the compiled classifier.

**Platform support** is pheo-oats': wheels for macOS (Apple silicon and
Intel), Linux x86-64, Linux aarch64 and Windows x86-64, and `pip` downloads
only yours.

**Working from source.** This repository holds the Python and the tests. To run
a source checkout, install pheo-oats for the classifier and put the checkout
ahead of it:

```bash
git clone https://github.com/pheo-ai/oats-scan
cd oats-scan
pip install pheo-oats
PYTHONPATH=src python3 -m oats_scan --files
```

Or point `OATS_SCAN_BIN_DIR` at a directory holding `pheo-action-gateway`,
`oatsctl` and `pheo-mcp-github`.

## What it looks at

With no arguments it reads the agent skills installed on this machine:
`~/.claude`, `~/.cursor`, `~/.codex`, `~/.openclaw`, `~/.aider`, `~/.windsurf`,
`~/.gemini`, `~/.continue`, plus the directory you are standing in.

Give it a path to read somewhere specific:

```bash
oats-scan ~/my-project
oats-scan --json                 # machine readable
oats-scan --strict               # exit 1 if anything needs review, for CI
```

## How it decides

Every command is sorted into a **consequence class**, each carrying a severity
from 0 to 100. Classes at or above 75 are the ones that can never become
routine, however well an agent has behaved. Those are what `never graduates`
marks.

Some things you can take back:

- Agent writes a bad document, you fix the document
- Agent opens a pull request, you close it

Some you can't:

- Agent deletes a folder, the files are gone
- Agent pushes to production, your customers already saw it
- Agent reads your password file, it has your password now
- Agent runs a script off the internet, whatever it did, it did

The classifier is deterministic. No model, no inference, no network call. It
reads the command string and nothing else, so the same command produces the
same class today, next year, and on your machine. Any result can be re-derived
without re-running anything.

The full list of classes ships with pheo-oats as
`pheo_oats/data/action-classes.json`, the same list the Pheo space and the
OATS gateway rule with.

## What it tells you, and what it leaves to you

`oats-scan` reports the **class** of each action. It does not decide whether
that action is acceptable, because that answer is yours.

A startup will let an agent install packages all day. A bank will not let one
read a credential file, ever. Both are right. They are different companies with
different blast radii. So this gives you the view and leaves the limit to you.

Everything it reports is normal software doing normal things. Installers
download and run code, because that is what installers are for. Some of those
actions happen to be ones you cannot undo, and those are the ones worth a look.

## How it works with your other tools

`oats-scan` reads actions. Registry scanners read artifacts. The two see
different things and both are worth having.

Scanners are the right tool for harm that never becomes an action: a hardcoded
recipient, an undisclosed scope, an instruction written to talk an agent into
misbehaving. `oats-scan` is the right tool for what the agent then goes and
does. Run both and you cover both.

## Honest limits

**These counts are a floor.** Only fenced shell content is read. Prose is
ignored, because "this skill can delete your notes" is a sentence rather than
an action. A block is skipped unless its first command is a recognised one. The
real number is what you see here or higher.

**Precision is 92%**, with a 95% confidence interval of [84.8, 96.5] on a
hand adjudicated sample of 100. The known failure mode is content that looks
like a command inside a heredoc. When that happens the extra line is visible in
`--files`, so you can see it and judge for yourself.

**Unresolved blocks are counted separately.** A block the classifier could not
read is reported on its own line rather than folded in with the clean ones.

## Privacy

Everything runs on your machine. The classifier is a local process listening on
127.0.0.1, started for the length of the scan and shut down afterwards. It
writes to a temporary database that is deleted when the scan ends, so a scan
never touches state you rely on. No telemetry, no account, no network calls.

## Where this comes from

The classifier is the resolver from the
[Open Agent Trust System](https://github.com/pheo-ai/open-agent-trust-system),
the same one that runs in front of live agents deciding whether an action
executes. The measurement study behind the class list covers 66,192 public
agent skills, and the classification of all of them is published as
[pheo-ai/clawhub-consequence-classes](https://huggingface.co/datasets/pheo-ai/clawhub-consequence-classes).

Once you can see what your agent is told to do, the next question is usually
whether something can hold an action while you look at it. That is
[Pheo OATS](https://pheo.ai), the gateway this classifier normally lives in,
and it is already installed: `oats quickstart claude` starts it. `oats-scan` is
the view. The gateway is the brake. Start with the view.

## Licence

The Python source in this repository is MIT. The compiled classifier is part of
pheo-oats, proprietary software of Pheo Inc. installed as a dependency under
its own terms. See [LICENSE](LICENSE).
