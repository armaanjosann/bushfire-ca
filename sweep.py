"""
Validation sweep (roadmap §5 Exp 0, quick version): beta=1, kappa=0, f=1, tau=1,
so the CA is exactly site percolation. Spanning probability vs fuel density p
should jump sharply near p_c ~ 0.407 (Moore-neighbourhood site percolation).

Ignition is the whole left edge; 'span' = fire reaches the right edge.
usage: python sweep.py [L] [R]
"""
import sys, time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from src.model import run_fire

L = int(sys.argv[1]) if len(sys.argv) > 1 else 128
R = int(sys.argv[2]) if len(sys.argv) > 2 else 100
ps = np.round(np.arange(0.30, 0.52, 0.02), 3)

t0 = time.time()
span, area = [], []
for p in ps:
    res = [run_fire(L=L, p=p, beta=1.0, kappa=0.0, seed=s, ignition="left_edge")
           for s in range(R)]
    span.append(np.mean([r["span_lr"] for r in res]))
    area.append(np.mean([r["burned_frac"] for r in res]))
    print(f"p={p:.2f}  P(span)={span[-1]:.2f}  mean burned frac={area[-1]:.3f}")
print(f"{len(ps)*R} runs in {time.time()-t0:.1f}s")

fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(ps, span, "o-", label="P(span)")
ax.plot(ps, area, "s--", label="mean burned fraction")
ax.axvline(0.407, color="grey", ls=":", label="literature $p_c$ ≈ 0.407")
ax.set_xlabel("fuel density p"); ax.set_ylabel("value")
ax.set_title(f"Percolation limit, L={L}, R={R}")
ax.legend(); fig.tight_layout()
fig.savefig("figures/validation_sweep.png", dpi=150)
print("saved figures/validation_sweep.png")
