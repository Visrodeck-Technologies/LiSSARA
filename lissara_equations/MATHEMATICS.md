# Lissara Equations — Mathematics Reference

`lissara_equations` is the single source of truth for the curve mathematics used
across Lissara. It is **pure Python standard library only** (no NumPy, OpenCV,
PIL, or SVG renderer). This document records the formulas, the implementation
decisions, and — importantly — the points where the implementation is an
*approximation* rather than an exact computation.

Notation: bold `P` denotes a 2D point/vector `(x, y)`; `t` is the curve
parameter; `B(t)` is a curve; a prime (`'`) is `d/dt`.

---

## 1. Data model

A curve is a plain dictionary. The **canonical cubic record** is:

```python
{
  "control_points": [P0, P1, P2, P3],
  "x_coeffs": {"a3": ..., "a2": ..., "a1": ..., "a0": ...},
  "y_coeffs": {"b3": ..., "b2": ..., "b1": ..., "b0": ...},
}
```

The asymmetric `a*`/`b*` naming is **intentional** and must not be renamed:
`lissara_engine.PathRecord`, the MathScene JSON, and the SVG exporter read these
keys directly.

A quadratic record additionally carries `"degree": 2` and uses keys
`a2/a1/a0` in both `x_coeffs` and `y_coeffs`.

---

## 2. Points and vectors (`points.py`)

| Operation | Formula |
|---|---|
| distance | `sqrt((x1-x0)^2 + (y1-y0)^2)` |
| distance² | `(x1-x0)^2 + (y1-y0)^2` |
| lerp (clamped) | `P0 + clamp(t,0,1)·(P1-P0)` |
| dot | `x0·x1 + y0·y1` |
| cross (scalar) | `x0·y1 - y0·x1` |
| length | `sqrt(x^2 + y^2)` |
| normalize | `P / length(P)`, `(0,0)` if zero |
| perpendicular (CCW) | `(-y, x)` |
| angle between | `atan2(cross, dot)` |
| polar | `r·(cos θ, sin θ)` |

`validate_point` raises `TypeError` for inputs that are not a 2-element
numeric pair. All coercions go through `_to_float`, which returns `0.0` on a
non-numeric value so that numpy scalars and strings behave predictably.

---

## 3. Line segments (`segments.py`)

A segment is `(A, B)`. Point-on-segment is `A + t(B-A)`. The closest point to a
target `Q` uses the projection parameter

```
t = dot(Q-A, B-A) / |B-A|^2,   clamped to [0, 1]
```

so points beyond an endpoint clamp to that endpoint (nearest-endpoint
behaviour). Segment–segment intersection solves the 2×2 system for `t1, t2`
and reports a hit only when both lie in `[0, 1]`.

---

## 4. Quadratic Bézier (`quadratic.py`)

Bernstein form and its power basis:

```
B(t) = (1-t)^2 P0 + 2(1-t)t P1 + t^2 P2
     = a2 t^2 + a1 t + a0
a2 = P0 - 2 P1 + P2
a1 = 2 (P1 - P0)
a0 = P0
```

* `B'(t) = 2 a2 t + a1`
* `B''(t) = 2 a2` (constant)
* Curvature `k(t) = (x'y'' - y'x'') / (x'^2 + y'^2)^(3/2)`, signed; `0` when speed is `0`.
* Degree elevation to cubic: `Q = (P0, (P0+2P1)/3, (2P1+P2)/3, P2)` — **exact**.
* `quadratic_from_three_points` inverts `B(t_mid) = p_mid` for `P1`.

**Approximations.** `quadratic_arc_length` is a uniform polyline sum (default 32
segments) — approximate. `quadratic_bounding_box` is **exact**: it evaluates the
endpoints and the interior critical points `t = -a1/(2 a2)` that fall in `(0,1)`.

---

## 5. Cubic Bézier (`cubic.py`)

Bernstein form and its power basis:

```
B(t) = (1-t)^3 P0 + 3(1-t)^2 t P1 + 3(1-t) t^2 P2 + t^3 P3
     = a3 t^3 + a2 t^2 + a1 t + a0
a3 = -P0 + 3 P1 - 3 P2 + P3
a2 =  3 P0 - 6 P1 + 3 P2
a1 = -3 P0 + 3 P1
a0 =  P0
```

Derivatives:

```
B'(t)  = 3(1-t)^2 (P1-P0) + 6(1-t)t (P2-P1) + 3 t^2 (P3-P2)
       = 3 a3 t^2 + 2 a2 t + a1
B''(t) = 6 a3 t + 2 a2
```

* `tangent` returns the unit `B'`; `normal` is the unit tangent rotated +90° (CCW).
* `tangent_angle = atan2(y', x')`.
* Curvature `k(t) = (x'y'' - y'x'') / (x'^2 + y'^2)^(3/2)` (signed; `0` at zero speed).
* `evaluate` uses the power basis (fast, Horner-friendly). `evaluate_de_casteljau`
  uses repeated `lerp` and is numerically stable outside `[0, 1]`; the two agree
  on `[0, 1]` to floating-point tolerance (verified by tests).
* `is_degenerate` classifies a cubic as `point` (all control points coincide),
  `line` (all control points collinear), and/or `coincident_endpoints` (`P0==P3`).

**Approximation.** `arc_length` is a uniform polyline sum (default 64 segments).
Exact length requires integrating `|B'(t)|`, which is a degree-4 polynomial in
`t` under a square root and has no elementary antiderivative in general.

---

## 6. Cross-curve algorithms (`algorithms.py`)

### Subdivision (de Casteljau) — exact
Splitting at `t`:

```
Q0=lerp(P0,P1,t)  Q1=lerp(P1,P2,t)  Q2=lerp(P2,P3,t)
R0=lerp(Q0,Q1,t)  R1=lerp(Q1,Q2,t)
S =lerp(R0,R1,t)                      # point on curve
left  = (P0, Q0, R0, S)
right = (S, R1, Q2, P3)
```

This preserves the geometric locus exactly (both halves reproduce the original
curve on their parameter sub-ranges). `split_cubic_many` re-maps each split
parameter into the local coordinate of the remaining right-hand sub-curve.

### Extrema and bounding box — exact
`B'(t) = 3 a3 t^2 + 2 a2 t + a1 = 0` is solved per axis with the numerically
stable quadratic formula

```
q = -0.5 (b + sign(b) sqrt(b^2 - 4ac));   roots = q/a and c/q
```

keeping roots in `[0, 1]`. `cubic_bounding_box` then takes the min/max over the
two endpoints **and** the interior extrema — this is the *exact* tight box.
`cubic_bounding_box_fast` returns the control-point hull, which is a safe
over-approximation (the curve lies within its convex hull).

### Adaptive flattening — approximate
`flatten_cubic_adaptive` recursively bisects a sub-curve until both interior
control points are within `flatness` of the `P0–P3` chord (perpendicular
distance via the cross product), capped at `max_depth`. Output is a piecewise
linear approximation; tighter `flatness` ⇒ more points.

### Closest point — approximate
`closest_point_on_cubic` performs a coarse scan at `n_samples+1` parameters,
then a bounded ternary search around the best sample. The refined candidate only
replaces the incumbent when it is genuinely closer, so a true boundary minimum
(`t=0` or `t=1`) is never discarded. Exact closest-point requires solving a
degree-5 polynomial `(B(t)-Q)·B'(t)=0`, which is why this is approximate.

---

## 7. Fitting and continuity (`fitting.py`)

### Chord-length parameterization — approximation
Each sample point is assigned the cumulative chord length normalized to `[0,1]`.
This is a cheap first-order approximation to arc-length parameterization; the
degenerate all-coincident case falls back to uniform spacing.

### `fit_cubic_segment` — accurate interpolation, approximate interior
Endpoints are interpolated **exactly** (`P0 = first`, `P3 = last`). Interior
control points are set to the data points at the parameters nearest `u = 1/3`
and `u = 2/3`. This is a speed/stability heuristic, **not** a least-squares
optimum. `len==2` yields a straight cubic `(P0, P0, P3, P3)`.

### `fit_cubic_least_squares` — least squares (endpoints fixed)
For fixed `P0, P3`, solving for `P1, P2` minimizes squared error. With Bernstein
weights `b0..b3`:

```
target_i = data_i - P0 b0(t_i) - P3 b3(t_i)
A = [[Σ b1², Σ b1 b2], [Σ b1 b2, Σ b2²]]
rhs_axis = [Σ b1·target, Σ b2·target]
```

`A · [P1, P2]^T = rhs` is solved per axis by a 2×2 determinant (Cramer). A
near-singular system (`|det| < 1e-12`) falls back to `fit_cubic_segment`.

### Fit error — conservative upper bound
`cubic_fit_error` is the maximum distance from each data point to the **sampled**
polyline of the fitted curve. Because it compares against samples, it slightly
*over-estimates* true geometric error; this is deliberate so it is safe as a
subdivision trigger.

### Continuity predicates
* **C0**: `distance(A_end, B_start) ≤ tol`.
* **C1**: derivative vectors match (`|A'(1) - B'(0)| ≤ tol`).
* **G1**: unit tangents match in direction (`|t_A(1) - t_B(0)| ≤ tol`).
* `enforce_c0_chain` snaps each curve's start onto the previous curve's end and
  rebuilds the coefficient cache via `make_cubic`.

---

## 8. Exact vs approximate — quick reference

| Function | Nature |
|---|---|
| power-basis / de Casteljau evaluation | exact (FP tolerance) |
| derivatives, tangent, normal, curvature | exact |
| quadratic/cubic bounding box (tight) | exact |
| de Casteljau split | exact |
| degree elevation (quad→cubic) | exact |
| closest point on segment | exact |
| quadratic/cubic arc length | approximate (polyline) |
| adaptive / uniform flattening | approximate |
| closest point on cubic | approximate (scan + refine) |
| chord-length parameterization | approximate |
| `fit_cubic_segment` interior points | heuristic |
| fit error | conservative over-estimate |
| `fit_cubic_least_squares` | least squares (endpoints fixed) |

---

## 9. References

1. Pomax, *A Primer on Bézier Curves*, https://pomax.github.io/bezierinfo/
   (Bernstein/power-basis conversion, de Casteljau, extrema, bounding boxes,
   curve fitting, curvature).
2. Python `math` — https://docs.python.org/3/library/math.html
3. Python `typing` — https://docs.python.org/3/library/typing.html
4. W3C, *SVG 2 — Paths*, https://www.w3.org/TR/SVG/latest/paths.html
   (the cubic `C` command the exporter emits).
