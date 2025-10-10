import numpy as np
from scipy.signal import find_peaks, savgol_filter
import matplotlib.pyplot as plt

# ------------------------------
# 打开第一个文件 osa_formatted_output.txt
# ------------------------------
x1, y1 = [], []
with open("osa_formatted_output.txt", "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        parts = line.strip().split()
        try:
            wavelength = float(parts[0])   # e.g. 1500.00
            power     = float(parts[3])   # e.g. -45.23
            if power < -61:
                power = -61
            x1.append(wavelength)
            y1.append(power)
        except (ValueError, IndexError):
            print("跳过无法解析的行:", line)

y1 = savgol_filter(y1, window_length=31, polyorder=3)
peaks1, _ = find_peaks(y1, height=-70, distance=60, prominence=0.5, width=35)

# ------------------------------
# 打开第二个文件 osa_formatted_output_meas.txt
# ------------------------------
x2, y2 = [], []
with open("osa_formatted_output_meas.txt", "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        parts = line.strip().split()
        try:
            wavelength = float(parts[0])   # e.g. 1500.00
            power     = float(parts[3])   # e.g. -45.23
            if power < -61:
                power = -61
            x2.append(wavelength)
            y2.append(power)
        except (ValueError, IndexError):
            print("跳过无法解析的行:", line)

y2 = savgol_filter(y2, window_length=31, polyorder=3)
peaks2, _ = find_peaks(y2, height=-70, distance=60, prominence=0.5,width = 30)

# ------------------------------
# 画图：一个画框里放两幅图（上下排列）
# ------------------------------
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=False)

# 图1
ax1.plot(x1, y1, label="templ")
ax1.plot(np.array(x1)[peaks1], y1[peaks1], "rx", label="Peaks")
ax1.set_title("OSA Trace - osa_formatted_output.txt")
ax1.set_xlabel("Wavelength (nm)")
ax1.set_ylabel("Power (dBm)")
ax1.grid(True)
ax1.legend()

# 图2
ax2.plot(x2, y2, label="meas")
ax2.plot(np.array(x2)[peaks2], y2[peaks2], "rx", label="Peaks")
ax2.set_title("OSA Trace - osa_formatted_output_meas.txt")
ax2.set_xlabel("Wavelength (nm)")
ax2.set_ylabel("Power (dBm)")
ax2.grid(True)
ax2.legend()

plt.tight_layout()
plt.show()
