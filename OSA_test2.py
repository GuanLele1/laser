import pyvisa
import numpy as np
from scipy.signal import find_peaks
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter
import serial
import time
import sys
import os



def format_results(y_dBm, x_nm, precision=2, save_file="osa_formatted_output.txt"):
    """
           将波长和功率数组拼成 ['1535.04 nm : -72.97 dBm', ...] 的形式
           并保存到文件
           参数:
               y_dBm: 功率数组
               x_nm: 波长数组
               precision: 小数点保留位数
               save_file: 保存文件名
           返回:
               格式化后的字符串列表
           """
    results = [
        f"{x:.{precision}f} nm : {y:.{precision}f} dBm"
        for x, y in zip(x_nm, y_dBm)
    ]

    # 保存到文件
    with open(save_file, "w", encoding="utf-8") as f:
        f.write("\n".join(results))

    return



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



        format_results(y_dBm, x_nm, precision=2, save_file="osa_formatted_output_meas.txt")

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


#数据分析
def Get_Peaks(y_dBm, x_nm):
    """
    从光谱图中分析出峰值
    参数:
        y_dBm：从光谱仪获取的强度数组
        x_nm：从光谱仪获取的位置数组
    """

    # ------------------------------
    # 强度限幅：小于 -65 的都改为 -65
    # ------------------------------
    y_dBm = [max(y, -65.0) for y in y_dBm]

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




class PCDM02DigitalController:
    """
    PCD-M02数字控制模式接口
    通过STM32发送数字控制信号
    """

    def __init__(self, port='COM7', baudrate=115200):
        self.ser = serial.Serial(port, baudrate, timeout=1)
        time.sleep(2)  # 等待STM32初始化

    def set_voltage(self, channel: int, voltage: float):
        """
        设置指定通道的输出电压
        :param channel: 通道号（1-4）
        :param voltage: 目标电压（0-140V）
        """
        if not 1 <= channel <= 4:
            raise ValueError("通道号必须为1-4")
        if voltage < 0 or voltage > 140:
            raise ValueError("电压超出范围（0-140V）")

        # 转换为12位数字值（0-4095）
        digital_value = int((voltage / 140.0) * 4095)
        cmd = f"CH{channel} {digital_value}\r\n"
        self.ser.write(cmd.encode())
        time.sleep(0.05)  # 确保命令发送完成

    def close(self):
        """关闭串口连接"""
        self.ser.close()


def fitness_symmetry(meas_peaks, target_count, w_pos=0.6, w_amp=0.4, huge=np.inf):
    """
    以“峰的数量 + 对称性（位置+强度）”为判据的适应度（越小越好）
    - meas_peaks: [(x, a)]，x=波长/频率位置，a=幅度（dBm 也可，内部会归一化）
    - target_count: 目标峰数（必须满足，否则直接给大惩罚）
    - w_pos / w_amp: 位置对称项与强度对称项的权重（和=1较好）
    - 返回: 浮点分数（越小越好）
    规则：
      1) 首先必须满足“峰的数量 = target_count”。若多/少，直接大惩罚。
      2) 若等于 target_count：
         - odd: 以“中间峰”为对称轴
         - even: 以“中间两峰的中点”为对称轴
         - 计算两侧配对的‘位置距离对称误差’与‘强度对称误差’，加权求和。
    """
    if target_count <= 0:
        return huge

    # 没有峰/目标不匹配 → 大惩罚
    if meas_peaks is None or len(meas_peaks) != target_count:
        return huge


    # 2) 对称性评估：先按 x 从小到大
    meas_peaks_sorted = sorted(meas_peaks, key=lambda t: t[0])
    xs = np.array([p[0] for p in meas_peaks_sorted], dtype=float)
    amps = np.array([p[1] for p in meas_peaks_sorted], dtype=float)

    # 幅度归一化（避免量纲、便于比较）
    # 注意 dBm 是对数；这里我们只做相对对称性，不做线性换算，保持简单一致性
    amps_n = amps / np.sum(amps)

    n = len(xs)
    # 计算对称轴
    if n % 2 == 1:
        # 奇数：以中间峰为对称轴
        mid = n // 2
        axis = xs[mid]
        # 两侧配对： (mid-1, mid+1), (mid-2, mid+2), ...
        pairs = [(mid - k, mid + k) for k in range(1, mid + 1)]
    else:
        # 偶数：以中间两峰的中点为轴
        mid_left = n // 2 - 1
        mid_right = n // 2
        axis = 0.5 * (xs[mid_left] + xs[mid_right])
        # 配对： (mid_left-0, mid_right+0), (mid_left-1, mid_right+1), ...
        pairs = [(mid_left - k, mid_right + k) for k in range(0, mid_left + 1)]

    # 3) 计算对称误差
    # 位置对称：理想情况是 xs[i] 与 xs[j] 关于 axis 等距 → |(xs[i]-axis) + (xs[j]-axis)| = 0
    # 强度对称：理想情况是 amps_n[i] == amps_n[j]
    pos_errs = []
    amp_errs = []
    for i, j in pairs:
        if i < 0 or j >= n:
            return huge  # 索引异常（理论不该发生）
        di = xs[i] - axis
        dj = xs[j] - axis
        pos_errs.append((di + dj)**2)                # 等距对称误差（平方）
        print(f"di={di}, dj={dj}, (di + dj)**2={(di + dj)**2}")
        amp_errs.append((amps_n[i] - amps_n[j])**2)  # 强度对称误差（平方）

    # 归一：避免不同数量配对下的偏置
    pos_err = float(np.mean(pos_errs)) if pos_errs else 0.0
    amp_err = float(np.mean(amp_errs)) if amp_errs else 0.0
    print(f"位置误差：{pos_err}，强度误差：{amp_err}")

    # 4) 汇总
    fitness = w_pos * pos_err + w_amp * amp_err
    return fitness


def voltage_pso_optimization(
        v_min: float = 0.0,
        v_max: float = 135.0,
        num_particles: int = 10,
        max_iterations: int = 100
):
    """
    用粒子群算法(PSO)自动优化输出电压，使目标频率标准差最小（四通道EPC优化）
    :param v_min: 起始电压 (单位：V)
    :param v_max: 终止电压 (单位：V)
    :param num_particles: 粒子数量
    :param max_iterations: 最大迭代次数
    """
    ctrl = PCDM02DigitalController(port='COM7')
    meas = OSA_MeasurementSystem()

    try:
        # 初始化
        # 现在粒子是一个4维数组，每个粒子对应四个通道的电压
        particles = np.random.uniform(v_min, v_max, (num_particles, 4))  # 粒子数量 x 4通道
        velocities = np.zeros((num_particles, 4))  # 对应四个通道的速度
        personal_best_positions = particles.copy()  # 个体最优位置（电压）
        personal_best_scores = np.full(num_particles, np.inf)  # 个体最优分数
        global_best_position = np.nan  # 全局最优位置
        global_best_score = np.inf  # 全局最优分数

        #获取标准谱
        x_nm_templ = []
        y_dBm_templ = []
        with open("osa_formatted_output.txt", "r") as f:    #打开标准谱文件
            for line in f:
                # 忽略空行
                if not line.strip():
                    continue
                # 拆分格式：1500.00 nm : -45.23 dBm
                parts = line.strip().split()
                try:
                    wavelength = float(parts[0])  # 1500.00
                    power = float(parts[3])  # -45.23

                    if power < -61:
                        power = -61

                    x_nm_templ.append(wavelength)
                    y_dBm_templ.append(power)
                except (ValueError, IndexError):
                    print("跳过无法解析的行:", line)

        y_dBm_templpeaks, x_nm_templpeaks = Get_Peaks(y_dBm_templ, x_nm_templ)
        templ_peaks  = list(zip(x_nm_templpeaks, y_dBm_templpeaks))


        # max_iterations 次的迭代循环
        for iteration in range(max_iterations):
            print(f"\n=== PSO迭代 {iteration + 1}/{max_iterations} ===")
            # num_particles 个粒子的操作
            for i in range(num_particles):
                v = particles[i]  # 当前粒子的电压（四个通道）
                # 为每个通道设置电压并等待稳定
                for channel in range(1, 5):  # 四个通道
                    ctrl.set_voltage(channel, v[channel - 1])
                time.sleep(0.8)  # 等待电压稳定


                y_dBm, x_nm = meas.read_OSA()
                y_dBm_peaks, x_nm_peaks = Get_Peaks(y_dBm, x_nm)
                meas_peaks  = list(zip(x_nm_peaks, y_dBm_peaks))



                fitness = fitness_symmetry(meas_peaks, 5)

                # 更新个体最优
                if fitness is not None and fitness < personal_best_scores[i]:
                    personal_best_scores[i] = fitness
                    personal_best_positions[i] = v

                # 更新全局最优
                if personal_best_scores[i] < global_best_score:
                    global_best_score = personal_best_scores[i]
                    global_best_position = personal_best_positions[i]

                print(f"粒子 {i+1} 电压 {v} -> 峰的个数：{len(y_dBm_peaks)} -> 适应度分数: {fitness if fitness is not None else 'NaN'} Hz")


                # ❗❗❗❗ 退出条件
                if fitness <= 25:
                    return


            # 粒子群速度与位置更新
            # w * velocities[i] 是惯性项，延续上一步的速度，w越大表示探索性越强，越小表示探索越保守
            # 个体认知项 c1 * r1 * (pbest - x)，c1 是力度系数，r1 是随机数，增加随机性、避免整齐振荡。
            # 群体社会项 c2 * r2 * (gbest - x)，c2 是力度系数，r2 同样是随机数。
            # r的作用是给“拉力”加随机性，避免所有粒子动作完全一致，保持群体的多样性。
            for i in range(num_particles):
                if np.isinf(personal_best_scores[i]):
                    print(f"[重置] 第 {i} 个粒子有个体最佳为 inf，对其重置。")
                    particles[i] = np.random.uniform(v_min, v_max, 4)
                    personal_best_positions[i] = particles[i]
                    continue
                w = 0.5
                c1 = 1.5
                c2 = 1.5
                r1 = np.random.rand(4)
                r2 = np.random.rand(4)
                # 更新速度公式，适用于四个通道的电压和速度
                velocities[i] = (w * velocities[i]
                                 + c1 * r1 * (personal_best_positions[i] - particles[i])
                                 + c2 * r2 * (global_best_position - particles[i]))
                # 更新粒子位置
                particles[i] += velocities[i]
                particles[i] = np.clip(particles[i], v_min, v_max)  # 限定电压范围

            print(f"当前最优电压: {global_best_position} V  最小分数: {global_best_score:.2f} Hz")

        # 输出最终最优解
        print("\n===== 粒子群优化结果 =====")
        print(f"最优电压: {global_best_position} V")
        print(f"最小分数: {global_best_score:.2f} Hz")

        # 为每个通道设置全局最优电压
        for channel in range(1, 5):  # 四个通道
            ctrl.set_voltage(channel, global_best_position[channel - 1])

    finally:
        ctrl.close()
        meas.close()



if __name__ == "__main__":
    # osa = OSA_MeasurementSystem(ip="192.168.1.3")
    # y_dBm, x_nm = osa.read_OSA()
    # y_dBm_peaks, x_nm_peaks = Get_Peaks(y_dBm, x_nm)
    # meas_peaks = list(zip(x_nm_peaks, y_dBm_peaks))
    #
    # fitness = fitness_symmetry(meas_peaks, 5)
    # print(fitness)
    # format_results(y_dBm, x_nm, precision=2, save_file="osa_formatted_output_meas.txt")
    voltage_pso_optimization()

# # 打印部分数据
# #print(f"共 {npts} 点")
# for i in range(2000):  # 前10个点
#     print(f"{x_nm[i]:.2f} nm : {y_dBm[i]:.2f} dBm")
#
# with open("power_values.txt", "w") as f:
#     for y in y_dBm:
#         f.write(f"{y:.2f}\n")
#
# print("已保存到 power_values.txt")
#
#
# filename = "osa_formatted_output.txt"
#
# with open(filename, "w") as f:
#     for x, y in zip(x_nm, y_dBm):
#         f.write(f"{x:.2f} nm : {y:.2f} dBm\n")
#
# print(f"格式化数据已保存到 {filename}")

