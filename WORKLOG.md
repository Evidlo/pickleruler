# Worklog

Newest first.

## 2026-09-28 — every drawn point snaps (0.0.8, both versions)
- Hover dot now also shows while a shape is in progress, and every point snaps to it (line end, path/area
  vertices, angle arms, circle edge); preview follows. Hover snap wins over Shift 45°.
- py `find_hover(x, y)` takes the canvas point (release events don't update `self.mouse`); `cursor_point`
  shared by preview and clicks. Tests: snap check now covers both points of a line.

## 2026-09-28 — start new shapes on the hover snap point (0.0.7, both versions)
- If the white hover dot (`find_hover` foot) is showing when a shape's first point is placed, the point
  goes on the dot instead of the cursor (py `event_point`, JS `cursorPoint`). Applies to every drawing
  tool, including digitizer points.
- Tests: one check in each suite.

## 2026-09-28 — repo layout for commit / GitHub Pages
- Web app is to be served as `index.html` (user renaming `pickleruler.html` → `index.html` for gh-pages);
  all scripts and docs now reference `index.html`.
- Dev tooling moved to `dev/`: `smoke_test.py`, `web_test.sh`, `web_harness.html`, `embed_examples.py`,
  plus the clip helpers `capture_frame.py` (static red frame for positioning) and `record_clip.py`
  (countdown + 1 s ping-pong APNG). Scripts resolve the repo root as `dev/..`, so run them from anywhere.
- Added `.gitignore` (`__pycache__/`). Both suites verified from `dev/` via a temporary index.html link.

## 2026-09-28 — welcome-screen example clips (0.0.6)
- Recorded three 300×200 1-second clips at 1× (user-positioned in a red on-screen frame; 5 s countdown,
  20 fps, looped forward then reverse): `examples/{distance,area,angle}_anim.png` (APNG originals).
  Content: flood-gauge post with a 5 ft reference; map building area with a 20 m reference; protractor on
  the Antikythera mechanism photo. `examples/area.png` is an earlier still, unused.
- `embed_examples.py` converts them to animated WebP q70 (APNG was up to 2.9 MB; WebP ~0.1–0.2 MB each)
  and inlines them between `<!-- examples:start/end -->` markers. The page is now ~0.5 MB.
- Clip borders drawn outside the 300×200 image so clips display 1:1 (were squeezed to 298×198).

## 2026-09-28 — HUD tweaks + welcome placeholders (0.0.4)
- HUD help/scale rows restored to the pre-0.0.2 wording (minus `s`) at user request (0.0.3).
- Cursor row shows `img W×H` (both versions; web dropped the source label). "[scale ref]" removed from
  readouts; the canvas "(ref)" label marks the reference.
- HUD text selectable: web `user-select: text`, re-render skipped when unchanged; Python Text widgets skip
  unchanged re-renders and Ctrl+C copies the selection.
- Tool row ends with `c Calibrate` (both); web "Capture window" button removed (`w` key kept).
- Web welcome: removed the maim/xclip tip; added three 300×200 placeholder boxes with captions
  (measure distances / area / angles) for the example screenshots. Python stays resource-free.

## 2026-09-28 — one image scale (0.0.2, both versions)
- Units model reworked around a single image scale (user stories: m² of a building from a map's scale bar;
  a distance in a photo from a known length). Calibrating any line/path/circle with two values, or an area
  with a known area, fixes `units/px` for the whole image; all existing and future shapes report in it.
- Blank point 2 on an already scaled image: keeps the scale, sets only this shape's start value (offset);
  the units step is skipped. Blank point 1: clears this shape; on the reference it clears the image scale.
- Scale is fixed at calibration (not live-following the reference) so the earlier "area calibration holds
  after resizing" request still holds; re-press `c` on the reference to re-fit. Reference shows "(ref)".
- Digitizer axes stay independent value mappings (log allowed) and never set the scale. `s` key removed.
- Photos: a linear reference is only valid at its own depth/plane; perspective (rectangle/homography)
  reference parked by user decision.
- Also this session: grab-target highlight (handle ring / segment / outline) in the pan tool; version label
  (`VERSION`) in both title bars; crosshair-vs-pointer offset investigated — measured aligned in Tk,
  Chromium and Firefox; system pointer hidden while crosshair on.

## 2026-09-27 — drag to move (both versions)
- Pan tool drag priority: handle (reshape) → segment/edge → area/circle interior → pan view.
- Segment drag moves that segment's two points: whole line/axis; one edge of a path/area
  (neighbours stretch). Protractor arm drag moves the whole protractor (my choice; not requested).
- Interior drag (area polygon, or inside/edge of circle) moves the whole shape.
- Pressing a handle or body selects the shape. Tests: 7 new drag checks in each suite.

## 2026-09-27 — feedback round 3 (both versions)
- Keys: `a` = area, `p` = protractor (was angle).
- Colours swapped: selected = blue, unselected = yellow (calibration box/ring follow selected colour).
- Each calibrated shape reports its own measurements in its own units (a line calibrated 0→10 m
  shows "10 m", Δx/Δy too); single value only, no "(… px)" alongside. Uncalibrated shapes use the
  global scale (`s`) if set, else px.
- Hover readouts include units; calibrated path hover shows just the value (no separate s=).
- Calibration box: removed "blank → pixels" hint and "was …" placeholder (value/unit steps are blank).
- Protractor arc radius 24 → 48, label moved out to 84 px.
- Crosshair vs pointer: measured on the real display, drawn crosshair matches the pointer hotspot
  exactly in Tk, Chromium and Firefox; the apparent ~20 px offset is likely the cursor theme's icon vs
  hotspot. The system pointer is now hidden while the crosshair is on (`x` toggles both).
- Smoke test no longer hangs when a step throws.

## 2026-09-27 — step-by-step calibration (both versions)
- Replaced the one-line "v0 v1 [log] [cw] [unit]" prompt with a floating box just above the point being
  calibrated (yellow ring marks it; box follows pan/zoom; flips below the point near the top edge).
  Steps: line/path: point 1, point 2, units · circle: centre, edge, units, clockwise? ·
  digitizer axis: + log scale? · area: known area, units.
- Greyed placeholder shows the previous answer for reference. Blank Enter on a value step clears the
  calibration (back to pixels); blank units = none; blank yes/no keeps previous (default no).
  Esc cancels with no change; Backspace on an empty field goes back a step; clicking the canvas cancels.
- Decisions (user): log only on digitizer axes; cw only on circles (angles stay uncalibrated for now).
- Pure step logic: `cal_steps` / `cal_previous` / `cal_answer` / `build_cal` (JS: camelCase twins).
- Tests: py smoke 20 checks, web harness 17 checks, all pass; screenshots checked for both dialogs.

## 2026-09-27 — web version
- `pickleruler.html`: full port to a single-file browser app (canvas + vanilla JS, no deps).
  Sources: `w` window capture (getDisplayMedia, `displaySurface: 'window'`, CaptureController
  `no-focus-change` where supported), `f` live capture (redraws every frame; freezes when stopped or when
  sharing ends), Ctrl+V paste, drag-and-drop, `i` open file. Outputs: HUD, `y`/`Y` clipboard,
  `E` copy full report, `P` save annotated PNG at source resolution.
- Double-click detection uses `mousedown.detail >= 2`, mirroring Tk's Double-Button semantics.
- Initial centring rounds to whole pixels (half-pixel offsets made 1:1 rendering soft and clicks land .5 off).
- `web_test.sh` + `web_harness.html`: 10 numeric checks pass in headless Chromium and Firefox.
  Actual screen capture untested (needs a human at the picker).

## 2026-09-27 — feedback round 2
- Wording: `c` is described as "calibrate" everywhere (hints, help, prompt).
- Area calibration: `c` on an area polygon takes a known area "value [unit]" (e.g. `25 cm`).
  Stored as a factor k = units²/px², so it holds when the polygon is resized; perimeter uses √k.
  A calibrated area can also be the global length scale (`s`).
- `shape_scale(s)` centralizes "units per px implied by a shape"; `fmt_len`/`fmt_area` accept an explicit scale.
- Smoke test covers area calibration + resize; prints tracebacks for Tk callback errors.
  One run failed with no code at fault: a stray keypress probably reached the test window (it takes focus).

## 2026-09-27 — feedback round 1
- HUD restyle: tool buttons are key badges (bold yellow key + name) with hover/active colours;
  info and help panels are rich text (dim row labels, bold keys, green status line, pixel colour swatch),
  separated by rules.
- Endpoint values (`c` / right-click / double-click) now apply to path (start, end) and circle (centre, edge),
  not just line/axis. Value labels drawn beside both ends of every calibrated shape.
- Hover readouts:
  - line: interpolated value (or distance from start if uncalibrated)
  - path: distance along the path from the start, plus the interpolated value if calibrated
  - circle: angle θ from the centre→edge line (CCW; `cw` flag flips it), radius, and radial value if calibrated.
    Works like a polar plot digitizer.
- Length scale (`s`) can come from any linear-calibrated line, path or circle.
- `y` copies the hover readout (`value, θ` for circles).
- Added `smoke_test.py` and `AGENTS.md`.
- Fixed: HUD rows built as `[row] * bool(x)` evaluated `None[0]` and crashed; now plain conditionals.

## 2026-09-27 — initial build
- Decisions (with user): frozen screenshot rather than a live SHAPE overlay; HUD inside the overlay; X11 only;
  output goes to the HUD, clipboard and stdout on quit.
- Tools: pan/select, line, angle, area polygon, path, circle, 2D digitizer (lin/log axes, skew-tolerant),
  loupe, crosshair, Shift 45° snap, handle editing, undo/delete, zoom/pan.

## Ideas / not done
- Wayland capture backend (e.g. `grim`) behind the same drawing code.
- Multi-monitor: fullscreen covers only the focused output; could start the view on the monitor under the pointer.
- Persist shapes/calibration between launches; export an annotated PNG (done in web as `P`).
- Web welcome screen: 3 example thumbnails (distance on a plot, area on a map, angle on architecture);
  plan: user captures with `maim -s`, `embed_examples.py` inlines them as WebP data URIs. Not started.
- Perspective reference for photos: 4-corner known rectangle → homography, measure anywhere on that plane.
- Web: popup window that can live on another i3 workspace to capture windows there.
