import numpy as np
from fontTools.unicodedata import block
from scipy.signal import find_peaks
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter
import pyvisa
import numpy as np
from scipy.signal import find_peaks
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter
import serial
import time


class OSA_MeasurementSystem:

    """
    光谱仪（OSA）操作类
    - 初始化时建立连接
    - read_OSA() 用于一次扫描并读取数据
    - close() 用于关闭连接
    """

    def __init__(self, ip: str = "192.168.1.3"):
        """
        初始化并连接到 OSA 仪器
        参数:
            ip: 仪器 IP 地址
        """
        self.ip = ip
        self.rm = pyvisa.ResourceManager()
        self.osa = self.rm.open_resource(f"TCPIP0::{ip}::inst0::INSTR")  # VXI-11 接口
        self.osa.timeout = 30000  # ms，扫描时间可能较长

    def read_OSA(self):
        """
        执行一次扫描并读取数据
        返回:
            y_dBm (list[float]), x_nm (list[float])
        """
        osa = self.osa

        # ------------------------------
        # 设置波长区间和参数
        # ------------------------------
        osa.write(":SENSE:WAVELENGTH:START 1535NM")       # 起始波长
        osa.write(":SENSE:WAVELENGTH:STOP 1585NM")        # 结束波长
        osa.write(":SENSE:BANDWIDTH:RESOLUTION 0.05NM")   # 分辨率
        osa.write(":SENSE:SENSITIVITY HIGH1")             # 灵敏度

        # ------------------------------
        # 扫描一次
        # ------------------------------
        osa.write(":INIT:CONT OFF")   # 单次扫描模式
        osa.write(":INIT")            # 发起扫描
        osa.query("*OPC?")            # 等待扫描完成

        # ------------------------------
        # 读取数据
        # ------------------------------
        xdata = osa.query(":TRACe:DATA:X? TRA")           # 波长数组（单位：米）
        ydata = osa.query(":TRACe:DATA:Y? TRA")           # 功率数组（单位：dBm）

        # 转换为 float 数组
        x_nm = [float(x) * 1e9 for x in xdata.strip().split(",")]  # m → nm
        y_dBm = [float(y) for y in ydata.strip().split(",")]

        # ------------------------------
        # 强度限幅：小于 -65 的都改为 -65
        # ------------------------------
        y_dBm = [max(y, -65.0) for y in y_dBm]

        # format_results(y_dBm, x_nm, precision=2, save_file="osa_formatted_output_meas.txt")

        return y_dBm, x_nm

    def read_OSA_exist(self):
        """
        读取 OSA 最近一次扫描的数据（不重新触发扫描）
        返回:
            y_dBm (list[float]), x_nm (list[float])
        """
        osa = self.osa

        # ------------------------------
        # 直接读取数据
        # ------------------------------
        xdata = osa.query(":TRACe:DATA:X? TRA")  # 波长数组（单位：米）
        ydata = osa.query(":TRACe:DATA:Y? TRA")  # 功率数组（单位：dBm）

        # 转换为 float 数组
        x_nm = [float(x) * 1e9 for x in xdata.strip().split(",")]  # m → nm
        y_dBm = [float(y) for y in ydata.strip().split(",")]

        # ------------------------------
        # 强度限幅：小于 -65 的都改为 -65
        # ------------------------------
        y_dBm = [max(y, -65.0) for y in y_dBm]

        return y_dBm, x_nm

    def close(self):
        """关闭 OSA 连接"""
        if self.osa is not None:
            self.osa.close()
        if self.rm is not None:
            self.rm.close()

def Get_Peaks(y_dBm, x_nm):
    """
    从光谱图中分析出峰值
    参数:
        y_dBm：从光谱仪获取的强度数组
        x_nm：从光谱仪获取的位置数组
    """

    # 对功率数据应用 Savitzky-Golay 滤波器
    y_dBm = savgol_filter(y_dBm, window_length=31, polyorder=3)

    # 查找峰值
    peaks, properties = find_peaks(y_dBm, height=-70, distance=200, prominence=0.8, width=30)

    # #画图
    # plt.clf()
    # plt.plot(x_nm, y_dBm, label="Signal")
    # plt.plot(np.array(x_nm)[peaks], y_dBm[peaks], "rx", label="Peaks")  # 红叉表示峰
    # plt.xlabel("Wavelength (nm)")
    # plt.ylabel("Power (dBm)")
    # plt.title("OSA Trace")
    # plt.grid(True)
    # plt.legend()
    # plt.savefig("figure.png", dpi=300)
    # plt.show(block=False)
    # time.sleep(0.2)

    return y_dBm[peaks], np.array(x_nm)[peaks]

x_nm = []
y_dBm = []

osa = OSA_MeasurementSystem(ip="192.168.1.3")
y_dBm, x_nm = osa.read_OSA()
y_dBm_peaks, x_nm_peaks = Get_Peaks(y_dBm, x_nm)
meas_peaks = list(zip(x_nm_peaks, y_dBm_peaks))
osa.close()



# 转换为 NumPy 数组
#y_dBm = np.array(y_dBm)

# 对功率数据应用 Savitzky-Golay 滤波器
y_dBm = savgol_filter(y_dBm, window_length=31, polyorder=3)

# 查找峰值
peaks, properties = find_peaks(y_dBm, height=-70, distance=60, prominence=0.5, width=30)

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