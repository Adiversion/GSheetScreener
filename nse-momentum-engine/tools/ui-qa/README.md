# Responsive UI QA harness

Headless-Chrome harnesses that measure the real rendered layout of `app/index.html`
inside an iframe at a chosen viewport width. They report **metrics**, not screenshots,
so regressions are caught by CI or by eye in the terminal.

## Running

Serve the repo root (the harness loads the app relative to itself, and same-origin
access is required to read the iframe's DOM):

```bash
python -m http.server 8001 --bind 127.0.0.1
```

Then dump the result for any width:

```bash
CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"
"$CHROME" --headless=new --disable-gpu --no-sandbox --virtual-time-budget=16000 \
  --dump-dom "http://127.0.0.1:8001/tools/ui-qa/tabsweep.html?w=390" | grep -o 'TABS:{.*}'
```

## Harnesses

| File | Answers |
| --- | --- |
| `tabsweep.html` | Per-tab (`Signal`/`Portfolio`/`History`/`Settings`) horizontal scroll + off-screen controls. The main regression gate. |
| `measure.html` | Terminal tab detail: table fit, single-line numeric cells, card mode, touch-target size, root font size. |
| `scrolltest.html` | Whether the page can *actually* scroll sideways (an honest overflow test). |
| `offenders.html` | Which elements extend past the viewport, plus the ancestor chain (`overflow`, `min-width`) of the GTT table. |
| `bisect.html` | Hides candidate subtrees to find which one causes page overflow. |
| `drill.html` | Greedily drills from `.gtt-card` down to the single element causing overflow. |
| `probe.html` | Per-column widths of the leaders table and the header control widths. |
| `debug.html` | Computed styles and column widths for the leaders table. |

## Widths worth sweeping

`320 360 390 430 640 768 1024 1280 1366 1440 1920 2560 3840`

## Two traps this harness exists to catch

1. **Inline `display` set from JS beats width-gated CSS.** `renderMarketRegime()`
   used to set `ticker.style.display = 'inline-flex'`, which overrode both the base
   `display: none` and the `@media (min-width: 1536px)` gate — pushing the refresh
   button to x=677 on a 360px phone. Toggle a class instead.
2. **`repeat(N, 1fr)` cannot shrink.** `1fr` means `minmax(auto, 1fr)`, so a track
   floors at its content's min-content width and overflows narrow viewports. Use
   `minmax(0, 1fr)` (or `auto-fit` + a minimum) for anything that must fit a phone.
