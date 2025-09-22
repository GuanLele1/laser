import numpy as np
from scipy.signal import find_peaks
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter

x_nm = []
y_dBm = []


# 转换为 NumPy 数组
#y_dBm = np.array(y_dBm)

# 对功率数据应用 Savitzky-Golay 滤波器
y_dBm = savgol_filter(y_dBm, window_length=21, polyorder=3)

# 查找峰值
peaks, properties = find_peaks(y_dBm, height=-70, distance=20, prominence=1)

# 确保 peaks 是整数类型
peaks = np.array(peaks, dtype=int)

# 绘图
plt.plot(x_nm, y_dBm, label="Smoothed Signal")
plt.plot(np.array(x_nm)[peaks], y_dBm[peaks], "rx", label="Peaks")  # 红叉表示峰
plt.xlabel("Wavelength (nm)")
plt.ylabel("Power (dBm)")
plt.title("OSA Trace")
plt.grid(True)
plt.legend()
plt.show()