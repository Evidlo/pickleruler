"""Red frame + caption countdown, then record the framed region and save a ping-pong looping APNG.

  dev/record_clip.py 300 200 examples/distance_anim.png    then: dev/embed_examples.py
"""
import sys
import time
import tkinter as tk

from PIL import ImageGrab

W, H, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
COUNTDOWN, SECONDS, FPS, T = 5, 1.0, 20, 3
root = tk.Tk()
root.withdraw()
x0, y0 = (root.winfo_screenwidth() - W) // 2, (root.winfo_screenheight() - H) // 2
wins = []
for x, y, w, h in [(x0 - T, y0 - T, W + 2 * T, T), (x0 - T, y0 + H, W + 2 * T, T),
                   (x0 - T, y0, T, H), (x0 + W, y0, T, H)]:
    t = tk.Toplevel(root, bg='#ff2d55')
    t.overrideredirect(True)
    t.geometry(f'{w}x{h}+{x}+{y}')
    wins.append(t)
lab = tk.Toplevel(root)
lab.overrideredirect(True)
caption = tk.Label(lab, bg='#ff2d55', fg='white', font='TkFixedFont', padx=4)
caption.pack()
lab.geometry(f'+{x0 - T}+{y0 + H + T}')
wins.append(lab)
frames, stamps = [], []


def lift():
    for w in wins:
        w.lift()


def countdown(n):
    lift()
    if n:
        caption.config(text=f'recording in {n}…')
        root.after(1000, countdown, n - 1)
        return
    caption.config(text='● REC')
    root.update()
    root.after(1, record, time.perf_counter())


def record(t0):
    now = time.perf_counter()
    if now - t0 >= SECONDS:
        return save()
    frames.append(ImageGrab.grab(bbox=(x0, y0, x0 + W, y0 + H)))
    stamps.append(now)
    delay = max(1, int((t0 + len(frames) / FPS - time.perf_counter()) * 1000))
    root.after(delay, record, t0)


def save():
    ms = round(1000 * (stamps[-1] - stamps[0]) / max(len(stamps) - 1, 1))
    loop = frames + frames[-2:0:-1]
    loop[0].save(out, save_all=True, append_images=loop[1:], duration=ms, loop=0)
    caption.config(text=f'saved {len(frames)} frames')
    print(f'{len(frames)} frames, {ms} ms/frame, {len(loop)} in loop -> {out}', flush=True)
    root.after(1200, root.destroy)


countdown(COUNTDOWN)
root.mainloop()
