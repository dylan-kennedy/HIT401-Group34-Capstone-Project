"""
HIT401 Group 34 - Groundwater Report Card toolkit
Demonstration / validation of the four core functions on SYNTHETIC data.
These are not results from the real NT bore data (Bores_w_wl_data.xlsx etc.)
supplied by Cat Kutay on 6 Aug 2026 - they exist to show the functions are
implemented correctly and ready to run the moment that data is loaded.

Run: python3 toolkit_demo.py   (writes toolkit_demo.png)
"""
import numpy as np
import pandas as pd
from scipy.special import exp1          # Theis well function W(u) = E1(u)
from scipy.stats import linregress
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

rng = np.random.default_rng(34)  # Group 34, for reproducibility

# ---------------------------------------------------------------
# 1. DRAWDOWN: Theis (1935) forward model + Cooper-Jacob (1946) fit
# ---------------------------------------------------------------
def theis_drawdown(t_days, Q, T, S, r):
    """Theis (1935) confined-aquifer drawdown, s (m), at radius r (m) and time t (days)."""
    t = np.asarray(t_days, dtype=float)
    u = (r ** 2 * S) / (4 * T * t)
    return (Q / (4 * np.pi * T)) * exp1(u)

def cooper_jacob_fit(t_days, s_obs, Q, r):
    """Cooper-Jacob (1946) straight-line fit of s vs log10(t) to recover T and S."""
    t = np.asarray(t_days, dtype=float)
    logt = np.log10(t)
    slope, intercept, rvalue, _, _ = linregress(logt, s_obs)
    T_fit = (2.30 * Q) / (4 * np.pi * slope)
    t0 = 10 ** (-intercept / slope)          # x-intercept (s = 0)
    S_fit = (2.25 * T_fit * t0) / (r ** 2)
    return T_fit, S_fit, rvalue ** 2

# True aquifer parameters (synthetic "pumping test")
T_true, S_true, Q_true, r_obs = 250.0, 2.0e-4, 800.0, 30.0
t_days = np.geomspace(0.02, 2.0, 40)
s_true = theis_drawdown(t_days, Q_true, T_true, S_true, r_obs)
s_noisy = s_true + rng.normal(0, 0.03, size=t_days.shape)
T_fit, S_fit, r2 = cooper_jacob_fit(t_days, s_noisy, Q_true, r_obs)

# ---------------------------------------------------------------
# 2. BACKFILLING: linear interpolation vs nearest-gauge regression
# ---------------------------------------------------------------
def backfill_linear(series):
    return series.interpolate(method="linear", limit_direction="both")

def backfill_regression(target, donor):
    """Fill target's gaps using an OLS regression against a correlated donor gauge."""
    mask = target.notna() & donor.notna()
    slope, intercept, *_ = linregress(donor[mask], target[mask])
    filled = target.copy()
    gap = target.isna() & donor.notna()
    filled[gap] = slope * donor[gap] + intercept
    return filled

days = pd.date_range("2025-01-01", periods=120, freq="D")
true_flow = 5 + 2 * np.sin(np.linspace(0, 6 * np.pi, 120)) + rng.normal(0, 0.2, 120)
donor_flow = 0.8 * true_flow + rng.normal(0, 0.3, 120) + 1.5   # correlated nearby gauge
target = pd.Series(true_flow, index=days)
gap_idx = rng.choice(120, size=25, replace=False)
observed = target.copy()
observed.iloc[gap_idx] = np.nan
donor = pd.Series(donor_flow, index=days)

filled_lin = backfill_linear(observed)
filled_reg = backfill_regression(observed, donor)
rmse_lin = np.sqrt(np.mean((filled_lin.iloc[gap_idx] - target.iloc[gap_idx]) ** 2))
rmse_reg = np.sqrt(np.mean((filled_reg.iloc[gap_idx] - target.iloc[gap_idx]) ** 2))

# ---------------------------------------------------------------
# 3. BASEFLOW SEPARATION: one-parameter recursive digital filter
#    (per the filter class evaluated by Nathan & McMahon, 1990)
# ---------------------------------------------------------------
def baseflow_filter(streamflow, alpha=0.925, passes=3):
    q = np.asarray(streamflow, dtype=float)
    b = q.copy()
    for p in range(passes):
        f = np.zeros_like(q)
        seq = range(1, len(q)) if p % 2 == 0 else range(len(q) - 2, -1, -1)
        prev = 0 if p % 2 == 0 else len(q) - 1
        for i in seq:
            f[i] = alpha * f[prev] + ((1 + alpha) / 2) * (q[i] - q[prev]) if p == 0 else f[i]
            prev = i
        if p == 0:
            qf = np.clip(q - f, 0, None)
        b = np.minimum(b, np.clip(q - f, 0, None)) if p > 0 else qf
    return np.minimum(b, q)

t2 = np.arange(200)
baseflow_true = 3 + 0.5 * np.sin(t2 / 30)
quickflow = np.zeros(200)
for peak in [20, 70, 120, 160]:
    quickflow += 8 * np.exp(-0.5 * ((t2 - peak) / 4) ** 2)
streamflow = baseflow_true + quickflow + rng.normal(0, 0.1, 200)
baseflow_est = baseflow_filter(streamflow)

# ---------------------------------------------------------------
# 4. CHEMICAL CONNECTIVITY SCREEN: similarity between bore chemistries
# ---------------------------------------------------------------
bores = ["RN01", "RN02", "RN03", "RN04", "RN05"]
chem = pd.DataFrame({
    "EC_uS_cm": [420, 435, 980, 410, 1500],
    "Cl_mg_L": [35, 38, 210, 33, 340],
    "HCO3_mg_L": [180, 175, 90, 190, 60],
}, index=bores)
z = (chem - chem.mean()) / chem.std()
dist = pd.DataFrame(index=bores, columns=bores, dtype=float)
for a in bores:
    for b in bores:
        dist.loc[a, b] = np.sqrt(((z.loc[a] - z.loc[b]) ** 2).sum())

# ---------------------------------------------------------------
# Figure
# ---------------------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(11, 8))

ax = axes[0, 0]
ax.plot(t_days, s_noisy, "o", ms=4, label="synthetic \"observed\" drawdown")
ax.plot(t_days, theis_drawdown(t_days, Q_true, T_fit, S_fit, r_obs), "-",
        label=f"Cooper-Jacob fit (T={T_fit:.0f} m2/d, S={S_fit:.1e})")
ax.set_xscale("log"); ax.set_xlabel("time (days)"); ax.set_ylabel("drawdown s (m)")
ax.set_title(f"1. Drawdown: true T={T_true:.0f}, fitted T={T_fit:.0f} m2/d (R2={r2:.3f})")
ax.legend(fontsize=8); ax.invert_yaxis()

ax = axes[0, 1]
ax.plot(target.index, target, "k-", lw=1, label="true (unknown in practice)")
ax.plot(observed.index, observed, "o", ms=3, color="gray", label="observed (gaps=NaN)")
ax.plot(target.index[gap_idx], filled_lin.iloc[gap_idx], "x", color="tab:blue",
        label=f"linear interp (RMSE={rmse_lin:.2f})")
ax.plot(target.index[gap_idx], filled_reg.iloc[gap_idx], "+", color="tab:red",
        label=f"donor regression (RMSE={rmse_reg:.2f})")
ax.set_title("2. Backfilling: two methods compared on withheld points")
ax.legend(fontsize=7); ax.tick_params(axis='x', labelrotation=30)

ax = axes[1, 0]
ax.plot(t2, streamflow, color="steelblue", lw=1, label="total streamflow")
ax.plot(t2, baseflow_est, color="darkorange", lw=1.5, label="estimated baseflow")
ax.plot(t2, baseflow_true, "--", color="gray", lw=1, label="true baseflow (synthetic)")
ax.set_title("3. Baseflow separation (digital filter)")
ax.legend(fontsize=8); ax.set_xlabel("day")

ax = axes[1, 1]
im = ax.imshow(dist.values.astype(float), cmap="viridis_r")
ax.set_xticks(range(len(bores))); ax.set_xticklabels(bores)
ax.set_yticks(range(len(bores))); ax.set_yticklabels(bores)
ax.set_title("4. Chemical similarity (lower=more alike) -> likely connectivity")
fig.colorbar(im, ax=ax, shrink=0.8, label="standardised distance")

fig.suptitle("Fig. 4-1  Group 34 toolkit - validated on synthetic data pending real NT bore data", y=1.02)
fig.tight_layout()
fig.savefig("toolkit_demo.png", dpi=150, bbox_inches="tight")

print(f"Drawdown fit: T_true={T_true}, T_fit={T_fit:.1f}, S_true={S_true:.1e}, S_fit={S_fit:.1e}, R2={r2:.4f}")
print(f"Backfill RMSE: linear={rmse_lin:.3f}, regression={rmse_reg:.3f}")
print(f"Baseflow index (mean baseflow/mean total): {baseflow_est.mean()/streamflow.mean():.3f}")
print("Chemical distance matrix:")
print(dist.round(2))
print("Nearest pair (excluding self):",
      dist.replace(0, np.nan).stack().idxmin())
