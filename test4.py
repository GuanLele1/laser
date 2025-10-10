import numpy as np
from fontTools.unicodedata import block
from scipy.signal import find_peaks
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter

x_nm = []
y_dBm = []

with open("osa_formatted_output_meas.txt", "r") as f:
    for line in f:
        # 忽略空行
        if not line.strip():
            continue
        # 拆分格式：1500.00 nm : -45.23 dBm
        parts = line.strip().split()
        try:
            wavelength = float(parts[0])     # 1500.00
            power     = float(parts[3])     # -45.23

            # if power < -61:
            #     power = -61

            x_nm.append(wavelength)
            y_dBm.append(power)
        except (ValueError, IndexError):
            print("跳过无法解析的行:", line)

# 转换为 NumPy 数组
#y_dBm = np.array(y_dBm)

# 对功率数据应用 Savitzky-Golay 滤波器
y_dBm = savgol_filter(y_dBm, window_length=31, polyorder=3)

# 查找峰值
peaks, properties = find_peaks(y_dBm, height=-70, distance=50, prominence=0.2, width=20)

# 确保 peaks 是整数类型
#peaks = np.array(peaks, dtype=int)

for i, peak in enumerate(peaks):
    peak_x = x_nm[peak]
    peak_y = y_dBm[peak]

    left_base_idx = int(properties["left_bases"][i])
    right_base_idx = int(properties["right_bases"][i])

    left_x = x_nm[left_base_idx]
    right_x = x_nm[right_base_idx]

    width_pts = properties["widths"][i]
    width_nm = x_nm[int(properties["right_ips"][i])] - x_nm[int(properties["left_ips"][i])]

    print(f"峰 {i+1}:")
    print(f"  峰位置: {peak_x:.2f} nm, 强度: {peak_y:.2f} dBm")
    print(f"  左谷: {left_x:.2f} nm, 右谷: {right_x:.2f} nm")
    print(f"  宽度: {width_pts:.1f} 点, 约 {width_nm:.2f} nm")
    print("-" * 40)

# 绘图
plt.plot(x_nm, y_dBm, label="Smoothed Signal")
plt.plot(np.array(x_nm)[peaks], y_dBm[peaks], "rx", label="Peaks")  # 红叉表示峰
plt.xlabel("Wavelength (nm)")
plt.ylabel("Power (dBm)")
plt.title("OSA Trace")
plt.grid(True)
plt.legend()
plt.savefig("figure.png", dpi=300)
plt.show()