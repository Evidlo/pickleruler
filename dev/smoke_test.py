#!/usr/bin/env python3
"""Drive pickleruler on a synthetic plot and check the numbers.

Needs a live X display (a fullscreen window flashes for ~1 s; don't type while it runs,
it takes keyboard focus).
  python3 dev/smoke_test.py [screenshot.png]
"""

import math
import pathlib
import sys
import traceback
import types

from PIL import Image, ImageDraw, ImageGrab

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pickleruler as pr

im = Image.new('RGB', (800, 600), 'white')
draw = ImageDraw.Draw(im)
draw.line([(100, 500), (700, 500)], fill='black', width=2)
draw.line([(100, 500), (100, 100)], fill='black', width=2)
draw.line([(100, 500), (700, 100)], fill='red', width=2)

r = pr.Ruler(im, 'digitize', screen_mode=False)
failures = []


def on_tk_error(*exc):
    traceback.print_exception(*exc)
    failures.append(f'Tk callback: {exc[1]!r}')


r.root.report_callback_exception = on_tk_error


def E(p, state=0):
    x, y = r.c(p)
    return types.SimpleNamespace(x=x, y=y, state=state, keysym='')


def clicks(*pts, state=0):
    for p in pts:
        r.on_press(E(p, state))
        r.on_release(E(p, state))


def values(*answers):
    """Answer successive calibration steps; '' presses Enter on the greyed placeholder."""
    for text in answers:
        if text:
            r.ph = None
            r.entry.delete(0, 'end')
            r.entry.insert(0, text)
        r.cal_enter()


def hover(p):
    r.on_motion(E(p))
    r.root.update()
    return r.hover


def check(name, got, want, tol=1e-6):
    ok = math.isclose(got, want, rel_tol=tol, abs_tol=tol)
    failures.extend([] if ok else [f'{name}: got {got}, want {want}'])
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {got:.6g}")


def same(name, got, want):
    ok = got == want
    failures.extend([] if ok else [f'{name}: got {got!r}, want {want!r}'])
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {got!r}")


def step():
    try:
        steps()
    except Exception:
        traceback.print_exc()
        failures.append('exception in steps()')
    r.root.after(300, finish)


def steps():
    r.root.update()
    r.reset_view()

    clicks((100, 500), (700, 500))
    values('0', '10', '', '')
    clicks((100, 500), (100, 100))
    values('1', '1000', '', 'yes')
    clicks((400, 300), (700, 100))
    d = r.to_data((400, 300))
    check('digitize x', d[0], 5)
    check('digitize log y', d[1], math.sqrt(1000))
    same('axes do not set the image scale', r.scale(), None)

    r.set_tool('line')
    clicks((100, 550), (700, 550))
    line = r.shapes[-1]
    same('uncalibrated image reports px', r.short(line), '600.0 px')
    r.start_cal(line)
    values('0', '60', 'mm')
    check('line calibration sets image scale', r.scale()[0], 0.1)
    same('reference label', r.short(line), '60 mm (ref)')
    r.start_cal(line)
    values('5', '5')
    check('equal endpoint values rejected, still on step 2', r.calflow['i'], 1)
    r.end_cal()
    check('cancel keeps scale', r.scale()[0], 0.1)
    check('line hover value', float(hover((250, 552))['copy']), 15)
    same('hover shows units', r.hover['text'], '15 mm')

    clicks((100, 580), (400, 580))
    line2 = r.shapes[-1]
    same('new shape gets units automatically', r.short(line2), '30 mm')
    r.start_cal(line2)
    values('100', '')
    same('blank point 2 skips units and finishes', r.calflow, None)
    check('blank point 2 keeps scale', r.scale()[0], 0.1)
    same('reference unchanged', r.scale_src is line, True)
    check('offset line: start value + scaled distance', float(hover((250, 582))['copy']), 115)

    r.set_tool('poly')
    clicks((200, 200), (300, 200), (300, 300))
    r.on_right(E((0, 0)))
    poly = r.shapes[-1]
    check('poly area px²', pr.shoelace(poly['pts']), 5000)
    same('area in image units', r.short(poly), '50 mm²')
    r.start_cal(poly)
    values('50', 'cm²')
    check('area calibration sets scale', r.scale()[0], 0.1)
    same('other shapes follow the new scale', r.short(line), '60 cm')
    r.set_tool('pan')
    r.on_press(E((300, 300)))
    r.on_motion(E((300, 400)))
    r.on_release(E((300, 400)))
    check('scale holds after resizing the reference', r.scale()[0], 0.1)
    same('resized reference area', r.short(poly), '100 cm² (ref)')
    r.sel = poly
    r.start_cal(poly)
    check('value step placeholder is blank', r.ph is None, True)
    r.end_cal()

    r.set_tool('angle')
    clicks((500, 200), (400, 300), (500, 300))
    check('angle', abs(pr.angle_extent(r.shapes[-1]['pts'])[1]), 45)

    r.set_tool('path')
    clicks((150, 150), (250, 150), (250, 250))
    r.on_right(E((0, 0)))
    r.start_cal(r.shapes[-1])
    values('0', '1', '')
    h = hover((251, 200))
    check('path value along', float(h['copy']), 0.75)

    r.start_cal(r.shapes[-1])
    values('')
    check('blank point 1 clears calibration', r.shapes[-1]['cal'] is None, True)
    same('clearing the reference returns image to px', r.scale(), None)
    check('uncalibrated path distance px', float(hover((251, 200))['copy']), 150)
    r.start_cal(r.shapes[-1])
    values('0', '1', '')

    r.set_tool('circle')
    clicks((600, 300), (650, 300))
    r.start_cal(r.shapes[-1])
    values('0', '1', '', '')
    h = hover((600, 280))
    check('circle radial value', float(h['copy'].split(',')[0]), 0.4)
    check('circle angle ccw', float(h['copy'].split(',')[1]), 90)
    r.start_cal(r.shapes[-1])
    values('0')
    r.entry_key(types.SimpleNamespace(keysym='BackSpace', char='\x08'))
    check('backspace on empty field steps back', r.calflow['i'], 0)
    values('0', '1', '', 'maybe')
    check('bad yes/no stays on clockwise step', r.calflow['i'], 3)
    values('yes')
    check('circle angle cw', float(hover((600, 280))['copy'].split(',')[1]), 270)

    r.set_tool('pan')
    kinds = {}
    for s in r.shapes:
        kinds.setdefault(s['kind'], s)
    line, poly, path, circle = kinds['line'], kinds['poly'], kinds['path'], kinds['circle']

    def drag(a, b):
        r.on_press(E(a))
        r.on_motion(E(b))
        r.on_release(E(b))

    r.on_motion(E((400, 550)))
    hot = r.hot_part()
    check('hover line segment highlights it', hot[0] is line and hot[1] == [0, 1] and not hot[2], True)
    r.on_motion(E((700, 550)))
    check('hover endpoint highlights handle', r.hot_part()[2] and r.hot_part()[1] == [1], True)
    r.on_motion(E((600, 320)))
    check('hover inside circle highlights whole', r.hot_part()[0] is circle, True)
    drag((400, 550), (400, 560))
    check('drag line segment moves both ends', line['pts'][0][1] + line['pts'][1][1], 1120)
    area0 = pr.shoelace(poly['pts'])
    drag((280, 250), (290, 270))
    check('drag inside area moves all: vertex', poly['pts'][0][0] + poly['pts'][0][1], 430)
    check('drag inside area keeps area', pr.shoelace(poly['pts']), area0)
    drag((200, 150), (200, 140))
    check('drag path segment moves its two points', path['pts'][0][1] + path['pts'][1][1], 280)
    check('drag path segment leaves others', path['pts'][2][1], 250)
    drag((600, 320), (620, 320))
    check('drag inside circle moves centre', circle['pts'][0][0], 620)
    check('drag inside circle keeps radius', pr.dist(*circle['pts']), 50)

    r.on_key(types.SimpleNamespace(keysym='question', state=0))
    r.zoom_at(*r.c((600, 280)), 1.25)
    r.root.update()


def finish():
    if len(sys.argv) > 1:
        ImageGrab.grab().save(sys.argv[1])
    r.quit()


r.root.after(500, step)
r.run()
print('FAILED:\n  ' + '\n  '.join(failures) if failures else 'all ok')
sys.exit(bool(failures))
