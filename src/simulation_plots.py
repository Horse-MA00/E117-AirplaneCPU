"""Plot generated booking states and normal-fare observations, without fitting models."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np


_COLORS = {"cold": "#168A89", "normal": "#336DC2", "hot": "#9853A6"}
_NAMES = {"cold": ("冷門", "Low demand"), "normal": ("一般", "Typical demand"), "hot": ("熱門", "High demand")}


def _font() -> tuple[str, bool]:
    for path in (
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
    ):
        if Path(path).exists():
            font_manager.fontManager.addfont(path)
            return font_manager.FontProperties(fname=path).get_name(), True
    return "DejaVu Sans", False


def _scenario(result: dict) -> str:
    return str(result["snapshots"][0].get("scenario", result.get("truth", {}).get("scenario", "unknown")))


def _bands(ensemble_results: list[dict]) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, int]]:
    groups = defaultdict(list)
    for result in ensemble_results:
        groups[_scenario(result)].append(result["snapshots"])
    bands = {}
    for name, runs in groups.items():
        if len(runs) < 2:
            continue
        days = np.array([row["days_to_departure"] for row in runs[0]])
        if not all(np.array_equal(days, [row["days_to_departure"] for row in run]) for run in runs):
            raise ValueError("Ensemble histories must share the same snapshot days.")
        curves = np.array([[100 * row["occupancy_rate"] for row in run] for run in runs])
        lower, upper = np.quantile(curves, [0.1, 0.9], axis=0)
        bands[name] = days, lower, upper, len(runs)
    return bands


def plot_results(
    results: list[dict],
    output_dir: Path,
    ensemble_results: list[dict] | None = None,
) -> list[Path]:
    """Save overview and D28 zoom as PNG and PDF; return all four paths.

    Solid booking lines are individual runs. Shaded bands, when supplied,
    describe simulated scenario variation rather than forecast uncertainty.
    A missing fare remains a gap; it is never plotted as a zero-priced offer.
    """
    if not results or any(not result.get("snapshots") for result in results):
        raise ValueError("At least one non-empty simulation result is required.")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    font_name, chinese = _font()
    bands = _bands(ensemble_results or [])
    all_days = [row["days_to_departure"] for result in results for row in result["snapshots"]]
    start_day = max(all_days)
    outputs = []
    text = lambda zh, en: zh if chinese else en
    prices = [
        float(row[key])
        for result in results for row in result["snapshots"]
        for key in ("base_fare", "total_payable")
        if row.get("is_available") and row.get(key) is not None
    ]
    max_price = max(prices, default=100)
    price_limit = max(200, np.ceil(max_price * 1.14 / 100) * 100)

    with plt.rc_context({
        "font.family": font_name,
        "font.size": 11,
        "axes.unicode_minus": False,
        "axes.edgecolor": "#D7DFE6",
        "axes.labelcolor": "#475569",
        "text.color": "#172B40",
        "xtick.color": "#64748B",
        "ytick.color": "#64748B",
        "figure.facecolor": "#F7F9FC",
        "axes.facecolor": "white",
        "pdf.fonttype": 42,
    }):
        for filename, horizon in (("overview", start_day), ("last28days", min(28, start_day))):
            fig, axes = plt.subplots(2, len(results), figsize=(5.2 * len(results), 8.8), squeeze=False)
            fig.subplots_adjust(left=0.065, right=0.98, bottom=0.15, top=0.80, wspace=0.23, hspace=0.36)
            title = text(
                f"D{horizon} 至 D0：訂位與正常票價模擬",
                f"D{horizon} to D0: simulated bookings and normal fares",
            )
            fig.text(0.065, 0.95, title, fontsize=23, weight="bold")
            fig.text(0.065, 0.906, text(
                "每欄一班代表航班；僅正常銷售，尚未開放會員優惠。所有需求與價格均為模擬假設。",
                "One representative flight per scenario. Normal sales only; demand and prices are simulated assumptions.",
            ), fontsize=11, color="#526276")
            handles = [Line2D([], [], color="#475569", linewidth=2.5, label=text("單班模擬訂位率", "Single simulated booking history"))]
            if bands:
                handles.append(Patch(facecolor="#CBD7E3", alpha=0.55, label=text("同情境模擬 P10–P90 範圍", "Scenario simulations: P10–P90")))
            fig.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.06, 0.885), frameon=False, ncol=2, fontsize=10)

            for column, result in enumerate(results):
                rows = result["snapshots"]
                scenario = _scenario(result)
                color = _COLORS.get(scenario, "#336DC2")
                label = _NAMES.get(scenario, (scenario, scenario))[0 if chinese else 1]
                days = np.array([row["days_to_departure"] for row in rows])
                occupancy = np.array([100 * row["occupancy_rate"] for row in rows])
                booking_ax, price_ax = axes[:, column]
                capacity = int(rows[-1]["sellable_capacity"])
                booked = int(rows[-1]["net_booked_seats"])
                booking_ax.set_title(
                    f"{label}  |  " + text(f"最終 {booked}/{capacity} 位", f"Final {booked}/{capacity} seats"),
                    loc="left", fontsize=14, weight="bold", color=color, pad=12,
                )
                if scenario in bands:
                    band_days, lower, upper, count = bands[scenario]
                    booking_ax.fill_between(band_days, lower, upper, color=color, alpha=0.14, linewidth=0)
                    booking_ax.text(0.97, 0.06, text(f"範圍：{count} 次模擬", f"Band: {count} simulations"),
                                    transform=booking_ax.transAxes, ha="right", va="bottom", fontsize=9, color="#64748B")
                booking_ax.plot(days, occupancy, color=color, linewidth=2.4, zorder=3)
                booking_ax.scatter([0], [occupancy[-1]], s=30, color=color, zorder=4, clip_on=False)
                booking_ax.axhline(100, color="#CBD5E1", linestyle=":", linewidth=1)
                booking_ax.set_ylim(0, 107)
                booking_ax.set_yticks([0, 25, 50, 75, 100], labels=["0%", "25%", "50%", "75%", "100%"])
                booking_ax.set_ylabel(text("有效訂位率", "Valid booked / capacity"))

                for key, style, alpha, price_label in (
                    ("total_payable", "-", 1, text("含必付費用總價", "Total incl. mandatory fees")),
                    ("base_fare", "--", 0.7, text("正常基本票價", "Normal base fare")),
                ):
                    values = np.array([
                        float(row[key]) if row.get("is_available") and row.get(key) is not None else np.nan
                        for row in rows
                    ])
                    price_ax.step(days, values, where="post", color=color, linestyle=style,
                                  linewidth=2 if style == "-" else 1.6, alpha=alpha, label=price_label)
                price_ax.set_ylim(0, price_limit)
                price_ax.set_ylabel(text("公開報價（HKD）", "Public quote (HKD)"))
                price_ax.set_title(text("正常票價，並非會員票價", "Normal fares, not member offers"),
                                   loc="left", fontsize=11, pad=10)
                price_ax.legend(loc="upper left", frameon=False, fontsize=8.5)
                sold_out_days = [row["days_to_departure"] for row in rows
                                 if row["days_to_departure"] > 0 and row["days_to_departure"] <= horizon
                                 and not row.get("is_available")]
                if sold_out_days:
                    price_ax.text(0.97, 0.05, text("斷線＝當時無可售報價", "Gap = no available quote"),
                                  ha="right", transform=price_ax.transAxes, fontsize=8.5, color="#64748B")
                for ax in (booking_ax, price_ax):
                    ax.spines[["top", "right"]].set_visible(False)
                    ax.grid(axis="y", color="#E7ECF1", linewidth=0.7)
                    ax.set_axisbelow(True)
                    ax.set_xlim(horizon, 0)
                    if horizon > 28:
                        ax.axvspan(28, 0, color="#E0E9F4", alpha=0.35, zorder=0)
                        ax.axvline(28, color="#8296AB", linewidth=1, linestyle=":")
                        ticks = [d for d in (180, 150, 120, 90, 60, 28, 0) if d <= horizon]
                    else:
                        ticks = [d for d in (28, 21, 14, 7, 0) if d <= horizon]
                    ax.set_xticks(ticks, labels=[f"D{d}" for d in ticks])
                price_ax.set_xlabel(text("距離起飛天數（向右接近起飛）", "Days before departure →"), labelpad=8)

            fig.text(0.065, 0.075, text(
                "讀圖：訂位率可因取消而下降；報價可因促銷而下降，也會隨庫存或臨期調整。售罄／停售不是零元票。",
                "Bookings may fall after cancellations. Promotions can lower fares. Sold-out or closed sales do not mean a zero fare.",
            ), fontsize=10, color="#526276")
            fig.text(0.065, 0.043, text(
                "陰影是模擬情境差異，並非模型預測信賴區間；D0 為停售結算快照，不再提供報價。",
                "Bands describe simulated variation, not calibrated forecast intervals. D0 is the sales-cutoff outcome, with no quote.",
            ), fontsize=9, color="#64748B")
            for suffix in ("png", "pdf"):
                path = output_dir / f"{filename}.{suffix}"
                fig.savefig(path, dpi=170 if suffix == "png" else 150, facecolor=fig.get_facecolor())
                outputs.append(path)
            plt.close(fig)
    return outputs
