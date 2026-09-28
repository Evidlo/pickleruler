"""Red capture frame (4 bars around an empty rectangle) centred on screen; bars sit outside the region.

  dev/capture_frame.py 300 200 "caption"      prints the region "x0 y0 w h"; stop with Ctrl+C
"""
import sys
import tkinter as tk

W, H, caption = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
T = 3
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
tk.Label(lab, text=caption, bg='#ff2d55', fg='white', font='TkFixedFont', padx=4).pack()
lab.geometry(f'+{x0 - T}+{y0 + H + T}')
wins.append(lab)


def keep_on_top():
    for w in wins:
        w.lift()
    root.after(300, keep_on_top)


keep_on_top()
print(x0, y0, W, H, flush=True)
root.mainloop()
