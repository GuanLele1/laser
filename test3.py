import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import find_peaks

# 模拟一个波形数据（包含多个峰）
y_dBm = np.array([0, 1, 3, 1, 0, 2, 5, 3, 1, 0, 1, 0, 4, 6, 3, 0])

# 使用 find_peaks 寻找峰
peaks, properties = find_peaks(y_dBm, prominence=2)

# 打印峰的索引和属性
print("Detected peaks at indices:", peaks)
print("Peak properties:", properties)

# 绘制结果
plt.plot(y_dBm, label="Signal")
plt.plot(peaks, y_dBm[peaks], "rx", label="Peaks")
plt.legend()
plt.show()