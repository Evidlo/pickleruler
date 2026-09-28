# pickleruler

Screen ruler / protractor / area meter / plot digitizer. Two independent implementations kept in feature parity:
- `pickleruler.py`: i3/X11 app; screenshots the screen (or opens an image) fullscreen and measures on it.
- `index.html` (GitHub Pages): single-file browser app (no deps); image via getDisplayMedia window capture
  (snapshot or live), paste, drop or open. Same keys; `E` report / `P` annotated PNG replace stdout.
  Welcome clips: `examples/*_anim.png` ← `dev/record_clip.py` (framed via `dev/capture_frame.py`);
  `dev/embed_examples.py` inlines them as WebP between `<!-- examples:start/end -->`.

## Constraints
- Python: stdlib + tkinter + Pillow (`xclip` optional); X11 only, frozen screenshot; HUD inside the fullscreen window.

## Layout of `pickleruler.py`
- Module level: pure geometry/calibration helpers (`seg_param`, `polyline_foot`, `cal_answer`, `cal_value`...).
- `Ruler`: shapes are dicts `{kind, pts, cal, axis}` in *image* pixel coords; `c()`/`i()` convert to/from canvas.
- `redraw(full)` → `flush()`; tags `ov` = shapes, `cur` = cursor overlay. HUD `rich()`: `{k}` bold key, `§` swatch.
- One image scale `scale_k = (units/px, unit)`, fixed when any line/path/circle/area is calibrated with a
  second value (`scale_src` = that shape). Other shapes' `cal = {v0, dir, cw}` is just a start offset.
  Digitizer axes are independent: `cal = {v0, v1, log, unit}` via `cal_value`. Hover readouts: `hover_info`.

## Testing
- `python3 dev/smoke_test.py [shot.png]`: drives the app on a synthetic plot on the live X display (no Xvfb);
  Tk callback exceptions count as failures; don't touch mouse/keyboard while it runs.
- `dev/web_test.sh [shot.png]`: injects `dev/web_harness.html` into `index.html`, headless Chromium
  (`--password-store=basic`). Firefox: `--headless --no-remote --profile <tmpdir>`. Capture: test by hand.

## Conventions
- Bump `VERSION` (0.0.x, same in both files) each change; log changes and ideas in `WORKLOG.md` (newest first).
  Terse style, no narrative comments; no eager `* bool(x)` rows.
