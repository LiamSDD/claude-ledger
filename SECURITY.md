# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.2.x | Yes |
| 0.1.x and older | No |

Fixes are released as a new patch version of the latest supported line.

## Reporting a vulnerability

Please report vulnerabilities privately. Do not open a public issue, pull request or discussion for them.

1. Go to the repository's **Security** tab on GitHub.
2. Choose **Report a vulnerability** to open a private advisory through GitHub private vulnerability reporting.
3. Include the version (`claude-ledger --version`), your Python version and operating system, the steps to reproduce, and if possible a minimal synthetic transcript that triggers the problem. Never attach real transcripts: they can contain your prompts, code and file paths.

You should get an acknowledgement within 7 days. Once the issue is confirmed, a fix and a published advisory follow as soon as practical, and you are credited unless you ask not to be.

## Scope

`claude-ledger` is a read-only, offline tool. It reads JSONL transcripts under a projects directory, an optional `--prices` JSON file and Claude Code's agent metadata files, and prints a report to stdout. It never writes to those files, makes no network connections and has no runtime dependencies.

Because transcripts can come from anywhere (shared, synced or copied from another machine), their content is treated as untrusted input. The following count as vulnerabilities:

- **Terminal escape injection.** Values taken from transcripts, such as model IDs, working directories, session IDs or agent types, reaching table, CSV or any other output with control characters or ANSI escape sequences intact, so that a crafted transcript can rewrite the terminal, hide output or change the window title.
- **Crashes or hangs on malicious content.** A crafted transcript, metadata file or price file that makes the tool raise an unhandled exception, loop forever or use memory far out of proportion to the input, instead of skipping the bad data.
- **Path handling.** Reading files outside the projects directory and the explicit `--prices` file, for example by following crafted file names or metadata, or any situation in which the tool writes, moves or deletes a file.
- **Spreadsheet formula injection.** CSV output that lets a crafted value run as a formula when opened in a spreadsheet.
- **Any network access** or any execution of code or commands taken from input files.

The following are out of scope:

- Cost figures that differ from your bill. These are estimates; see the FAQ in the README, and report wrong prices as a normal issue.
- Problems that need an attacker who can already run code as your user or write to your Python environment.
- Vulnerabilities in Python itself or in development-only tools such as `pytest`.
