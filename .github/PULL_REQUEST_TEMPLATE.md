## Summary

<!-- What problem does this solve, and how? Link the issue, for example "Fixes #123". -->

## Changes

-

## Checks

<!-- Tick what you ran. State anything you could not verify, such as other platforms or the live YouTube test. -->

- [ ] `python -m pytest tests -m "not live_youtube"`
- [ ] `node --check` for changed files in `src/yt2karaoke/player/static/`
- [ ] Manual studio check for UI changes, following [ACCESSIBILITY.md](https://github.com/mbianchidev/yt2karaoke/blob/main/ACCESSIBILITY.md)
- [ ] Documentation updated for changed behavior, options, or setup

## Contributor checklist

- [ ] Tests and fixtures use generated media and original test lyrics only.
- [ ] No credentials, cookies, personal data, or copyrighted recordings are included.
- [ ] I reviewed and can explain every change, including AI-assisted work ([AI policy](https://github.com/mbianchidev/yt2karaoke/blob/main/README.md#ai-policy)).
