import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
import matplotlib.ticker as mticker


# ============================================================
# 1) Data loading (robust auto-parse; keeps original behavior)
# ============================================================
def _detect_data_start(lines):
    """
    Find the first row where the first two fields are numeric.
    Return (start_row_index, delimiter) where delimiter is one of:
    ',', ';', '\\t', or 'whitespace'.
    """
    float_re = re.compile(r'^[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?$')

    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        for d in [",", ";", "\t"]:
            parts = [p.strip() for p in s.split(d)]
            if len(parts) >= 2 and float_re.match(parts[0]) and float_re.match(parts[1]):
                return i, d

    for i, line in enumerate(lines):
        parts = line.strip().split()
        if len(parts) >= 2 and float_re.match(parts[0]) and float_re.match(parts[1]):
            return i, "whitespace"

    raise ValueError("Cannot find numeric data start (two numeric columns).")


def load_rf_csv(path: str) -> pd.DataFrame:
    """
    Load RF spectrum data from instrument-exported files.
    Returns a DataFrame with numeric columns: x, y.
    """
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    start_idx, delim = _detect_data_start(lines)

    if delim == "whitespace":
        df = pd.read_csv(
            path,
            skiprows=start_idx,
            header=None,
            delim_whitespace=True,
            engine="python",
            on_bad_lines="skip",
        )
    else:
        df = pd.read_csv(
            path,
            skiprows=start_idx,
            header=None,
            sep=delim,
            engine="python",
            on_bad_lines="skip",
        )

    df = df.iloc[:, :2].copy()
    df.columns = ["x", "y"]

    # Remove non-numeric tail rows (if any)
    df["x"] = pd.to_numeric(df["x"], errors="coerce")
    df["y"] = pd.to_numeric(df["y"], errors="coerce")
    df = df.dropna().reset_index(drop=True)

    return df


# ============================================================
# 2) NEW interface: show-only window by points around max peak
#    (plot ALL points, only restrict x-axis display range)
# ============================================================
def xlim_around_peak_by_points(df: pd.DataFrame, n_points: int | None):
    """
    Return (xmin, xmax) corresponding to a window of n_points centered at the
    strongest peak (max y). Does NOT crop data.

    - n_points=None      -> None (show full spectrum)
    - n_points>=len(df)  -> None
    - Peak near edges    -> window clamps to available indices
    """
    if n_points is None:
        return None

    n_points = int(n_points)
    if n_points <= 0:
        raise ValueError("n_points must be a positive integer or None.")

    total = len(df)
    if n_points >= total:
        return None

    x = df["x"].to_numpy()
    y = df["y"].to_numpy()
    peak_idx = int(y.argmax())

    left = n_points // 2
    right = n_points - left  # keeps total == n_points

    start = peak_idx - left
    end = peak_idx + right  # end is exclusive

    # clamp to valid range while keeping exactly n_points
    if start < 0:
        start, end = 0, n_points
    if end > total:
        end = total
        start = total - n_points

    xmin = float(x[start])
    xmax = float(x[end - 1])

    # Handle rare non-monotonic x
    if xmin > xmax:
        xmin, xmax = xmax, xmin

    return xmin, xmax


# ============================================================
# 3) Paper-style plot (square + tight margins + smaller fonts)
#    + Mark the strongest peak (max y)
# ============================================================
def plot_rf_spectrum(
    df: pd.DataFrame,
    n_points: int | None = None,   # <<< control shown range; None keeps original full display
    title: str | None = None,
    out_png: str = "rf_spectrum_plot.png",
    out_pdf: str = "rf_spectrum_plot.pdf",
    mark_peak: bool = True,        # <<< NEW: mark the highest spike
):
    x = df["x"].to_numpy()
    y = df["y"].to_numpy()

    # --- strongest peak (global max y) ---
    peak_idx = int(np.argmax(y))
    peak_x = float(x[peak_idx])
    peak_y = float(y[peak_idx])

    # Auto unit
    xmax = float(np.nanmax(x))
    if xmax >= 1e9:
        x_plot, x_unit, scale = x / 1e9, "GHz", 1e9
    elif xmax >= 1e6:
        x_plot, x_unit, scale = x / 1e6, "MHz", 1e6
    elif xmax >= 1e3:
        x_plot, x_unit, scale = x / 1e3, "kHz", 1e3
    else:
        x_plot, x_unit, scale = x, "Hz", 1.0

    # Journal-like typography (compact)
    mpl.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
        "font.size": 6.5,
        "axes.labelsize": 6.5,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        "axes.linewidth": 0.9,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.size": 0.2,
        "ytick.major.size": 0.2,
        "xtick.minor.size": 1.6,
        "ytick.minor.size": 1.6,
        "xtick.major.width": 0.9,
        "ytick.major.width": 0.9,
        "xtick.minor.width": 0.7,
        "ytick.minor.width": 0.7,
        "savefig.dpi": 800,
    })

    # Square panel
    fig, ax = plt.subplots(figsize=(2.55, 2.55), dpi=260)
    ax.plot(x_plot, y, linewidth=0.75)

    ax.set_xlabel(f"Frequency ({x_unit})", labelpad=1.5)
    ax.set_ylabel("Power (dBm)", labelpad=1.5)

    if title:
        ax.set_title(title, fontsize=7.5, pad=2)

    ax.minorticks_on()
    ax.xaxis.set_major_locator(mticker.MaxNLocator(5))
    ax.yaxis.set_major_locator(mticker.MaxNLocator(5))

    # Force square frame
    ax.set_box_aspect(1)

    # Show-only x-range around peak by points
    xlim = xlim_around_peak_by_points(df, n_points)
    if xlim is not None:
        xmin, xmax_ = xlim
        ax.set_xlim(xmin / scale, xmax_ / scale)

    # --- Mark the highest spike ---
    if mark_peak:
        px = peak_x / scale
        # vertical line + marker + label
        ax.plot([px], [peak_y], marker="o", color = "black", markersize=0.7)

        label = f"({px:.6g}{x_unit}, {peak_y:.2f}dBm)"
        # Put text near top, slightly right of the peak if possible
        x0, x1 = ax.get_xlim()
        y0, y1 = ax.get_ylim()
        x_text = min(px + 0.02 * (x1 - x0), x1 - 0.02 * (x1 - x0))
        y_text = y1 - 0.04 * (y1 - y0)
        ax.text(x_text, y_text, label, fontsize=6, va="top")

    # Tight margins (reduce whitespace)
    fig.subplots_adjust(left=0.16, right=0.995, bottom=0.16, top=0.995)
    # ===== 在这里加：固定y范围 + 小刻度每5dB + 不要大刻度 =====
    ax.set_ylim(-125, -75)

    # 5 dB 一根刻度线：用 minor 画“每5的线”
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(5))

    # 10 dB 显示一次数字：用 major 放“每10的带数字刻度”
    ax.yaxis.set_major_locator(mticker.MultipleLocator(10))

    # 从 -125 开始显示：强制主刻度落在 -125, -115, ...（间隔10）
    ax.set_yticks(np.arange(-125, -75 + 1, 10))

    # 确保小刻度线显示出来（有时候被设置/样式影响）
    ax.tick_params(axis="y", which="minor", length=1.6, width=0.7)
    ax.tick_params(axis="y", which="major", length=3.0, width=0.9)
    # ================================================
    fig.savefig(out_png, bbox_inches="tight", pad_inches=0.01)
    fig.savefig(out_pdf, bbox_inches="tight", pad_inches=0.01)
    plt.show()


# ============================================================
# 4) One-stop API
# ============================================================
def run_plot(
    path: str,
    n_points: int | None = None,   # None -> full spectrum, otherwise show window around max peak
    title: str | None = None,
    out_png: str = "rf_spectrum_plot.png",
    out_pdf: str = "rf_spectrum_plot.pdf",
    mark_peak: bool = True,
):
    df = load_rf_csv(path)
    plot_rf_spectrum(
        df,
        n_points=n_points,
        title=title,
        out_png=out_png,
        out_pdf=out_pdf,
        mark_peak=mark_peak,
    )


if __name__ == "__main__":
    # Use:
    # - n_points=None: show full spectrum (original behavior)
    # - n_points=2000: still plot all points, but x-axis only shows the window of 2000 points around the max peak
    run_plot(
        path="1.29 200mw.csv",
        n_points=2000,
        title=None,
        out_png="rf_spectrum_plot_xlim_peak.png",
        out_pdf="rf_spectrum_plot_xlim_peak.pdf",
        mark_peak=True,
    )
