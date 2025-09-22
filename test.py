import numpy as np
from scipy.signal import find_peaks
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter

# 模拟一个含有多个峰的信号
x = np.linspace(0, 10, 500)
y = np.sin(x) ** 2 + np.random.normal(0, 0.05, len(x))  # 信号 + 噪声
y_smooth = savgol_filter(y, window_length=21, polyorder=3)

peaks, properties = find_peaks(y_smooth, height=0.2, distance=20)
peak_values = y[peaks]
print("峰的位置索引:", peaks)
print("峰的值:", peak_values)





plt.plot(x, y_smooth, label="Signal")
plt.plot(x[peaks], y_smooth[peaks], "rx", label="Peaks")  # 红叉表示峰
plt.legend()
plt.show()