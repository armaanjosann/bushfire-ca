"""
Make a GIF of a single fire spreading with an easterly wind, plus a still of
the final burn scar.  usage: python animate.py
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.animation import FuncAnimation, PillowWriter
from src.model import run_fire

L, p, beta, kappa = 100, 0.60, 0.8, 2.0
r = run_fire(L=L, p=p, beta=beta, kappa=kappa, phi=0.0, seed=3,
             ignition="centre", record=True)
frames = r["frames"]
print(f"{len(frames)} frames, burned {r['burned_frac']:.2f} of grid, span={r['span']}")

cmap = ListedColormap(["#f5f0e6", "#4a7c3f", "#ff6a00", "#222222"])  # empty, fuel, burning, burnt
fig, ax = plt.subplots(figsize=(5, 5))
im = ax.imshow(frames[0], cmap=cmap, vmin=0, vmax=3, interpolation="nearest")
ax.set_xticks([]); ax.set_yticks([])
title = ax.set_title("")

def update(i):
    im.set_data(frames[i])
    title.set_text(f"t={i}   p={p}  β={beta}  κ={kappa} (wind → east)")
    return im, title

anim = FuncAnimation(fig, update, frames=len(frames), interval=80, blit=False)
anim.save("figures/fire.gif", writer=PillowWriter(fps=12))
print("saved figures/fire.gif")

fig2, ax2 = plt.subplots(figsize=(5, 5))
ax2.imshow(frames[-1], cmap=cmap, vmin=0, vmax=3, interpolation="nearest")
ax2.set_xticks([]); ax2.set_yticks([]); ax2.set_title("final burn scar")
fig2.savefig("figures/fire_final.png", dpi=150, bbox_inches="tight")
print("saved figures/fire_final.png")
