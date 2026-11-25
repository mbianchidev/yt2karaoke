# Security policy

## Supported versions

| Version or branch | Receives security fixes |
| --- | --- |
| `main` | Yes |
| Latest published [GitHub Release](https://github.com/mbianchidev/yt2karaoke/releases) | Yes, fixes ship in a newer release |
| Older releases | No, upgrade to the latest release |

## Report a vulnerability privately

Use GitHub's
[private vulnerability reporting form](https://github.com/mbianchidev/yt2karaoke/security/advisories/new).
Sign in to GitHub to submit a report. Do not publish vulnerability details in a
public issue, pull request, or discussion.

Include:

- The affected version (`yt2karaoke --version`) or commit, operating system,
  Python version, and whether you used the CLI, the studio, or the Python API.
- How the studio was started, including `--host` and `--port`, if relevant.
- The impact and affected component, for example uploads, media or lyric
  routes, the queue API, YouTube downloads, or the optional track2stem client.
- Minimal reproduction steps using generated audio (for example sine tones)
  and original test lyrics.
- Relevant redacted logs or a small proof of concept. Never include
  credentials, browser cookies, copyrighted recordings, or other people's data.

The studio is a local development server. It binds to `127.0.0.1` by default
and the [usage guide](docs/usage.md#from-a-source-checkout) warns against
exposing it publicly.

## Response and disclosure

Reports are handled on a **best-effort basis**, without a guaranteed
acknowledgment, update, or remediation timeline. Maintainers may request more
information through the private report and coordinate any fix and release
there.

Keep details private while coordinating with maintainers. Publish after a fix
is available or on a disclosure date agreed in the private report. There is no
fixed disclosure window.

For non-security bugs, follow the [contribution guide](CONTRIBUTING.md).
