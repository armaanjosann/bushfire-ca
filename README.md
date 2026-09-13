# Bushfire spread CA with fuel management (CITS4403)

Stochastic 2D cellular automaton of bushfire spread on an L×L lattice with a
Moore neighbourhood, wind bias, and per-cell fuel load. See
`checkpoint1-bushfire-ca-roadmap.md` for the full plan.

## Quick start

```bash
pip install numpy matplotlib pillow
python sweep.py 128 100     # validation: percolation transition near p ≈ 0.41 (~30 s)
python animate.py           # figures/fire.gif — a fire spreading under an easterly wind
```

## What's here

- `src/model.py` — the CA: states, wind kernel, `step()`, `run_fire()`
- `sweep.py` — Exp 0 quick version: P(span) and burned fraction vs fuel density p
- `animate.py` — GIF of one fire plus a still of the final scar
- `figures/` — outputs

## Model (short)

A burning cell ignites each neighbour j with `P = clip(β · w(θ) · f_j, 0, 1)`,
where `w` is a von Mises wind kernel (κ = strength, φ = direction) normalised
to mean 1 over the 8 directions, and `f_j` is the target cell's fuel load.
With β = 1, κ = 0, f ≡ 1 this reduces exactly to site percolation, which is the
validation baseline. Boundaries are absorbing; update is synchronous.

## Current result

Left-edge ignition, L = 128, 100 replicates per p: spanning probability goes
0.05 → 0.39 → 0.92 → 1.00 across p = 0.38 → 0.40 → 0.42 → 0.44, i.e. the
transition sits at p ≈ 0.41, matching the literature value (~0.407) for
Moore-neighbourhood site percolation.

## Not yet done

Treatment geometries (`geometries.py`), metrics/analysis, parallel sweep runner,
finite-size scaling. Those are Sprints 1–2 in the roadmap.
