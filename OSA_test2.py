import pyvisa
import numpy as np
from scipy.signal import find_peaks
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter
import serial
import time
import sys
import os
from matplotlib.animation import FuncAnimation, PillowWriter


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
        osa.write(":SENSE:WAVELENGTH:START 1516NM")       # 起始波长
        osa.write(":SENSE:WAVELENGTH:STOP 1636NM")        # 结束波长
        osa.write(":SENSE:BANDWIDTH:RESOLUTION 0.2NM")   # 分辨率
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
        # >>> 功率裁剪，小于 -55 dBm 的全部固定为 -55 <<<
        y_dBm = [max(y, -55) for y in y_dBm]
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



#单片机操作类
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


#动图制作
def make_osa_animation(all_spectra, filename="osa_pso.gif", fps=2):
    """
    all_spectra: [(x_nm_array, y_dBm_array), ...]
    """
    if not all_spectra:
        print("没有记录到任何光谱，无法生成动画。")
        return

    # 先确定全局的 x、y 范围，避免每帧缩放乱跳
    all_x = np.concatenate([spec[0] for spec in all_spectra])
    all_y = np.concatenate([spec[1] for spec in all_spectra])

    x_min, x_max = np.min(all_x), np.max(all_x)
    y_min, y_max = np.min(all_y), np.max(all_y)

    fig, ax = plt.subplots()
    line, = ax.plot([], [], lw=1)

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min - 2, y_max + 2)
    ax.set_xlabel("Wavelength (nm)")
    ax.set_ylabel("Power (dBm)")
    ax.set_title("OSA Spectrum Evolution (PSO Iterations)")
    ax.grid(True)

    def init():
        line.set_data([], [])
        return line,

    def update(frame):
        x, y = all_spectra[frame]
        line.set_data(x, y)
        ax.set_title(f"OSA Spectrum - Frame {frame+1}/{len(all_spectra)}")
        return line,

    ani = FuncAnimation(
        fig,
        update,
        frames=len(all_spectra),
        init_func=init,
        blit=True
    )

    # 使用 Pillow 保存为 GIF（需要安装 pillow: pip install pillow）
    ani.save(filename, writer=PillowWriter(fps=fps))
    plt.close(fig)
    print(f"动画已保存为 {filename}")



#取峰及其属性
def Get_Peaks(y_dBm, x_nm):

    y_dBm = savgol_filter(y_dBm, window_length=31, polyorder=3)

    peaks, properties = find_peaks(
        y_dBm, height=-65, prominence=0.2, width=10
    )

    if len(peaks) == 0:
        return y_dBm[peaks], np.array(x_nm)[peaks], peaks, properties, y_dBm

    x_nm = np.asarray(x_nm)
    y_dBm = np.asarray(y_dBm)
    peaks = np.asarray(peaks, dtype=int)

    # --- 先记录 SciPy 原始的 left/right bases 和宽度 ---
    orig_left  = properties["left_bases"].copy()
    orig_right = properties["right_bases"].copy()
    orig_width_pts = properties["widths"].copy()
    orig_width_nm  = x_nm[orig_right] - x_nm[orig_left]

    # --- 先找所有“局部谷底” ---
    valleys, _ = find_peaks(-y_dBm)

    # 新的左右谷底（默认先用原始的）
    left_bases  = orig_left.copy()
    right_bases = orig_right.copy()

    for i, p in enumerate(peaks):

        # ===== 中间峰（非首非尾） → 使用最近谷底 =====
        if 0 < i < len(peaks) - 1:

            # 最近左谷
            v_left = valleys[valleys < p]
            if v_left.size > 0:
                left_bases[i] = v_left[-1]

            # 最近右谷
            v_right = valleys[valleys > p]
            if v_right.size > 0:
                right_bases[i] = v_right[0]

        # ===== 最左峰（i == 0） → 完全保持 SciPy 原始 =====
        elif i == 0:
            left_bases[i]  = orig_left[i]
            right_bases[i] = orig_right[i]

        # ===== 最右峰（i == 最后） → 完全保持 SciPy 原始 =====
        elif i == len(peaks) - 1:
            left_bases[i]  = orig_left[i]
            right_bases[i] = orig_right[i]

    # ---- 基于新的左右谷底更新宽度（仅中间峰） ----
    new_width_pts = right_bases - left_bases
    new_width_nm  = x_nm[right_bases] - x_nm[left_bases]

    # 但最左峰、最右峰的宽度改回“原始 SciPy”
    new_width_pts[0]  = orig_width_pts[0] * 2.5
    new_width_nm[0]   = new_width_pts[0] * 0.04

    new_width_pts[-1] = orig_width_pts[-1] * 2.5
    new_width_nm[-1]  = orig_width_nm[-1] * 0.04

    # 写回 properties
    properties["left_bases"]  = left_bases
    properties["right_bases"] = right_bases
    properties["widths"]      = new_width_pts
    properties["widths_nm"]   = new_width_nm

    return y_dBm[peaks], x_nm[peaks], peaks, properties, y_dBm



def fitness_symmetry(meas_peaks, target_count, w_pos=100, w_amp=100, huge=np.inf, widths=None):
    """
    以“峰的数量 + 对称性（位置+强度）”为判据的适应度（越小越好）
    - meas_peaks: [(x, a)]，x=波长/频率位置，a=幅度（dBm 也可，内部会归一化）
    - target_count: 目标峰数（主峰 + 对称 Kelly），比如 5 = 主峰 + 左右各 2 个
    - w_pos / w_amp: 位置对称项与强度对称项的权重
    - widths: 与 meas_peaks 一一对应的峰宽数组，用来确定主峰（宽度最大）
    - 返回: 浮点分数（越小越好）
    """
    if target_count <= 0:
        return huge

    # 注意这里改成 "< target_count"：峰数量不够才罚，大于 target_count 也可以，从中挑
    if meas_peaks is None or len(meas_peaks) < target_count:
        return huge

    # 2) 对称性评估：先按 x 从小到大
    meas_peaks_sorted = sorted(meas_peaks, key=lambda t: t[0])
    xs = np.array([p[0] for p in meas_peaks_sorted], dtype=float)
    amps = np.array([p[1] for p in meas_peaks_sorted], dtype=float)

    # 幅度归一化（避免量纲、便于比较）
    amps_n = amps / np.sum(amps)

    n = len(xs)

    # ---- 2.1 处理 widths：重排到与 xs 一致的顺序 ----
    widths_sorted = None
    if widths is not None:
        widths = np.asarray(widths)
        if len(widths) == len(meas_peaks):
            # 原始 meas_peaks 中的 x 顺序
            xs_raw = np.array([p[0] for p in meas_peaks], dtype=float)
            order = np.argsort(xs_raw)
            widths_sorted = widths[order]

    # ---- 2.2 计算对称轴 & 根据 target_count 选取主峰 + 对称 Kelly ----
    if widths_sorted is not None:
        # >>> 最大宽度门槛 <<<
        if np.max(widths_sorted) < 250:
            return huge
        # 用峰宽最大的作为主峰
        main_idx = int(np.argmax(widths_sorted))
        axis = xs[main_idx]
        print(1)
        # 从主峰开始，向两边取对称的 Kelly 边带，直到总数达到 target_count
        pairs = []
        current_count = 1           # 当前总峰数（已含主峰）

        k = 1
        while current_count < target_count:
            i = main_idx - k
            j = main_idx + k

            # 一侧越界、另一侧还在 → 直接返回 huge（你说的逻辑）
            if i < 0 or j >= n:
                return huge

            pairs.append((i, j))
            current_count += 2
            k += 1

        # 3) 计算对称误差
        # 位置对称：理想情况是 xs[i] 与 xs[j] 关于 axis 等距 → |(xs[i]-axis) + (xs[j]-axis)| = 0
        # 强度对称：理想情况是 amps_n[i] == amps_n[j]

        # 计算尺度 L（取半跨度）
        L = np.max(np.abs(xs - axis))
        if L == 0:
            return huge

        pos_errs = []
        amp_errs = []
        for i, j in pairs:
            if i < 0 or j >= n:
                return huge  # 理论上不该发生
            di = xs[i] - axis
            dj = xs[j] - axis

            pos_errs.append(((di + dj) / L)**2)                # 等距对称误差（平方）
            print(f"di={di}, dj={dj}, (di + dj)**2={(di + dj)**2}")
            amp_errs.append((amps_n[i] - amps_n[j])**2)        # 强度对称误差（平方）

        # 归一：避免不同数量配对下的偏置
        pos_err = float(np.mean(pos_errs)) / 4 if pos_errs else 0.0
        amp_err = float(np.mean(amp_errs)) if amp_errs else 0.0
        print(f"位置误差：{pos_err}，强度误差：{amp_err}")

        # 4) 汇总
        fitness = w_pos * pos_err + w_amp * amp_err
        return fitness

    else:
        return huge



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
        k = 0   #优秀个体计数
        all_spectra = []  # 用来记录每次迭代的光谱 (x_nm, y_dBm) 做动图用

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
                y_dBm_peaks, x_nm_peaks, peaks, properties, y_lvbo = Get_Peaks(y_dBm, x_nm)
                meas_peaks  = list(zip(x_nm_peaks, y_dBm_peaks))

                all_spectra.append((np.array(x_nm), np.array(y_lvbo))) #把光谱加进动图素材

                widths = properties["widths"]  # find_peaks 给出的每个峰的宽度

                fitness = fitness_symmetry(meas_peaks, 5, widths=widths)
                print(fitness)
                # 更新个体最优
                if fitness is not None and fitness < personal_best_scores[i]:
                    personal_best_scores[i] = fitness
                    personal_best_positions[i] = v

                # 更新全局最优
                if personal_best_scores[i] < global_best_score:
                    global_best_score = personal_best_scores[i]
                    global_best_position = personal_best_positions[i]

                    # ★★★ 新增：每当找到更小的全局适应度时，保存当前光谱数据到新文件
                    k = k+1
                    filename = f"osa_best_iter{iteration + 1}_particle{i + 1}_best{k}.txt"
                    format_results(y_dBm, x_nm, precision=2, save_file=filename)

                print(f"粒子 {i+1} 电压 {v} -> 峰的个数：{len(y_dBm_peaks)} -> 适应度分数: {fitness if fitness is not None else 'NaN'} Hz")


                # ❗❗❗❗ 退出条件
                if fitness <= 0.001:
                    make_osa_animation(all_spectra, filename="osa_pso.gif", fps=2)  #动图制作
                    return


            # 粒子群速度与位置更新
            # w * velocities[i] 是惯性项，延续上一步的速度，w越大表示探索性越强，越小表示探索越保守
            # 个体认知项 c1 * r1 * (pbest - x)，c1 是力度系数，r1 是随机数，增加随机性、避免整齐振荡。
            # 群体社会项 c2 * r2 * (gbest - x)，c2 是力度系数，r2 同样是随机数。
            # r的作用是给“拉力”加随机性，避免所有粒子动作完全一致，保持群体的多样性。
            for i in range(num_particles):
                if np.isinf(personal_best_scores[i]):
                    if np.any(np.isnan(global_best_position)):
                        # 一开始还没全局最优，用全局随机
                        particles[i] = np.random.uniform(v_min, v_max, 4)
                    else:
                        # 已经有不错的解了：在全局最优附近随机微调
                        local_span = 10  # 比如 ±10V 的小立方体
                        particles[i] = global_best_position + np.random.uniform(-local_span, local_span, 4)
                        particles[i] = np.clip(particles[i], v_min, v_max)

                personal_best_positions[i] = particles[i]
                continue

                # ===== 根据适应度调节最大步长：适应度越小，步长越小 =====
                score = personal_best_scores[i]

                # 设定一个“好到什么程度”的参考尺度，比如 0.05
                # 小于它就认为已经很不错了，进入很小步长微调区间
                score_ref = 0.1

                # 把 score 截断到 [0, score_ref]
                score_clipped = min(max(score, 0.0), score_ref)

                # 映射到一个 [step_min_factor, 1] 的因子：
                #   score_clipped = score_ref 时 → factor = 1 （很差，步长最大）
                #   score_clipped → 0 时         → factor → step_min_factor（很好，步长最小）
                step_min_factor = 0.1  # 最小步长比例（防止完全不动）
                factor = step_min_factor + (1.0 - step_min_factor) * (score_clipped / score_ref)

                # 电压每次的最大步长基准，比如 4 V（你可以自己调 1~5 V 看效果）
                v_step_max_base = 4.0
                v_step_max = v_step_max_base * factor
                # ===================================================

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
    # meas = OSA_MeasurementSystem()
    # y_dBm, x_nm = meas.read_OSA()
    # meas.close()
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

