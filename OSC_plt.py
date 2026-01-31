import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import find_peaks

# ========================================
# 配置参数（方便修改）
# ========================================
ATTR_FILE = "RefCurve_2026-01-28_0_230124.csv"
WFM_FILE = "RefCurve_2026-01-28_0_230124.Wfm.csv"

PEAK_HEIGHT_RATIO = 0.5  # 峰值检测阈值（最大值的50%）
MIN_PEAK_DISTANCE = 100  # 两个峰之间最小距离（采样点数）
MAX_DATA_POINTS = 100000  # 最大数据点数限制


# ========================================
# 1. 读取属性文件
# ========================================
def read_attributes(filename):
    """读取示波器属性文件，返回字典"""
    attrs = {}
    with open(filename, 'r') as f:
        for line in f:
            if ':' in line:
                key, value = line.strip().split(':', 1)
                attrs[key] = value.rstrip(':')  # 去除末尾冒号
    return attrs


# ========================================
# 2. 读取波形数据
# ========================================
def read_waveform(filename):
    """读取波形CSV文件，以x=0为中心左右各取一半数据"""
    df = pd.read_csv(filename, header=None)
    time = df.iloc[:, 0].values
    voltage = df.iloc[:, 1].values

    # 找到最接近0的索引
    zero_idx = np.argmin(np.abs(time))

    # 以0为中心左右各取一半
    half = MAX_DATA_POINTS // 2
    start_idx = max(0, zero_idx - half)
    end_idx = min(len(time), zero_idx + half)

    return time[start_idx:end_idx], voltage[start_idx:end_idx]


# ========================================
# 3. 绘制波形并标注脉冲间隔
# ========================================
def plot_pulses(time, voltage, attrs):
    """绘制锁模激光脉冲图并标注间隔"""

    # 转换时间单位为纳秒
    time_ns = time * 1e9

    # 检测脉冲峰值
    threshold = np.min(voltage) + (np.max(voltage) - np.min(voltage)) * PEAK_HEIGHT_RATIO
    peaks, _ = find_peaks(voltage, height=threshold, distance=MIN_PEAK_DISTANCE)
    print(f"检测到 {len(peaks)} 个脉冲")

    # 创建图形
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(time_ns, voltage, 'b-', linewidth=1)

    # 标注中间两个相邻脉冲的间隔
    if len(peaks) >= 2:
        mid = len(peaks) // 2
        p1, p2 = peaks[mid], peaks[mid + 1]

        t1, t2 = time_ns[p1], time_ns[p2]
        dt_ns = t2 - t1
        freq_mhz = 1e3 / dt_ns  # 频率 = 1/周期

        # 箭头高度
        arrow_y = max(voltage[p1], voltage[p2]) * 1.05

        # 画箭头
        ax.annotate('', xy=(t1, arrow_y), xytext=(t2, arrow_y),
                    arrowprops=dict(arrowstyle='<->', color='black', lw=1.5))

        # 画辅助虚线
        ax.vlines([t1, t2], np.min(voltage), arrow_y,
                  colors='black', linestyles='--', alpha=0.5)

        # 标注文字
        label = f"Δt = {dt_ns:.3f} ns\nFreq = {freq_mhz:.3f} MHz"
        ax.text((t1 + t2) / 2, arrow_y, label, ha='center', va='bottom',
                color='black', fontweight='bold',
                bbox=dict(boxstyle='round', facecolor='white', edgecolor='black'))

        print(f"脉冲间隔: {dt_ns:.3f} ns, 重复频率: {freq_mhz:.3f} MHz")

    # 设置坐标轴
    source = attrs.get('Source', 'Unknown')

    ax.set_xlim(time_ns[0], time_ns[-1])
    ax.set_xlabel('Time (ns)', fontsize=12)
    ax.set_ylabel('Voltage (V)', fontsize=12)
    # ax.set_title(f'Timing pulse - {source}', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.5)

    plt.tight_layout()
    plt.show()


# ========================================
# 主程序
# ========================================
if __name__ == "__main__":
    attrs = read_attributes(ATTR_FILE)
    time, voltage = read_waveform(WFM_FILE)
    plot_pulses(time, voltage, attrs)


