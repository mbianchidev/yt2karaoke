# Accessibility

yt2karaoke aims for WCAG 2.2 Level AA in the browser studio and stage window.
This is a contribution target, not a certification or a claim that the studio
has passed an audit. The CLI and exported media have their own considerations
below.

## Contribution guidelines

- Use semantic HTML, a logical heading order, and visible labels or accessible
  names for every control. Keep the document `lang` attribute accurate.
- Keep every studio task usable with a keyboard alone: Tab order, visible
  `:focus-visible` outlines, the **Skip to studio** link, and native controls
  (buttons, range inputs, selects) before custom widgets.
- Announce progress, success, and errors through the existing `role="status"`
  and `role="alert"` regions without stealing focus or interrupting playback.
- Never use color as the only signal. Queue states, mic state, and errors
  need text. Meet AA contrast in both light and dark themes.
- Support browser zoom and narrow layouts down to 320 CSS pixels. Honor
  `prefers-reduced-motion`.
- Keep microphone capture, monitoring, and pop-up windows opt-in and clearly
  labelled. Explain blocked permissions in text.
- Rendered karaoke videos highlight the sung word in yellow on white text. Keep
  timed lyrics available as text (JSON, LRC, and ASS exports and the
  **View synced lyrics** panel) so lyrics are not only available as pixels.
- CLI output must remain readable without color or emoji; errors should state
  the problem and how to fix it.

## Verification

Run the [deterministic test suite](docs/development.md#checks). The Playwright
studio tests in `tests/e2e/test_studio.py` run in light and dark color schemes
and cover keyboard theme selection, keyboard operation of the vocal and mixer
sliders, the skip link, dark-theme text and control contrast ratios, and
responsive layouts at 320 to 1440 pixel widths.

These automated Chromium checks do not establish full WCAG conformance or
screen-reader support. For UI changes, also check manually:

1. Complete the main journeys (add a YouTube link or local file, play, adjust
   the vocal mix, enable and disable the microphone, open the stage window,
   reorder and remove songs) with Tab, Shift+Tab, Enter, Space, and arrow keys.
2. Listen to labels, headings, and status/error announcements with VoiceOver
   on macOS or NVDA/Narrator on Windows.
3. Check 200% zoom, 320 CSS-pixel reflow, visible focus, reduced motion, and
   contrast in both themes, including disabled, selected, and error states.

## Known limitations and reporting

There is no completed independent accessibility audit or screen-reader test
matrix. The rendered video's lyric highlighting is a visual effect, and
microphone, speaker, and display selection depend on browser support.

Report barriers with the
[bug report form](https://github.com/mbianchidev/yt2karaoke/issues/new?template=bug_report.yml).
Include the task, browser and operating system, any assistive technology and
its version, steps to reproduce, and the expected behavior. Use synthetic media
and sanitized screenshots. Use [SECURITY.md](SECURITY.md) instead if a report
exposes a vulnerability.
