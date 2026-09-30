#!/usr/bin/env -S uv run --script
# SPDX-License-Identifier: GPL-3.0-or-later
# /// script
# requires-python = ">3.9"
# dependencies = ["pillow"]
# ///

"""pickleruler: screen ruler, protractor, area meter and plot digitizer.

Takes a screenshot (X11) or opens an image, shows it fullscreen and lets you
measure on top of it.  Press ? inside for keys.
"""

import argparse
import math
import re
import shutil
import subprocess
import sys
import time
import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageGrab, ImageTk

VERSION = '0.0.8'
NEED = {'line': 2, 'axis': 2, 'angle': 3, 'circle': 2, 'pt': 1, 'poly': 0, 'path': 0}
TOOLS = [
    ('pan', 'v', 'Pan'),
    ('line', 'l', 'Line'),
    ('angle', 'p', 'Protractor'),
    ('poly', 'a', 'Area'),
    ('path', 't', 'Path'),
    ('circle', 'o', 'Circle'),
    ('digitize', 'd', 'Digitize'),
]
HINTS = {
    'pan': 'drag handle: reshape · drag edge: move it · drag inside area/circle: move all · {c} calibrates',
    'line': 'click-click or drag · {Shift} snaps 45° · {c} calibrates start/end values',
    'angle': 'click arm end, vertex, other arm end',
    'poly': 'click vertices · {right-click}/{Enter}/{double-click} closes · {c} calibrates known area',
    'path': 'click vertices · {right-click}/{Enter}/{double-click} ends · {c} calibrates start/end values',
    'circle': 'click centre, then a point on the edge · {c} calibrates centre/edge values',
}
HELP = [
    ('tools', '{v} pan/select  {l} line  {p} protractor  {a} area  {t} path  {o} circle  {d} digitize'),
    ('mouse', 'scroll zoom · left-drag pans (pan tool) · middle-drag pans (any tool)'),
    ('', '{Shift} snaps 45° · {right-click}/{Enter}/{double-click} finishes area/path'),
    ('calib', '{c}/{right-click} calibrate step by step at the point · {Enter} next · {Esc} cancel'),
    ('', 'blank value → back to pixels · {Backspace} on empty field → previous step'),
    ('', 'line/path: start, end, units · circle: + clockwise? · axis: + log scale?'),
    ('', 'area: known area, units (holds when the area is resized)'),
    ('hover', 'line: value · path: distance along · circle: angle from centre→edge, radius'),
    ('edit', 'pan tool: drag handle reshapes · drag edge moves it · drag inside area/circle moves all'),
    ('', '{Del} delete · {u} undo'),
    ('view', '{m} loupe · {x} crosshair · {r} reset view · {h} hide panel · {?} help'),
    ('output', '{y} copy readout · {Y} copy points CSV · {q} quit + print · {Esc} back'),
]
CAL_KINDS = ('line', 'axis', 'path', 'circle')
HUD = dict(bg='#111111', fg='#e8e8e8', head='#6f8599', key='#ffd866', dim='#a8b4c0', msg='#8fd18f',
           btn='#262626', btn_hover='#333333', btn_on='#4a4a1a', sep='#333333', title='#2b2b2b')
COL = dict(shape='#ffd400', sel='#00e5ff', preview='#ff4fd8', axis='#7cfc00',
           pt='#ff5c5c', cross='#b0b0b0', value='#ffffff', hot='#ffffff')
FONT = 'TkFixedFont'
HIT = 8
LOUPE_N, LOUPE_MAG = 15, 10


def dist(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def seg_param(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    return ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / max(dx * dx + dy * dy, 1e-12)


def lerp(a, b, t):
    return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))


def seg_dist(p, a, b):
    return dist(p, lerp(a, b, min(1.0, max(0.0, seg_param(p, a, b)))))


def snap45(anchor, p):
    dx, dy = p[0] - anchor[0], p[1] - anchor[1]
    ang = math.atan2(dy, dx)
    q = round(ang / (math.pi / 4)) * (math.pi / 4)
    L = math.hypot(dx, dy) * math.cos(ang - q)
    return (anchor[0] + L * math.cos(q), anchor[1] + L * math.sin(q))


def heading(a, b):
    """Direction a->b in degrees, counter-clockwise with y up (screen y is flipped)."""
    return math.degrees(math.atan2(a[1] - b[1], b[0] - a[0]))


def polyline_len(pts):
    return sum(dist(a, b) for a, b in zip(pts, pts[1:]))


def polyline_foot(pts, p):
    """Nearest point on a polyline: (distance, foot, arc length from start)."""
    best, s0 = None, 0.0
    for a, b in zip(pts, pts[1:]):
        t = min(1.0, max(0.0, seg_param(p, a, b)))
        f = lerp(a, b, t)
        cand = (dist(p, f), f, s0 + t * dist(a, b))
        best = cand if best is None or cand[0] < best[0] else best
        s0 += dist(a, b)
    return best


def inside_polygon(p, pts):
    x, y = p
    inside = False
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def shoelace(pts):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2


def fmt(v):
    return f'{v:.6g}'


def cal_steps(kind):
    """(key, prompt) for each step of the calibration dialogue."""
    if kind == 'poly':
        return [('area', 'known area'), ('unit', 'units')]
    a, b = ('centre', 'edge') if kind == 'circle' else ('point 1', 'point 2')
    extra = {'axis': [('log', 'log scale?')], 'circle': [('cw', 'clockwise?')]}.get(kind, [])
    return [('v0', f'calibrate {a}'), ('v1', f'calibrate {b}'), ('unit', 'units')] + extra


KEEP = 'keep'


def cal_previous(s):
    """Previous yes/no answers, shown greyed in the dialogue."""
    cal = s.get('cal') or {}
    return {k: 'yes' if cal.get(k) else 'no' for k in ('log', 'cw')}


def cal_answer(key, text, answers, prev, kind, scaled):
    """Parse one step's answer. None: clear the calibration. KEEP: blank point 2, keep the image scale."""
    if key == 'v1' and not text and kind != 'axis' and scaled:
        return KEEP
    if key == 'v1' and not text:
        raise ValueError('needs a value (no scale set yet)')
    if key in ('v0', 'v1', 'area'):
        if not text:
            return None
        try:
            v = float(text)
        except ValueError:
            raise ValueError('not a number') from None
        if key == 'v1' and v == answers['v0']:
            raise ValueError('must differ from the first value')
        if key == 'area' and v <= 0:
            raise ValueError('area must be positive')
        return v
    if key == 'unit':
        return re.sub(r'(\^2|²)$', '', text)
    t = (text or prev.get(key, 'no')).lower()
    if t not in ('y', 'yes', 'n', 'no'):
        raise ValueError('answer yes or no')
    yes = t in ('y', 'yes')
    if key == 'log' and yes and min(answers['v0'], answers['v1']) <= 0:
        raise ValueError('log scale needs positive values')
    return yes


def span_px(s):
    """Length that a shape's end value sits at: radius for circles, path length otherwise."""
    return dist(*s['pts']) if s['kind'] == 'circle' else polyline_len(s['pts'])


def cal_str(cal):
    flags = ' log' * cal['log'] + ' cw' * cal['cw']
    return f"{fmt(cal['v0'])} → {fmt(cal['v1'])}{flags} {cal['unit']}".rstrip()


def cal_value(cal, t):
    if cal['log']:
        l0, l1 = math.log10(cal['v0']), math.log10(cal['v1'])
        return 10 ** (l0 + t * (l1 - l0))
    return cal['v0'] + t * (cal['v1'] - cal['v0'])


def angle_extent(pts):
    a, v, b = pts
    start = heading(v, a)
    return start, (heading(v, b) - start + 180) % 360 - 180


def copy_to_clipboard(root, text):
    tool = shutil.which('xclip')
    if tool:
        subprocess.run([tool, '-selection', 'clipboard'], input=text.encode(),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    root.clipboard_clear()
    root.clipboard_append(text)


class Ruler:
    def __init__(self, img, tool, screen_mode):
        self.img = img.convert('RGB')
        self.screen_mode = screen_mode
        self.z, self.t = 1.0, [0.0, 0.0]
        self.view_touched = False
        self.shapes, self.cur, self.sel = [], None, None
        self.scale_k, self.scale_src = None, None
        self.mouse, self.shift = (0, 0), False
        self.drag, self.press = None, None
        self.hover = None
        self.show_loupe, self.show_cross = True, True
        self.calflow = None
        self.ph = None
        self.msg = ''
        self._queued, self._full = False, True

        self.root = tk.Tk(className='pickleruler')
        self.root.title('pickleruler')
        self.root.attributes('-fullscreen', True)
        self.root.protocol('WM_DELETE_WINDOW', self.quit)
        self.cv = tk.Canvas(self.root, bg='#1a1a1a', highlightthickness=0, cursor='tcross')
        self.cv.pack(fill='both', expand=True)
        self.img_item = self.cv.create_image(0, 0, anchor='nw')
        self.build_hud()
        self.bind()
        self.set_tool(tool)
        self.sync_cursor()
        self.root.after(200, self.grab_focus)

    # ---------------------------------------------------------------- setup
    def build_hud(self):
        bg = HUD['bg']
        self.bold = tkfont.nametofont(FONT).copy()
        self.bold.configure(weight='bold')
        self.hud = tk.Frame(self.root, bg=bg, highlightthickness=1, highlightbackground='#555')
        title = tk.Label(self.hud, text=f' pickleruler {VERSION}   ·  ? help  ·  h hide  ·  drag to move', bg=HUD['title'], fg='#dddddd', font=self.bold,
                         anchor='w', cursor='fleur')
        title.pack(fill='x')
        title.bind('<ButtonPress-1>', self.hud_press)
        title.bind('<B1-Motion>', self.hud_drag)
        bar = tk.Frame(self.hud, bg=bg)
        bar.pack(fill='x', padx=3, pady=(3, 0))
        bar2 = tk.Frame(self.hud, bg=bg)
        bar2.pack(fill='x', padx=3, pady=3)
        self.buttons = {}
        for name, key, text in TOOLS + [('calibrate', 'c', 'Calibrate')]:
            f = tk.Frame(bar2 if name == 'calibrate' else bar, bg=HUD['btn'], cursor='hand2')
            f.pack(side='left', padx=1)
            kl = tk.Label(f, text=key, font=self.bold, bg=HUD['btn'], fg=HUD['key'], padx=3)
            nl = tk.Label(f, text=text, font=FONT, bg=HUD['btn'], fg=HUD['fg'], padx=0)
            kl.pack(side='left')
            nl.pack(side='left', padx=(0, 5))
            act = (lambda e: self.calibrate_selected()) if name == 'calibrate' else (lambda e, n=name: self.set_tool(n))
            for w in (f, kl, nl):
                w.bind('<Button-1>', act)
                w.bind('<Enter>', lambda e, n=name: self.paint_button(n, hover=True))
                w.bind('<Leave>', lambda e, n=name: self.paint_button(n))
            self.buttons[name] = (f, kl, nl)
        tk.Frame(self.hud, height=1, bg=HUD['sep']).pack(fill='x')
        self.info = self.rich_widget()
        self.info.pack(fill='x')
        self.calbox = tk.Frame(self.root, bg=bg, highlightthickness=1, highlightbackground=COL['sel'])
        self.clabel = tk.Label(self.calbox, anchor='w', font=self.bold, bg=bg, fg=COL['sel'])
        self.clabel.pack(fill='x', padx=5, pady=(3, 0))
        self.entry = tk.Entry(self.calbox, font=FONT, width=26, bg='#000', fg='#fff', insertbackground='#fff',
                              highlightthickness=0, relief='flat')
        self.entry.pack(fill='x', padx=5, pady=2)
        self.chint = tk.Label(self.calbox, anchor='w', font=FONT, bg=bg, fg=HUD['head'])
        self.chint.pack(fill='x', padx=5, pady=(0, 3))
        self.entry.bind('<Return>', self.cal_enter)
        self.entry.bind('<KP_Enter>', self.cal_enter)
        self.entry.bind('<Escape>', lambda e: self.end_cal())
        self.entry.bind('<Key>', self.entry_key)
        self.entry.bind('<KeyRelease>', self.entry_keyup)
        self.hframe = tk.Frame(self.hud, bg=bg)
        tk.Frame(self.hframe, height=1, bg=HUD['sep']).pack(fill='x')
        help_text = self.rich_widget(self.hframe)
        help_text.pack(fill='x')
        self.rich(help_text, [(h, b, 'dim') for h, b in HELP])
        self.hud_pos = [16, 16]
        self.hud.place(x=16, y=16)

    def rich_widget(self, parent=None):
        t = tk.Text(parent or self.hud, font=FONT, bg=HUD['bg'], fg=HUD['fg'], bd=0, highlightthickness=0,
                    wrap='none', takefocus=0, cursor='xterm', padx=5, pady=3, height=1, width=1)
        t.tag_configure('head', foreground=HUD['head'])
        t.tag_configure('key', foreground=HUD['key'], font=self.bold)
        t.tag_configure('dim', foreground=HUD['dim'])
        t.tag_configure('msg', foreground=HUD['msg'])
        t.tag_configure('val', foreground=HUD['fg'])
        return t

    def rich(self, widget, rows):
        """rows of (head, body, tag); {x} in body is rendered as a bold key, § as the pixel swatch.
        Unchanged rows are not re-rendered, so a text selection in the panel survives redraws."""
        if getattr(widget, 'rows', None) == rows:
            return
        widget.rows = rows
        widget.config(state='normal')
        widget.delete('1.0', 'end')
        plain = []
        for n, (head, body, tag) in enumerate(rows):
            widget.insert('end', '\n' * (n > 0) + f'{head:<7}', 'head')
            for part in re.split(r'(\{[^}]*\}|§)', body):
                style = 'key' if part.startswith('{') else 'swatch' if part == '§' else tag
                widget.insert('end', part.strip('{}') if style == 'key' else '██' if style == 'swatch' else part, style)
            plain.append(7 + len(re.sub(r'\{([^}]*)\}', r'\1', body)) + body.count('§'))
        widget.config(state='disabled', height=len(rows), width=max(plain + [78]))

    def paint_button(self, name, hover=False):
        f, kl, nl = self.buttons[name]
        bg = HUD['btn_on'] if name == self.tool else HUD['btn_hover'] if hover else HUD['btn']
        for w in (f, kl, nl):
            w.config(bg=bg)

    def bind(self):
        cv = self.cv
        cv.bind('<Configure>', self.on_configure)
        for ev in ('<Motion>', '<B1-Motion>', '<B2-Motion>', '<B3-Motion>'):
            cv.bind(ev, self.on_motion)
        cv.bind('<ButtonPress-1>', self.on_press)
        cv.bind('<ButtonRelease-1>', self.on_release)
        cv.bind('<Double-Button-1>', self.on_double)
        cv.bind('<ButtonPress-2>', self.on_middle)
        cv.bind('<ButtonRelease-2>', self.on_release)
        cv.bind('<ButtonPress-3>', self.on_right)
        cv.bind('<Button-4>', lambda e: self.zoom_at(e.x, e.y, 1.25))
        cv.bind('<Button-5>', lambda e: self.zoom_at(e.x, e.y, 0.8))
        cv.bind('<MouseWheel>', lambda e: self.zoom_at(e.x, e.y, 1.25 if e.delta > 0 else 0.8))
        cv.bind('<Key>', self.on_key)
        cv.bind('<Enter>', lambda e: self.calflow or cv.focus_set())

    def grab_focus(self):
        self.root.focus_force()
        self.cv.focus_set()

    def on_configure(self, e):
        if not self.view_touched:
            self.reset_view()
        self.redraw()

    def reset_view(self):
        W, H = self.cv.winfo_width(), self.cv.winfo_height()
        iw, ih = self.img.size
        if self.screen_mode:
            self.z = 1.0
            self.t = [-self.cv.winfo_rootx(), -self.cv.winfo_rooty()]
        else:
            self.z = min(W / iw, H / ih, 1.0)
            self.t = [(W - iw * self.z) / 2, (H - ih * self.z) / 2]
        self.redraw()

    # ---------------------------------------------------------- coordinates
    def c(self, p):
        return (p[0] * self.z + self.t[0], p[1] * self.z + self.t[1])

    def i(self, x, y):
        return ((x - self.t[0]) / self.z, (y - self.t[1]) / self.z)

    def snapped(self, p, anchor):
        return snap45(anchor, p) if (self.shift and anchor is not None) else p

    def cursor_point(self, x, y):
        h = self.find_hover(x, y)
        return h['foot'] if h else self.snapped(self.i(x, y), self.cur['pts'][-1] if self.cur else None)

    def event_point(self, e):
        return self.cursor_point(e.x, e.y)

    # ------------------------------------------------------------- measures
    def scale(self):
        """(units per px, unit) for the whole image, or None."""
        return self.scale_k

    def set_scale(self, s, value, unit):
        """Fix the image scale from shape s having known length (or area, for polygons) `value`."""
        pts = s['pts']
        k = math.sqrt(value / max(shoelace(pts), 1e-12)) if s['kind'] == 'poly' else value / max(span_px(s), 1e-12)
        self.scale_k, self.scale_src = (k, unit), s

    def unit(self):
        sc = self.scale()
        return sc[1] if sc else 'px'

    def along_value(self, s, px):
        """Value at px along a line/path (or radius of a circle): its start offset plus scaled distance."""
        cal = s.get('cal') or dict(v0=0.0, dir=1)
        return cal['v0'] + cal['dir'] * px * (self.scale() or (1.0,))[0]

    def fmt_len(self, px):
        sc = self.scale()
        return f'{fmt(px * sc[0])} {sc[1]}'.rstrip() if sc else f'{px:.1f} px'

    def fmt_area(self, px2):
        sc = self.scale()
        if sc is None:
            return f'{px2:.1f} px²'
        return f'{fmt(px2 * sc[0] ** 2)} {sc[1]}²' if sc[1] else fmt(px2 * sc[0] ** 2)

    def axes(self):
        ax = {s['axis']: s for s in self.shapes if s['kind'] == 'axis' and s['cal']}
        return ax.get('x'), ax.get('y')

    def to_data(self, p):
        X, Y = self.axes()
        if X is None or Y is None:
            return None
        dX = (X['pts'][1][0] - X['pts'][0][0], X['pts'][1][1] - X['pts'][0][1])
        dY = (Y['pts'][1][0] - Y['pts'][0][0], Y['pts'][1][1] - Y['pts'][0][1])
        det = dX[0] * dY[1] - dX[1] * dY[0]
        if abs(det) < 1e-9:
            return None

        def solve(o):
            rx, ry = p[0] - o[0], p[1] - o[1]
            return (rx * dY[1] - ry * dY[0]) / det, (dX[0] * ry - dX[1] * rx) / det

        a = solve(X['pts'][0])[0]
        b = solve(Y['pts'][0])[1]
        return cal_value(X['cal'], a), cal_value(Y['cal'], b)

    def index_of(self, s):
        same = [x for x in self.shapes if x['kind'] == s['kind']]
        return same.index(s) + 1 if s in same else len(same) + 1

    def name(self, s):
        if s['kind'] == 'axis':
            return f"{s['axis'].upper()}-axis"
        return f"{s['kind']} {self.index_of(s)}"

    def cal_tag(self, s):
        k, cal = s['kind'], s.get('cal')
        if k == 'axis':
            return f'  [{cal_str(cal)}]' if cal else ''
        if not cal or k not in CAL_KINDS:
            return ''
        end = self.along_value(s, span_px(s))
        return f"  [{fmt(cal['v0'])} → {fmt(end)}{' cw' * cal['cw']} {self.unit()}".rstrip() + ']'

    def summary(self, s):
        k, pts = s['kind'], s['pts']
        L, tag = self.fmt_len, self.cal_tag(s)
        if k in ('line', 'axis') or (k == 'angle' and len(pts) < 3):
            a, b = pts[0], pts[1]
            return f'L={L(dist(a, b))}  Δx={L(b[0] - a[0])}  Δy={L(a[1] - b[1])}  θ={heading(a, b):.2f}°' + tag
        if k == 'angle':
            ang = abs(angle_extent(pts)[1])
            return f'{ang:.3f}°  (reflex {360 - ang:.3f}°)'
        if k == 'poly' and len(pts) >= 3:
            return f'A={self.fmt_area(shoelace(pts))}  P={L(polyline_len(pts + pts[:1]))}  n={len(pts)}' + tag
        if k in ('path', 'poly'):
            return f'L={L(polyline_len(pts))}  segments={len(pts) - 1}' + tag
        if k == 'circle':
            r = dist(*pts)
            return (f'r={L(r)}  d={L(2 * r)}  A={self.fmt_area(math.pi * r * r)}  C={L(2 * math.pi * r)}'
                    f'  θ₀={heading(*pts):.2f}°' + tag)
        d = self.to_data(pts[0])
        px = f'px {pts[0][0]:.1f}, {pts[0][1]:.1f}'
        return f'x={fmt(d[0])}  y={fmt(d[1])}  ({px})' if d else px

    def short(self, s):
        k, pts = s['kind'], s['pts']
        ref = ' (ref)' if s is self.scale_src else ''
        if k == 'line':
            return self.fmt_len(dist(*pts)) + ref
        if k == 'axis':
            return s['axis'].upper() + ('' if s['cal'] else ' (not calibrated: c)')
        if k == 'angle':
            return f'{abs(angle_extent(pts)[1]):.2f}°' if len(pts) == 3 else self.fmt_len(dist(*pts[:2]))
        if k == 'poly' and len(pts) >= 3:
            return self.fmt_area(shoelace(pts)) + ref
        if k in ('path', 'poly'):
            return self.fmt_len(polyline_len(pts)) + ref
        if k == 'circle':
            return 'r=' + self.fmt_len(dist(*pts)) + ref
        return f'#{self.index_of(s)}'

    def shape_dist(self, s, p):
        pts = s['pts']
        if s['kind'] == 'circle':
            return abs(dist(pts[0], p) - dist(*pts))
        if s['kind'] == 'pt':
            return dist(pts[0], p)
        segs = list(zip(pts, pts[1:])) + ([(pts[-1], pts[0])] if s['kind'] == 'poly' else [])
        return min(seg_dist(p, a, b) for a, b in segs)

    def nearest(self, x, y):
        p = self.i(x, y)
        cands = [(self.shape_dist(s, p) * self.z, s) for s in self.shapes]
        cands = [c for c in cands if c[0] <= HIT]
        return min(cands, key=lambda c: c[0])[1] if cands else None

    def hit_handle(self, x, y):
        order = ([self.sel] if self.sel in self.shapes else []) + self.shapes[::-1]
        for s in order:
            for k, p in enumerate(s['pts']):
                cx, cy = self.c(p)
                if math.hypot(cx - x, cy - y) <= HIT:
                    return s, k
        return None

    def hit_body(self, x, y):
        """Part of a shape to move from canvas (x, y): (shape, point indices), or None.
        Segments move their own two points (a protractor moves whole); area/circle interiors move whole."""
        p, tol = self.i(x, y), HIT / self.z
        order = ([self.sel] if self.sel in self.shapes else []) + self.shapes[::-1]
        for s in order:
            k, pts, n = s['kind'], s['pts'], len(s['pts'])
            if k not in ('line', 'axis', 'path', 'poly', 'angle'):
                continue
            segs = [(i, (i + 1) % n) for i in range(n if k == 'poly' else n - 1)]
            d, ij = min((seg_dist(p, pts[i], pts[j]), (i, j)) for i, j in segs)
            if d <= tol:
                return s, list(range(n)) if k == 'angle' else list(ij)
        for s in order:
            pts = s['pts']
            if (s['kind'] == 'poly' and inside_polygon(p, pts)
                    or s['kind'] == 'circle' and dist(pts[0], p) <= dist(*pts) + tol):
                return s, list(range(len(pts)))
        return None

    def hover_info(self, s, p):
        """Readout for cursor p near shape s, or None: dict(d, shape, foot, text, copy)."""
        pts, cal = s['pts'], s.get('cal')
        if s['kind'] == 'circle':
            c, R = pts[0], max(dist(*pts), 1e-12)
            r = dist(c, p)
            edge = abs(r - R) * self.z
            if r > R and edge > HIT:
                return None
            theta = (heading(c, p) - heading(*pts)) * (-1 if cal and cal['cw'] else 1) % 360
            val = self.along_value(s, r)
            radial = f'{fmt(val)} {self.unit()}' if cal else f'r={self.fmt_len(r)}'
            return dict(d=min(edge, HIT), shape=s, foot=p, text=f'θ={theta:.2f}°  {radial}',
                        copy=f'{fmt(val)}, {theta:.3f}')
        d, foot, along = polyline_foot(pts, p)
        if d * self.z > HIT:
            return None
        if s['kind'] == 'axis':
            val = cal and cal_value(cal, along / max(polyline_len(pts), 1e-12))
            text = f"{fmt(val)} {cal['unit']}".rstrip() if cal else self.fmt_len(along)
            return dict(d=d * self.z, shape=s, foot=foot, text=text, copy=fmt(val) if cal else text)
        val = self.along_value(s, along)
        text = f'{fmt(val)} {self.unit()}' if cal else self.fmt_len(along)
        return dict(d=d * self.z, shape=s, foot=foot, text=text, copy=fmt(val))

    def find_hover(self, x, y):
        if self.calflow:
            return None
        p = self.i(x, y)
        cands = [h for s in self.shapes if s['kind'] in CAL_KINDS for h in [self.hover_info(s, p)] if h]
        return min(cands, key=lambda h: h['d']) if cands else None

    # ------------------------------------------------------------- drawing
    def redraw(self, full=True):
        self._full |= full
        if not self._queued:
            self._queued = True
            self.root.after_idle(self.flush)

    def flush(self):
        self._queued = False
        if self._full:
            self._full = False
            self.render_image()
            self.cv.delete('ov')
            for s in self.shapes:
                self.draw_shape(s, 'ov')
        if self.calflow:
            self.place_calbox()
        self.draw_cursor()
        self.update_hud()

    def render_image(self):
        W, H = self.cv.winfo_width(), self.cv.winfo_height()
        iw, ih = self.img.size
        z, (tx, ty) = self.z, self.t
        x0, y0 = max(0, math.floor(-tx / z)), max(0, math.floor(-ty / z))
        x1, y1 = min(iw, math.ceil((W - tx) / z)), min(ih, math.ceil((H - ty) / z))
        if x1 <= x0 or y1 <= y0:
            self.cv.itemconfig(self.img_item, state='hidden')
            return
        size = (max(1, round((x1 - x0) * z)), max(1, round((y1 - y0) * z)))
        resample = Image.NEAREST if z >= 1 else Image.BILINEAR
        self.photo = ImageTk.PhotoImage(self.img.crop((x0, y0, x1, y1)).resize(size, resample))
        self.cv.itemconfig(self.img_item, image=self.photo, state='normal')
        self.cv.coords(self.img_item, x0 * z + tx, y0 * z + ty)

    def polyline(self, pts, color, tag, width=2, closed=False, dash=None):
        flat = [v for p in pts + pts[:1] * closed for v in self.c(p)]
        if len(flat) < 4:
            return
        kw = dict(tags=tag, capstyle='round', joinstyle='round')
        self.cv.create_line(*flat, fill='black', width=width + 2, **kw)
        self.cv.create_line(*flat, fill=color, width=width, dash=dash, **kw)

    def label(self, x, y, text, color, tag, anchor='sw'):
        t = self.cv.create_text(x, y, text=text, fill=color, font=FONT, anchor=anchor, tags=tag)
        x0, y0, x1, y1 = self.cv.bbox(t)
        r = self.cv.create_rectangle(x0 - 2, y0 - 1, x1 + 2, y1 + 1, fill='black', outline='', tags=tag)
        self.cv.tag_lower(r, t)

    def handle(self, p, color, tag):
        x, y = self.c(p)
        self.cv.create_rectangle(x - 3, y - 3, x + 3, y + 3, outline='black', fill=color, tags=tag)

    def draw_shape(self, s, tag, color=None):
        k, pts = s['kind'], s['pts']
        color = color or (COL['sel'] if s is self.sel else
                          COL['axis'] if k == 'axis' else COL['pt'] if k == 'pt' else COL['shape'])
        text = self.short(s)
        if k == 'pt':
            x, y = self.c(pts[0])
            for d in ((-5, -5, 5, 5), (-5, 5, 5, -5)):
                self.cv.create_line(x + d[0], y + d[1], x + d[2], y + d[3], fill='black', width=4, tags=tag)
                self.cv.create_line(x + d[0], y + d[1], x + d[2], y + d[3], fill=color, width=2, tags=tag)
            self.label(x + 6, y - 4, text, color, tag)
        elif k == 'circle':
            (cx, cy), r = self.c(pts[0]), dist(*pts) * self.z
            for w, col in ((4, 'black'), (2, color)):
                self.cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline=col, width=w, tags=tag)
            self.polyline(pts, color, tag, width=1, dash=(4, 3))
            self.label(cx + 4, cy - 4, text, color, tag)
        elif k == 'poly' and len(pts) >= 3:
            flat = [v for p in pts for v in self.c(p)]
            self.cv.create_polygon(*flat, fill=color, stipple='gray25', outline='', tags=tag)
            self.polyline(pts, color, tag, closed=True)
            cx, cy = self.c((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)))
            self.label(cx, cy, text, color, tag, anchor='center')
        elif k == 'angle' and len(pts) == 3:
            self.polyline(pts, color, tag)
            vx, vy = self.c(pts[1])
            start, extent = angle_extent(pts)
            self.cv.create_arc(vx - 48, vy - 48, vx + 48, vy + 48, start=start, extent=extent,
                               style='arc', outline=color, width=2, tags=tag)
            mid = math.radians(start + extent / 2)
            self.label(vx + 84 * math.cos(mid), vy - 84 * math.sin(mid), text, color, tag, anchor='center')
        else:
            self.polyline(pts, color, tag)
            (ax, ay), (bx, by) = self.c(pts[-2]), self.c(pts[-1])
            self.label((ax + bx) / 2 + 6, (ay + by) / 2 - 6, text, color, tag)
        if s.get('cal') and k in CAL_KINDS:
            cal = s['cal']
            v1 = cal['v1'] if k == 'axis' else self.along_value(s, span_px(s))
            self.end_label(pts[0], pts[0], pts[1], fmt(cal['v0']), color, tag)
            self.end_label(pts[-1], pts[-2], pts[-1], fmt(v1), color, tag)
        if s is self.sel:
            for p in pts:
                self.handle(p, color, tag)

    def end_label(self, at, a, b, text, color, tag):
        (x, y), (ax, ay), (bx, by) = self.c(at), self.c(a), self.c(b)
        L = max(math.hypot(bx - ax, by - ay), 1e-9)
        self.label(x + 14 * (ay - by) / L, y + 14 * (bx - ax) / L, text, color, tag, anchor='center')

    def draw_cursor(self):
        cv = self.cv
        cv.delete('cur')
        mx, my = self.mouse
        W, H = cv.winfo_width(), cv.winfo_height()
        if self.show_cross:
            cv.create_line(0, my, W, my, fill=COL['cross'], dash=(3, 5), tags='cur')
            cv.create_line(mx, 0, mx, H, fill=COL['cross'], dash=(3, 5), tags='cur')
        self.preview = None
        if self.cur:
            self.preview = dict(self.cur, pts=self.cur['pts'] + [self.cursor_point(mx, my)])
            self.draw_shape(self.preview, 'cur', COL['preview'])
        if self.calflow:
            x, y = self.c(self.cal_anchor())
            for w, col in ((4, 'black'), (2, COL['sel'])):
                cv.create_oval(x - 9, y - 9, x + 9, y + 9, outline=col, width=w, tags='cur')
        self.hover = self.find_hover(mx, my)
        if self.hover:
            h = self.hover
            fx, fy = self.c(h['foot'])
            if h['shape']['kind'] == 'circle':
                self.polyline([h['shape']['pts'][0], h['foot']], COL['value'], 'cur', width=1, dash=(4, 3))
            cv.create_oval(fx - 4, fy - 4, fx + 4, fy + 4, outline='black', fill=COL['value'], tags='cur')
            self.label(fx + 8, fy - 8, h['text'], COL['value'], 'cur')
        self.draw_hot()
        if self.show_loupe:
            self.draw_loupe(W, H)

    def hot_part(self):
        """What a pan-tool press would grab (or is dragging): (shape, point indices, is_handle) or None."""
        d = self.drag
        if d and d['kind'] in ('handle', 'move'):
            return (d['shape'], [d['k']], True) if d['kind'] == 'handle' else (d['shape'], d['idx'], False)
        if d or self.tool != 'pan' or self.calflow:
            return None
        h = self.hit_handle(*self.mouse)
        if h:
            return h[0], [h[1]], True
        b = self.hit_body(*self.mouse)
        return (b[0], b[1], False) if b else None

    def draw_hot(self):
        hot = self.hot_part()
        if not hot:
            return
        s, idx, is_handle = hot
        pts, cv = s['pts'], self.cv
        if is_handle:
            x, y = self.c(pts[idx[0]])
            for w, col in ((4, 'black'), (2, COL['hot'])):
                cv.create_oval(x - 7, y - 7, x + 7, y + 7, outline=col, width=w, tags='cur')
            return
        if s['kind'] == 'circle':
            (cx, cy), r = self.c(pts[0]), dist(*pts) * self.z
            cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline=COL['hot'], width=3, tags='cur')
            return
        n = len(pts)
        segs = list(zip(range(n), range(1, n))) + ([(n - 1, 0)] if s['kind'] == 'poly' else [])
        for i, j in segs:
            if i in idx and j in idx:
                self.polyline([pts[i], pts[j]], COL['hot'], 'cur', width=3)

    def draw_loupe(self, W, H):
        mx, my = self.mouse
        ix, iy = self.i(mx, my)
        half, size = LOUPE_N // 2, LOUPE_N * LOUPE_MAG
        x0, y0 = math.floor(ix) - half, math.floor(iy) - half
        crop = self.img.crop((x0, y0, x0 + LOUPE_N, y0 + LOUPE_N))
        self.loupe_photo = ImageTk.PhotoImage(crop.resize((size, size), Image.NEAREST))
        lx = mx + 30 if mx + 30 + size < W else mx - 30 - size
        ly = my + 30 if my + 30 + size < H else my - 30 - size
        cv = self.cv
        cv.create_image(lx, ly, image=self.loupe_photo, anchor='nw', tags='cur')
        cv.create_rectangle(lx - 1, ly - 1, lx + size, ly + size, outline='#ffffff', tags='cur')
        cx, cy = lx + (ix - x0) * LOUPE_MAG, ly + (iy - y0) * LOUPE_MAG
        cv.create_line(lx, cy, lx + size, cy, fill=COL['preview'], tags='cur')
        cv.create_line(cx, ly, cx, ly + size, fill=COL['preview'], tags='cur')

    def pixel_hex(self, p):
        x, y = math.floor(p[0]), math.floor(p[1])
        iw, ih = self.img.size
        if 0 <= x < iw and 0 <= y < ih:
            return '#%02x%02x%02x' % self.img.getpixel((x, y))
        return '-------'

    def hint(self):
        if self.tool != 'digitize':
            return HINTS[self.tool]
        kind, axis = self.next_kind()
        if kind == 'axis':
            n = len(self.cur['pts']) + 1 if self.cur else 1
            return f'click {axis.upper()}-axis point {n}/2 (at a known {axis} value), then type values'
        if None in self.axes():
            return 'axis not calibrated: select it (pan tool) and press {c}'
        return 'click to record a point · {Y} copies all points as CSV'

    def update_hud(self):
        p = self.i(*self.mouse)
        px = self.pixel_hex(p)
        w, h = self.img.size
        rows = [('cursor', f'{p[0]:8.1f} {p[1]:8.1f} px   § {px}   zoom {self.z:.3g}×   img {w}×{h}', 'val')]
        d = self.to_data(p)
        if d:
            rows.append(('data', f'x={fmt(d[0])}  y={fmt(d[1])}', 'val'))
        if self.hover:
            rows.append(('on', f"{self.name(self.hover['shape'])}: {self.hover['text']}", 'val'))
        if self.preview:
            rows.append(('draw', f'{self.preview["kind"]}  {self.summary(self.preview)}', 'val'))
        elif self.sel in self.shapes:
            rows.append(('sel', f'{self.name(self.sel)}  {self.summary(self.sel)}', 'val'))
        sc = self.scale()
        if sc:
            src = f'{self.name(self.scale_src)}: ' if self.scale_src in self.shapes else ''
            rows.append(('scale', f'{src}1 px = {fmt(sc[0])} {sc[1]}', 'val'))
        rows.append(('tool', self.hint(), 'dim'))
        if self.msg:
            rows.append(('', self.msg, 'msg'))
        self.info.tag_configure('swatch', foreground=px if px[0] == '#' else HUD['bg'])
        self.rich(self.info, rows)

    def say(self, msg):
        self.msg = msg
        self.redraw(False)

    # ----------------------------------------------------------------- HUD
    def hud_press(self, e):
        self._hud_off = (e.x_root - self.hud.winfo_x(), e.y_root - self.hud.winfo_y())

    def hud_drag(self, e):
        self.hud_pos = [e.x_root - self._hud_off[0], e.y_root - self._hud_off[1]]
        self.hud.place(x=self.hud_pos[0], y=self.hud_pos[1])

    def start_cal(self, s):
        if s['kind'] not in CAL_KINDS + ('poly',):
            self.say('calibration applies to lines, paths, circles and areas')
            return
        self.cur = None
        self.calflow = dict(shape=s, steps=cal_steps(s['kind']), i=0, answers={}, prev=cal_previous(s))
        self.show_cal_step()

    def cal_anchor(self):
        s, key = self.calflow['shape'], self.calflow['steps'][self.calflow['i']][0]
        pts = s['pts']
        if s['kind'] == 'poly':
            return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        return pts[0] if key == 'v0' else pts[-1]

    def show_cal_step(self, error=''):
        f = self.calflow
        key, prompt = f['steps'][f['i']]
        prev = f['prev'].get(key, '')
        self.clabel.config(text=f'{prompt}:' + (f'  {error}' if error else ''),
                           fg=COL['pt'] if error else COL['sel'])
        last = f['i'] == len(f['steps']) - 1
        self.chint.config(text=' · '.join(['Enter done' if last else 'Enter next', 'Esc cancel'] + ['⌫ back'] * (f['i'] > 0)))
        placeholder = '' if key in ('v0', 'v1', 'area', 'unit') else prev or 'no'
        if not error:
            self.set_placeholder(placeholder)
        self.place_calbox()
        self.entry.focus_set()
        self.redraw(False)

    def place_calbox(self):
        x, y = self.c(self.cal_anchor())
        above = y > 110
        self.calbox.place(x=x, y=y - 16 if above else y + 16, anchor='s' if above else 'n')

    def set_placeholder(self, text):
        self.ph = text or None
        self.entry.delete(0, 'end')
        self.entry.insert(0, text)
        self.entry.config(fg=HUD['head'] if text else '#ffffff')
        self.entry.icursor(0)

    def typed(self):
        return '' if self.ph else self.entry.get().strip()

    def entry_key(self, e):
        if e.keysym == 'BackSpace' and not self.typed():
            self.cal_back()
            return 'break'
        if self.ph and e.char and e.char.isprintable():
            self.ph = None
            self.entry.delete(0, 'end')
            self.entry.config(fg='#ffffff')

    def entry_keyup(self, e):
        if self.calflow and not self.ph and not self.entry.get():
            self.show_cal_step()

    def cal_enter(self, e=None):
        f = self.calflow
        key = f['steps'][f['i']][0]
        s = f['shape']
        try:
            ans = cal_answer(key, self.typed(), f['answers'], f['prev'], s['kind'], self.scale() is not None)
        except ValueError as err:
            self.show_cal_step(str(err))
            return
        if ans is None:
            was_ref = s is self.scale_src
            self.clear_cal(s)
            self.end_cal()
            self.say(f'{self.name(s)}: calibration cleared' + ' · image back to pixels' * was_ref)
            return
        f['answers'][key] = ans
        if ans == KEEP:
            f['steps'] = [st for st in f['steps'] if st[0] != 'unit']
        f['i'] += 1
        if f['i'] < len(f['steps']):
            self.show_cal_step()
            return
        self.finish_cal(s, f['answers'])
        self.end_cal()
        self.say(f'{self.name(s)}: {self.summary(s)}')

    def finish_cal(self, s, a):
        """Apply dialogue answers. Any non-axis calibration with a second value sets the image scale."""
        k = s['kind']
        unit = a.get('unit') or (self.scale() or (0, ''))[1]
        if k == 'axis':
            s['cal'] = dict(v0=a['v0'], v1=a['v1'], unit=a['unit'], log=a['log'], cw=False)
            return
        if k == 'poly':
            self.set_scale(s, a['area'], unit)
            return
        v0, v1 = a['v0'], a['v1']
        keep = v1 == KEEP
        direction = (s.get('cal') or {}).get('dir', 1) if keep else math.copysign(1, v1 - v0)
        s['cal'] = dict(v0=v0, dir=direction, cw=a.get('cw', False))
        if not keep:
            self.set_scale(s, abs(v1 - v0), unit)

    def clear_cal(self, s):
        s['cal'] = None
        if s is self.scale_src:
            self.scale_k = self.scale_src = None

    def cal_back(self):
        if self.calflow and self.calflow['i'] > 0:
            self.calflow['i'] -= 1
            self.show_cal_step()

    def end_cal(self):
        self.calflow = None
        self.calbox.place_forget()
        self.cv.focus_set()
        self.redraw()

    # -------------------------------------------------------------- tools
    def set_tool(self, tool):
        self.cur = None
        self.tool = tool
        for name in self.buttons:
            self.paint_button(name)
        self.cv.focus_set()
        self.redraw()

    def next_kind(self):
        if self.cur:
            return self.cur['kind'], self.cur.get('axis')
        if self.tool != 'digitize':
            return self.tool, None
        have = {s['axis'] for s in self.shapes if s['kind'] == 'axis'}
        missing = [a for a in 'xy' if a not in have]
        return ('axis', missing[0]) if missing else ('pt', None)

    def add_point(self, p):
        if not self.cur:
            kind, axis = self.next_kind()
            self.cur = dict(kind=kind, pts=[], cal=None, axis=axis)
        self.cur['pts'].append(p)
        need = NEED[self.cur['kind']]
        if need and len(self.cur['pts']) >= need:
            self.finish()
        self.redraw()

    def finish(self):
        s, self.cur = self.cur, None
        minimum = NEED[s['kind']] or (3 if s['kind'] == 'poly' else 2)
        if len(s['pts']) < minimum:
            self.say(f'{s["kind"]} needs at least {minimum} points')
            return
        self.shapes.append(s)
        self.sel = s
        self.msg = ''
        if s['kind'] == 'axis':
            self.start_cal(s)
        self.redraw()

    def delete(self, s):
        self.scale_src = None if s is self.scale_src else self.scale_src
        self.shapes.remove(s)
        self.sel = None if self.sel is s else self.sel
        self.redraw()

    # ------------------------------------------------------------- events
    def on_press(self, e):
        if self.calflow:
            self.end_cal()
        self.cv.focus_set()
        self.mouse, self.shift = (e.x, e.y), bool(e.state & 1)
        self.press = (e.x, e.y)
        if self.tool == 'pan':
            h = self.hit_handle(e.x, e.y)
            b = None if h else self.hit_body(e.x, e.y)
            if h:
                self.sel = h[0]
                self.drag = dict(kind='handle', shape=h[0], k=h[1])
            elif b:
                self.sel = b[0]
                self.drag = dict(kind='move', shape=b[0], idx=b[1], start=self.i(e.x, e.y), orig=list(b[0]['pts']))
            else:
                self.drag = dict(kind='pan', x=e.x, y=e.y, t=list(self.t), moved=False, select=True)
            self.redraw()
            return
        self.add_point(self.event_point(e))

    def on_middle(self, e):
        self.drag = dict(kind='pan', x=e.x, y=e.y, t=list(self.t), moved=False, select=False)

    def on_release(self, e):
        d, self.drag = self.drag, None
        if d:
            if d['kind'] == 'pan' and d['select'] and not d['moved']:
                self.sel = self.nearest(e.x, e.y)
            self.redraw()
            return
        if self.cur and self.press and math.hypot(e.x - self.press[0], e.y - self.press[1]) > 5:
            self.add_point(self.event_point(e))
        self.press = None

    def on_double(self, e):
        if self.cur and NEED[self.cur['kind']] == 0:
            self.finish()
        elif self.tool == 'pan':
            s = self.nearest(e.x, e.y)
            if s:
                self.sel = s
                self.start_cal(s)
        else:
            self.on_press(e)

    def on_right(self, e):
        if self.cur:
            (self.finish if NEED[self.cur['kind']] == 0 else self.cancel)()
            return
        s = self.nearest(e.x, e.y)
        if s:
            self.sel = s
            self.start_cal(s)

    def cancel(self):
        self.cur = None
        self.redraw()

    def on_motion(self, e):
        self.mouse, self.shift = (e.x, e.y), bool(e.state & 1)
        d = self.drag
        if d and d['kind'] == 'pan':
            dx, dy = e.x - d['x'], e.y - d['y']
            d['moved'] |= math.hypot(dx, dy) > 3
            self.t = [d['t'][0] + dx, d['t'][1] + dy]
            self.view_touched = True
            self.redraw()
        elif d and d['kind'] == 'handle':
            pts, k = d['shape']['pts'], d['k']
            anchor = pts[k - 1] if k > 0 else pts[1] if len(pts) > 1 else None
            pts[k] = self.snapped(self.i(e.x, e.y), anchor)
            self.redraw()
        elif d and d['kind'] == 'move':
            q, (sx, sy) = self.i(e.x, e.y), d['start']
            for k in d['idx']:
                d['shape']['pts'][k] = (d['orig'][k][0] + q[0] - sx, d['orig'][k][1] + q[1] - sy)
            self.redraw()
        else:
            self.redraw(False)

    def zoom_at(self, x, y, f):
        z = min(64.0, max(0.05, self.z * f))
        f = z / self.z
        self.t = [x - (x - self.t[0]) * f, y - (y - self.t[1]) * f]
        self.z = z
        self.view_touched = True
        self.redraw()

    def on_key(self, e):
        ks, ctrl = e.keysym, bool(e.state & 4)
        if ctrl and ks == 'c':
            self.copy_panel_selection()
            return
        tool_keys = {key: name for name, key, _ in TOOLS}
        actions = {
            'Escape': self.escape,
            'q': self.quit,
            'Return': self.enter, 'KP_Enter': self.enter,
            'c': self.calibrate_selected,
            'Delete': lambda: self.sel and self.delete(self.sel),
            'BackSpace': self.backspace,
            'u': self.undo, 'z': self.undo,
            'y': self.copy_readout, 'Y': self.copy_points,
            'm': lambda: self.toggle('show_loupe'),
            'x': lambda: self.toggle('show_cross'),
            'h': self.toggle_hud,
            'question': self.toggle_help,
            'r': lambda: (setattr(self, 'view_touched', False), self.reset_view()),
            'plus': lambda: self.zoom_at(*self.mouse, 1.25), 'equal': lambda: self.zoom_at(*self.mouse, 1.25),
            'minus': lambda: self.zoom_at(*self.mouse, 0.8),
        }
        if ks == 'z' and not ctrl:
            return
        if ks in tool_keys and not ctrl:
            self.set_tool(tool_keys[ks])
        elif ks in actions:
            actions[ks]()

    def calibrate_selected(self):
        if self.sel in self.shapes:
            self.start_cal(self.sel)
        else:
            self.say('select a shape to calibrate (pan tool, click it)')

    def copy_panel_selection(self):
        try:
            text = self.root.selection_get()
        except tk.TclError:
            return
        self.copy(text, 'selection')

    def escape(self):
        if self.cur:
            self.cancel()
        elif self.sel:
            self.sel = None
            self.redraw()
        elif self.tool != 'pan':
            self.set_tool('pan')
        else:
            self.quit()

    def enter(self):
        if self.cur and NEED[self.cur['kind']] == 0:
            self.finish()
        elif self.sel:
            self.start_cal(self.sel)

    def backspace(self):
        if self.cur:
            self.cur['pts'].pop()
            self.cur = self.cur if self.cur['pts'] else None
            self.redraw()
        elif self.sel:
            self.delete(self.sel)

    def undo(self):
        if self.cur:
            self.cancel()
        elif self.shapes:
            self.delete(self.shapes[-1])

    def toggle(self, attr):
        setattr(self, attr, not getattr(self, attr))
        self.sync_cursor()
        self.redraw(False)

    def sync_cursor(self):
        self.cv.config(cursor='none' if self.show_cross else 'tcross')

    def toggle_hud(self):
        if self.hud.winfo_ismapped():
            self.hud.place_forget()
        else:
            self.hud.place(x=self.hud_pos[0], y=self.hud_pos[1])

    def toggle_help(self):
        if self.hframe.winfo_ismapped():
            self.hframe.pack_forget()
        else:
            self.hframe.pack(fill='x')

    # ------------------------------------------------------------- output
    def copy(self, text, what):
        copy_to_clipboard(self.root, text)
        self.say(f'copied {what}: {text if len(text) < 60 else text[:57] + "..."}')

    def copy_readout(self):
        p = self.i(*self.mouse)
        d = self.to_data(p)
        if self.hover:
            self.copy(self.hover['copy'], f"{self.name(self.hover['shape'])} readout")
        elif d and self.tool == 'digitize':
            self.copy(f'{fmt(d[0])}, {fmt(d[1])}', 'cursor data')
        elif self.sel in self.shapes:
            self.copy(f'{self.name(self.sel)}: {self.summary(self.sel)}', self.name(self.sel))
        else:
            self.copy(f'{p[0]:.1f}, {p[1]:.1f}', 'cursor px')

    def points_csv(self):
        rows = []
        for s in self.shapes:
            if s['kind'] != 'pt':
                continue
            p = s['pts'][0]
            d = self.to_data(p) or (math.nan, math.nan)
            rows.append(f'{fmt(d[0])},{fmt(d[1])},{p[0]:.2f},{p[1]:.2f}')
        return 'x,y,px,py\n' + '\n'.join(rows) + '\n' if rows else ''

    def copy_points(self):
        csv = self.points_csv()
        if not csv:
            self.say('no digitized points yet (tool d)')
            return
        copy_to_clipboard(self.root, csv)
        self.say(f'copied {csv.count(chr(10)) - 1} points as CSV')

    def report(self):
        out = [f'{self.name(s)}: {self.summary(s)}' for s in self.shapes if s['kind'] != 'pt']
        csv = self.points_csv()
        return '\n'.join(out + ([csv.rstrip('\n')] if csv else []))

    def quit(self):
        text = self.report()
        self.root.destroy()
        if text:
            print(text, flush=True)

    def run(self):
        self.root.mainloop()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('image', nargs='?', help='measure this image file instead of the screen')
    ap.add_argument('-d', '--delay', type=float, default=0.0, help='seconds to wait before the screenshot')
    ap.add_argument('-t', '--tool', choices=[t[0] for t in TOOLS], default='line', help='initial tool')
    args = ap.parse_args()
    time.sleep(args.delay)
    img = Image.open(args.image) if args.image else ImageGrab.grab()
    Ruler(img, args.tool, screen_mode=not args.image).run()


if __name__ == '__main__':
    sys.exit(main())
