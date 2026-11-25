# Contributing to yt2karaoke

Thanks for helping. Bug reports, documentation fixes, accessibility
improvements, tests, and focused features are all welcome. Please follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Issues and proposals

Search [existing issues](https://github.com/mbianchidev/yt2karaoke/issues)
first, then use the
[bug report](https://github.com/mbianchidev/yt2karaoke/issues/new?template=bug_report.yml)
or [feature request](https://github.com/mbianchidev/yt2karaoke/issues/new?template=feature_request.yml)
form. Open an issue to discuss substantial changes before implementing them.
Issues labelled `good first issue` or `help wanted` are good starting points.

Report vulnerabilities privately through [SECURITY.md](SECURITY.md), never in a
public issue. Report conduct concerns using the private contact in the
[Code of Conduct](CODE_OF_CONDUCT.md).

Never attach copyrighted recordings, real lyrics you do not own, browser
cookies, credentials, or personal data to issues, pull requests, or tests.

## Development

Coding agents must read [AGENTS.md](AGENTS.md) before editing. Everyone should
start with the [documentation index](docs/README.md) and the
[development guide](docs/development.md), which covers:

- Python 3.11 to 3.14 (3.14 recommended), ffmpeg/ffprobe, and Node.js 22+ or
  Deno 2.3+ for YouTube extraction and JavaScript checks.
- An editable install with `python -m pip install -e ".[dev]"` and Playwright
  Chromium for browser tests.
- Deterministic unit, media, and browser tests; the opt-in live YouTube test;
  JavaScript syntax checks; and package builds.
- Architecture, bundled third-party assets, CI, and the release process.

Use generated media (for example sine tones) and original test lyrics in tests.
Follow [ACCESSIBILITY.md](ACCESSIBILITY.md) for studio and stage changes.

## Pull requests

1. Fork the repository or create a branch, and keep each pull request focused
   on one change.
2. Add or update tests for changed behavior and update the relevant docs,
   CLI help, and examples.
3. Run the [checks](docs/development.md#checks) that apply:
   `python -m pytest tests -m "not live_youtube"` at minimum, plus
   `node --check` for changed studio scripts.
4. Open the pull request using the template. Explain the problem, the solution,
   and the checks you ran, and state anything you could not verify.
5. The **CI** workflow runs on every pull request and must pass. The live
   full-song YouTube workflow is manual only, because YouTube blocks hosted
   runners; maintainers may run it by hand or ask for a local
   `pytest tests/live -m live_youtube` result. See
   [Full-song CI](docs/development.md#full-song-ci).
6. Respond to review feedback and keep CI green.

There is no separate formatter or linter configured; follow the surrounding
code style. Do not commit generated media, build output, model weights, or
local configuration.

You are responsible for all work you contribute, including AI-assisted
contributions, as described in the [AI policy](README.md#ai-policy).

## License

yt2karaoke is released under the [MIT License](LICENSE). Keep the license
notices for the bundled fonts (SIL Open Font License 1.1) and the Socket.IO
client (MIT) with those assets.
