# oats-scan

**See what the agent skills on your machine tell an AI agent to run.**

```bash
pip install oats-scan
oats-scan
```

Thirty seconds. No account, no sign up, no configuration, and nothing leaves
your machine.

## You already installed these

Agent skills are markdown files that tell an AI what commands to run on your
computer. You install them the way people installed browser extensions in 2010:
on a recommendation, without reading them.

Your agent reads them. You usually don't.

`oats-scan` reads them for you. Here is a real run on a working laptop:

```
  Scanning 3 installed skill locations and my-project

  4331 files, 1528 command blocks. Classifying ...

  What these instruct an agent to do

    Destructive command              4   always needs a person
    Remote code execution           13   always needs a person
    Credential access                2   always needs a person
    Shell command                 1506
    Read                             3

  19 of 1528 actions, in 3 classes, can never run unattended.
  Those are the ones worth your attention.
```

Nineteen. In plugins from well known vendors, all of them legitimate. One is
this line, sitting in an installed skill, waiting for the agent to decide to
run it:

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

Python 3.9 or newer. No other dependencies: `pip list` will show `oats-scan`
and nothing else.

**Platform support.** The classifier is compiled, so each platform has its own
wheel and `pip` downloads only yours.

| Platform | Wheel |
|---|---|
| macOS, Apple Silicon and Intel | universal |
| Linux x86-64 | yes |
| Linux aarch64 | yes |
| Windows x86-64 | yes |

**Working from source.** This repository holds the Python and the tests; the
compiled classifier is not committed, which is why a clone is small and fast.
To run against a source checkout, install the package for the binaries and put
the checkout ahead of it:

```bash
git clone https://github.com/pheo-ai/oats-scan
cd oats-scan
pip install oats-scan
PYTHONPATH=src python3 -m oats_scan --files
```

Or point `OATS_SCAN_BIN_DIR` at a directory holding `pheo-action-gateway` and
`oatsctl`.

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

Every command is sorted into one of 33 **consequence classes**, each carrying a
severity from 0 to 100. Classes at or above 75 are the ones that can never
become routine, however well an agent has behaved. Those are what
`always needs a person` marks.

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

The full list of 33 classes ships with the package as
`oats_scan/data/action-classes.json`.

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
[Pheo OATS](https://pheo.ai), which is the gateway this classifier normally
lives in. `oats-scan` is the view. The gateway is the brake. Start with the
view.

## Licence

The Python source in this repository is MIT. The compiled classifier bundled in
the published wheels is proprietary software of Pheo Inc., redistributable as
part of an unmodified `oats-scan` wheel. See [LICENSE](LICENSE).
