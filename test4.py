import numpy as np
import  OSA_test3
from fontTools.unicodedata import block
from scipy.signal import find_peaks
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter




x_nm = []
y_dBm = []

with open("osa_best_iter23_particle1_best6.txt", "r") as f:
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



# ========= 新增：将小于 -150 dBm 的点替换为其相邻上一个值 =========
if y_dBm:
    # 从第二个点开始，遇到小于 -150 的就用上一个值替换
    for i in range(1, len(y_dBm)):
        if y_dBm[i] < -150:
            y_dBm[i] = y_dBm[i - 1]

    # 若第一个点小于 -150，则用后面第一个非异常值替代（若存在）
    if y_dBm[0] < -150:
        for j in range(1, len(y_dBm)):
            if y_dBm[j] >= -150:
                y_dBm[0] = y_dBm[j]
                break

# # 转换为 NumPy 数组
# y_dBm = np.array(y_dBm)


y_dBm_peak, x_nm_peak, peaks,  properties, y_dBm= OSA_test3.Get_Peaks(y_dBm, x_nm)
meas_peaks  = list(zip(x_nm_peak, y_dBm_peak))

fitness = OSA_test3.fitness_symmetry(meas_peaks)

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
    width_nm = properties["widths_nm"][i]

    print(f"峰 {i+1}:")
    print(f"  峰位置: {peak_x:.2f} nm, 强度: {peak_y:.2f} dBm")
    print(f"  左谷: {left_x:.2f} nm, 右谷: {right_x:.2f} nm")
    print(f"  宽度: {width_pts:.1f} 点, 约 {width_nm:.2f} nm")
    print("-" * 40)


print(f"该光谱的适应度值为{fitness}")

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