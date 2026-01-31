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
import pickle



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




#示波器操作
class RTP_Oscilloscope:
    def __init__(self):
        """
        初始化示波器连接
        :param resource_string: 完整的VISA资源字符串
                                例如: 'TCPIP::192.168.1.1::hislip0::INSTR'
                                或 'USB0::0x0AAD::0x0197::123456::INSTR'
        """
        self.rm = pyvisa.ResourceManager()
        try:
            # 直接使用传入的资源字符串打开连接
            self.instr = self.rm.open_resource('USB0::0x0AAD::0x0197::1320.5007k04-103067::INSTR')

            # 设置超时 (USB通常很快，但截图传输需要较长时间)
            self.instr.timeout = 10000

            # 设置读写结束符 (这对 USB 通信也很重要)
            self.instr.read_termination = '\n'
            self.instr.write_termination = '\n'

            # 查询仪器ID以确认连接成功
            idn = self.instr.query("*IDN?")
            print(f"成功连接到: {idn.strip()}")

            # 清除状态寄存器
            self.instr.write("*CLS")

        except Exception as e:
            print(f"连接失败: {e}")
            raise

    # ... measure_channel1_frequency 和 take_screenshot 函数保持完全不变 ...
    # ... 因为 SCPI 命令内容与物理接口无关 ...

    def measure_channel1_frequency(self):
        """
                功能1: 测量通道1的频率
                参考手册章节: 26.3.2.1 Performing amplitude/time measurements
                """
        try:
            # 1. 确保通道1已打开 (Section 26.3.1)
            self.instr.write("CHANnel1:STATe ON")

            # 2. 启用测量组1 (MEASurement1)
            self.instr.write("MEASurement1:ENABle ON")

            # 3. 设置测量源为通道1波形1 (C1W1) (Section 26.4.2 Waveform parameter)
            self.instr.write("MEASurement1:SOURce C1W1")

            # 4. 设置测量类型为频率 (FREQ) (Section 26.3.2.1)
            self.instr.write("MEASurement1:MAIN FREQuency")

            # 5. 等待操作完成 (*OPC?) 确保设置已应用
            self.instr.query("*OPC?")

            # 6. 获取当前测量结果 (Section 26.3.2.1)
            # MEASurement<m>:RESult:ACTual? 返回当前统计周期的测量值
            result_str = self.instr.query("MEASurement1:RESult:ACTual?")

            freq_value = float(result_str)
            print(f"通道1 频率测量结果: {freq_value / 1e6:.4f} MHz")
            return freq_value

        except Exception as e:
            print(f"测量频率失败: {e}")
            return None


    def take_screenshot(self, local_filepath="screenshot2.png"):
        """
        功能2: 截图并保存到本地电脑
        参考手册章节: 26.3.5.1 Saving a screenshot to file
        过程: 先在示波器内部保存，读取二进制数据，再保存到本地，最后删除示波器内部文件。
        """
        # 示波器内部的临时路径 (Windows系统路径)
        scope_temp_path = r"C:\Temp\remote_screen.png"

        try:
            print("正在执行截图...")

            # 1. 确保显示更新已打开，否则截图可能为黑屏 (Section 26.7.2.5)
            # 手册提示: To get a correct screenshot, turn on the display first.
            self.instr.write("SYSTem:DISPlay:UPDate ON")

            # 2. 设置截图格式为 PNG (Section 26.16.8)
            self.instr.write("HCOPy:DEVice:LANGuage PNG")

            # 3. 设置截图目标为大容量存储 (Mass Memory) (Section 26.3.5.1)
            self.instr.write("HCOPy:DESTination 'MMEM'")

            # 4. 设置示波器内部保存的文件名 (Section 26.3.5.1)
            self.instr.write(f"MMEMory:NAME '{scope_temp_path}'")

            # 5. 执行截图 (HCOPy:IMMediate)
            self.instr.write("HCOPy:IMMediate")

            # 等待截图完成
            self.instr.query("*OPC?")

            # 6. 将文件从示波器传输到本地电脑
            # 使用 MMEMory:DATA? 命令读取文件数据 (Section 26.16.2 / 26.3.5.2)
            print(f"正在将截图从示波器传输到本地: {local_filepath}")
            self.instr.write(f"MMEMory:DATA? '{scope_temp_path}'")

            # 读取二进制块数据
            image_data = self.instr.read_raw()

            # 解析 SCPI 二进制块头 (例如 #41234...) 并去除
            # 注意：read_raw读取的数据通常包含头部信息，需要手动处理或使用pyvisa的工具
            # 这里使用更稳健的 pyvisa query_binary_values 方法重新获取
            image_data = self.instr.query_binary_values(
                f"MMEMory:DATA? '{scope_temp_path}'",
                datatype='B',
                header_fmt='ieee',
                container=bytearray
            )

            # 7. 保存到本地文件
            with open(local_filepath, 'wb') as f:
                f.write(image_data)

            print("截图保存成功。")

            # 8. 清理示波器内部的临时文件 (Section 26.3.5.2)
            self.instr.write(f"MMEMory:DELete '{scope_temp_path}'")

        except Exception as e:
            print(f"截图失败: {e}")


    def set_timebase_scale(self, scale_per_div):
        """
        功能: 设置示波器的水平时基刻度 (Time/Div)
        参考手册: 26.8.2 Time base
        :param scale_per_div: 每格的时间，单位为秒 (float)。例如 1ms = 1e-3
        """
        if self.instr is None: return

        try:
            # 命令: TIMebase:SCALe <Value>
            cmd = f"TIMebase:SCALe {scale_per_div}"
            self.instr.write(cmd)

            # 发送 *OPC? 确保硬件设置完成，防止后续命令冲突
            self.instr.query("*OPC?")
            print(f"时基已设置为: {scale_per_div} s/div")

        except Exception as e:
            print(f"设置时基失败: {e}")


    def stop_acquisition(self):
        """
        功能: 按下示波器的 STOP 键 (停止采集)
        参考手册: 26.8.1 Starting and stopping acquisition
        及示例 26.3.5.2 Exporting waveform data to file
        """
        if self.instr is None: return

        try:
            # 命令: STOP
            # 这是一个事件命令，不需要参数
            self.instr.write("STOP")

            # 关键：发送 *OPC? 等待示波器完全停止。
            # 如果不等待，立即读取数据可能会读到不完整的数据或导致超时。
            self.instr.query("*OPC?")
            print("采集已停止 (STOP)。")

        except Exception as e:
            print(f"停止采集失败: {e}")


    def close(self):
        if hasattr(self, 'instr'):
            self.instr.close()
        if hasattr(self, 'rm'):
            self.rm.close()



#光谱仪操作
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
        # print("VISA backend:", self.rm.visalib)
        # print("VISA resources:", self.rm.list_resources())
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
        osa.write(":SENSE:WAVELENGTH:START 1512.75NM")       # 起始波长
        osa.write(":SENSE:WAVELENGTH:STOP 1548.25NM")        # 结束波长
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
        # y_dBm = [max(y, -65.0) for y in y_dBm]
        format_results(y_dBm, x_nm, precision=2, save_file="osa_formatted_output.txt")
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

    y_dBm = savgol_filter(y_dBm, window_length=11, polyorder=3)

    peaks, properties = find_peaks(
        y_dBm, height=-58, prominence=0.2, width=8
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

        # ===== 中间峰（非首非尾） → 用「相邻两峰之间最深的谷」 =====
        if 0 < i < len(peaks) - 1:
            p_left = peaks[i - 1]
            p_right = peaks[i + 1]

            # 左侧谷：在 (p_left, p) 之间找谷，然后选 y 最小的那个
            mask_left = (valleys > p_left) & (valleys < p)
            v_left = valleys[mask_left]
            if v_left.size > 0:
                left_bases[i] = v_left[np.argmin(y_dBm[v_left])]
            # 如果这一段没有谷，就保持原始 orig_left[i]（不动）

            # 右侧谷：在 (p, p_right) 之间找谷，然后选 y 最小的那个
            mask_right = (valleys > p) & (valleys < p_right)
            v_right = valleys[mask_right]
            if v_right.size > 0:
                right_bases[i] = v_right[np.argmin(y_dBm[v_right])]
            # 同样，如果没有谷就保持 orig_right[i]

        # ===== 最左峰（i == 0） → 完全保持 SciPy 原始 =====
        elif i == 0:
            left_bases[i]  = orig_left[i]
            right_bases[i] = orig_right[i]

        # ===== 最右峰（i == 最后） → 完全保持 SciPy 原始 =====
        elif i == len(peaks) - 1:
            left_bases[i]  = orig_left[i]
            right_bases[i] = orig_right[i]

    # ============ 修改：只在“最强峰”离左右谷底过近时才删除，并更新邻峰谷底 ============
    min_peak_valley_nm = 0.9

    while True:
        if len(peaks) == 0:
            return y_dBm[peaks], x_nm[peaks], peaks, properties, y_dBm

        # 找到“最强峰”（y_dBm 最大的峰）
        i_max = int(np.argmax(y_dBm[peaks]))
        p_max = peaks[i_max]

        # 只计算最强峰到左右谷底的距离（nm）
        dL = float(np.abs(x_nm[p_max] - x_nm[left_bases[i_max]]))
        dR = float(np.abs(x_nm[p_max] - x_nm[right_bases[i_max]]))

        # 只有最强峰任一侧 < 阈值才删
        bad_max = (dL < min_peak_valley_nm) or (dR < min_peak_valley_nm)

        # 最强峰不需要删 => 结束（不删其他峰）
        if not bad_max:
            break

        # 删除最强峰（同步删除 bases）
        keep = np.ones(len(peaks), dtype=bool)
        keep[i_max] = False
        peaks = peaks[keep]
        left_bases = left_bases[keep]
        right_bases = right_bases[keep]

        if len(peaks) == 0:
            return y_dBm[peaks], x_nm[peaks], peaks, properties, y_dBm

        # ---- 删除后：按“相邻两峰之间最深谷”重新更新剩余峰的 bases ----
        for i, p in enumerate(peaks):
            if 0 < i < len(peaks) - 1:
                p_left = peaks[i - 1]
                p_right = peaks[i + 1]

                mask_left = (valleys > p_left) & (valleys < p)
                v_left = valleys[mask_left]
                if v_left.size > 0:
                    left_bases[i] = v_left[np.argmin(y_dBm[v_left])]

                mask_right = (valleys > p) & (valleys < p_right)
                v_right = valleys[mask_right]
                if v_right.size > 0:
                    right_bases[i] = v_right[np.argmin(y_dBm[v_right])]

            # 端点峰：保持当前 left_bases/right_bases（删峰后它们已同步被裁剪）
            # 不额外强行回到 SciPy 原始值，避免不连续

    # ============ 修改逻辑结束 ============

    # ---- 基于新的左右谷底更新宽度（仅中间峰） ----
    new_width_pts = right_bases - left_bases
    new_width_nm  = x_nm[right_bases] - x_nm[left_bases]

    # 但最左峰、最右峰的宽度改回“原始 SciPy”
    new_width_pts[0]  = orig_width_pts[0] * 2.5
    new_width_nm[0]   = new_width_nm[0] * 0.04

    new_width_pts[-1] = orig_width_pts[-1] * 2.5
    new_width_nm[-1]  = orig_width_nm[-1] * 0.04

    # 写回 properties
    properties["left_bases"]  = left_bases
    properties["right_bases"] = right_bases
    properties["widths"]      = new_width_pts
    properties["widths_nm"]   = new_width_nm

    # ===== 新增：用“重写后的 widths”过滤掉 width < 50 的峰（最小改动）=====
    width_min = 30  # 你要的阈值
    keep = properties["widths"] >= width_min

    # 如果全被过滤掉，返回“无峰”
    if not np.any(keep):
        peaks = np.array([], dtype=int)
        # 保持接口一致：y_dBm[peaks] 和 x_nm[peaks] 都是空数组
        return y_dBm[peaks], x_nm[peaks], peaks, properties, y_dBm

    # 过滤 peaks
    peaks = peaks[keep]

    # 同步过滤 properties 里“与峰一一对应”的数组项（长度等于原峰数的那些）
    # 注意：properties 里还有一些标量/非数组，不动即可
    for k, v in list(properties.items()):
        try:
            v_arr = np.asarray(v)
            if v_arr.shape[0] == keep.shape[0]:  # 与峰数一致
                properties[k] = v_arr[keep]
        except Exception:
            pass
    # ===============================================================

    return y_dBm[peaks], x_nm[peaks], peaks, properties, y_dBm






def fitness_symmetry(meas_peaks, w_pos=100, w_amp=100,
                     huge=np.inf,
                     widths=None):
    """
    用于识别“具有对称结构的束缚态双孤子分子”的适应度（越小越好）

    现在支持三种情况：
    1. 3 个峰：单孤子 + 1 对 Kelly 边带（过渡态）
    2. 5 个峰：单孤子 + 2 对 Kelly 边带（过渡态）
    3. 8 个峰：完整双孤子分子（原有逻辑）
    """

    # --- 新：统一单孤子过渡态逻辑（最强峰做轴，最多两对边带） ---
    if meas_peaks is None or len(meas_peaks) == 0:
        return huge

    # 先看 widths 是否可用（因为要第一时间判断最强峰宽度）
    if widths is not None and len(widths) == len(meas_peaks):
        xs = np.array([p[0] for p in meas_peaks], dtype=float)
        amps = np.array([p[1] for p in meas_peaks], dtype=float)
        widths_arr = np.array(widths, dtype=float)

        # 1) 第一时间判断：最强峰宽度是否 > 350
        idx0 = int(np.argmax(amps))
        if widths_arr[idx0] > 300 and len(meas_peaks) > 2:
            axis = float(xs[idx0])

            # 2) 幅度归一化
            s = float(np.sum(amps))
            if s == 0:
                return huge
            amps_n = amps / s

            # 3) 轴左右峰索引，按“离轴距离”从近到远排序
            left = np.where(xs < axis)[0]
            right = np.where(xs > axis)[0]
            if left.size == 0 or right.size == 0:
                return huge

            left = left[np.argsort(np.abs(xs[left] - axis))]
            right = right[np.argsort(np.abs(xs[right] - axis))]

            # 最多两对
            num_pairs = min(2, left.size, right.size)
            if num_pairs < 1:
                return huge

            # 4) 归一化尺度 L（用参与配对的峰的最远距离）
            used = np.concatenate([left[:num_pairs], right[:num_pairs]])
            L = float(np.max(np.abs(xs[used] - axis)))
            if L == 0:
                return huge

            pos_errs, amp_errs = [], []
            for k in range(num_pairs):
                i = int(left[k])
                j = int(right[k])
                di = xs[i] - axis
                dj = xs[j] - axis
                pos_errs.append(((di + dj) / L) ** 2)
                amp_errs.append((amps_n[i] - amps_n[j]) ** 2)

            pos_err = float(np.mean(pos_errs)) / 4.0
            amp_err = float(np.mean(amp_errs))
            symmetry_err = pos_err + amp_err
            print(f"unified symmetry fitness {symmetry_err}")

            if symmetry_err < 0.25:
                return 0.5
            return huge

    # 如果 widths 不可用，或最强峰宽度 <= 350，则不在这里返回，继续走你后面的原逻辑
    # -----------------------------------------------------

    # ------------------- 原有 8 峰逻辑开始 ----------------
    if meas_peaks is None or len(meas_peaks) < 6 or len(meas_peaks) > 11:
        return huge

    # ===== 新增门槛 + 新的 8 峰选择方式 =====

    # 1) 全部峰先按 x 排序（保留原索引，方便判断“相邻”）
    peaks_x = sorted(list(enumerate(meas_peaks)), key=lambda it: it[1][0])
    xs_all = np.array([p[0] for _, p in peaks_x], dtype=float)  # 所有峰的 x（按位置）
    amps_all = np.array([p[1] for _, p in peaks_x], dtype=float)  # 所有峰的 amp（按位置）
    orig_idx_all = np.array([idx for idx, _ in peaks_x], dtype=int)

    # 2) 找到“全体峰里强度最大的两个峰”（用原始索引表示）
    top2 = sorted(list(enumerate(meas_peaks)), key=lambda it: it[1][1], reverse=True)[:2]
    idx_a = top2[0][0]  # meas_peaks 中的索引
    idx_b = top2[1][0]

    amp_a = float(meas_peaks[idx_a][1])
    amp_b = float(meas_peaks[idx_b][1])

    x_a = float(meas_peaks[idx_a][0])
    x_b = float(meas_peaks[idx_b][0])

    # # 强度差门槛
    # if abs(amp_a - amp_b) >= 1.5:
    #     return huge

    # 距离差门槛
    if abs(x_a - x_b) <= 1.2:
        return huge

    # 3) 判断这两个最强峰在 x 排序后是否相邻
    pos_a = int(np.where(orig_idx_all == idx_a)[0][0])
    pos_b = int(np.where(orig_idx_all == idx_b)[0][0])
    if abs(pos_a - pos_b) != 1 or widths[idx_a] > 150 or widths[idx_b] > 150:
        print(1)
        return huge

    # 4) 以这两个峰为中心：左侧取 3 个 + 两个中心峰 + 右侧取 3 个 => 8 个
    left_pos = min(pos_a, pos_b)
    right_pos = max(pos_a, pos_b)

    start = left_pos - 2
    end = right_pos + 2

    # 边界检查：必须能凑够 8 个
    if start < 0 or end >= len(peaks_x):
        return huge

    selected = peaks_x[start:end + 1]  # 长度应为 8
    if len(selected) != 6:
        return huge

    # 5) 用这 8 个峰进入你原来的对称性计算（保持不变）
    meas_peaks_sorted = [p for _, p in selected]  # 已经按 x 排好序
    xs = np.array([p[0] for p in meas_peaks_sorted], dtype=float)
    amps = np.array([p[1] for p in meas_peaks_sorted], dtype=float)

    sum_amp = np.sum(amps)
    if sum_amp == 0:
        return huge
    amps_n = amps / sum_amp

    n = len(xs)  # 这里应为 8

    # 中间两个峰的中心作为对称轴（现在刚好就是“最强的两个峰”，且位于索引 3、4）
    mid_left = n // 2 - 1
    mid_right = n // 2
    axis = 0.5 * (xs[mid_left] + xs[mid_right])

    # 配对 (mid_left, mid_right), (mid_left-1, mid_right+1), ...
    pairs = []
    i = mid_left
    j = mid_right
    while i >= 0 and j < n:
        pairs.append((i, j))
        i -= 1
        j += 1

    L = np.max(np.abs(xs - axis))
    if L == 0:
        return huge

    pos_errs = []
    amp_errs = []

    for i, j in pairs:
        di = xs[i] - axis
        dj = xs[j] - axis

        pos_errs.append(((di + dj) / L) ** 2)
        amp_errs.append((amps_n[i] - amps_n[j]) ** 2)

    pos_err = float(np.mean(pos_errs)) / 4 if pos_errs else 0.0
    amp_err = float(np.mean(amp_errs)) if amp_errs else 0.0

    fitness = w_pos * pos_err + w_amp * amp_err
    if fitness > 1:
        print(fitness)
        return huge
    return fitness






def voltage_pso_optimization(
        v_min: float = 0.0,
        v_max: float = 135.0,
        num_particles: int = 10,
        max_iterations: int = 1000
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
    OSC_meas = RTP_Oscilloscope()

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
        personal_best_freq_scores = np.full(num_particles, np.inf)  # 频率std适应度
        global_best_freq_score = np.inf  # 全局最优频率std

        # ---- 新增：第一次 global_best < 0.3 后，下一轮聚焦撒点（只做一次）----
        focus_once = False  # 是否已触发过
        focus_next = False  # 下一轮是否执行
        focus_center = None  # 聚焦中心（当时的 global_best_position）
        focus_span = 1.5  # ±2 V
        # -------------------------------------------------------------------

        # max_iterations 次的迭代循环
        for iteration in range(max_iterations):

            # ---- 新增：若上一轮触发了聚焦，本轮开始时把其它粒子撒到 gbest±2V ----
            if focus_next and focus_center is not None:
                focus_next = False

                # 找到当前最接近 focus_center 的粒子当“锚点”，它不动（避免把最优粒子也打散）
                anchor = int(np.argmin(np.linalg.norm(particles - focus_center, axis=1)))

                for j in range(num_particles):
                    if j == anchor:
                        continue
                    particles[j] = focus_center + np.random.uniform(-focus_span, focus_span, 4)
                    particles[j] = np.clip(particles[j], v_min, v_max)
                    velocities[j] = 0.0
                    personal_best_scores[j] = np.inf
                    personal_best_positions[j] = particles[j].copy()

                print(f"[FOCUS] Re-scatter particles around {focus_center} ±{focus_span}V")
            # -------------------------------------------------------------------

            print(f"\n======================== PSO迭代 {iteration + 1}/{max_iterations} ========================")
            # num_particles 个粒子的操作
            for i in range(num_particles):
                v = particles[i]  # 当前粒子的电压（四个通道）
                # 为每个通道设置电压并等待稳定
                for channel in range(1, 5):  # 四个通道
                    ctrl.set_voltage(channel, v[channel - 1])
                time.sleep(0.8)  # 等待电压稳定

                #光谱仪操作
                y_dBm, x_nm = meas.read_OSA()
                y_dBm_peaks, x_nm_peaks, peaks, properties, y_lvbo = Get_Peaks(y_dBm, x_nm)
                meas_peaks  = list(zip(x_nm_peaks, y_dBm_peaks))

                all_spectra.append((np.array(x_nm), np.array(y_lvbo)))  # 把光谱加进动图素材

                widths = properties["widths"]  # find_peaks 给出的每个峰的宽度

                #示波器测频率稳定性
                # 采样20次，计算标准差，有一次采样失败标准差就不存在


                fitness = fitness_symmetry(meas_peaks, widths = widths)
                if fitness == 0.5:
                    latest_transit_pos = v.copy()
                print(fitness)

                    # ★★★ 新增：每当找到更小的全局适应度时，保存当前光谱数据到新文件
                    # k = k+1
                    # filename = f"osa_best_iter{iteration + 1}_particle{i + 1}_best{k}.txt"
                    # format_results(y_dBm, x_nm, precision=2, save_file=filename)

                print(f"粒子 {i+1} 电压 {v} -> 峰的个数：{len(y_dBm_peaks)} -> 适应度分数: {fitness if fitness is not None else 'NaN'} Hz")


                # ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ ❗ 退出条件/以时序稳定性更新
                if fitness <= 0.25:
                    frequencies = []
                    time.sleep(5)
                    for _ in range(20):
                        freq = OSC_meas.measure_channel1_frequency()
                        if freq is None :
                            std = np.nan
                            break
                        time.sleep(0.2)
                        frequencies.append(freq)
                    std = np.std(frequencies) if len(frequencies) == 20 else np.inf
                    print(f"当前频率稳定性std = {std}")

                    if std < 650000 and std > 10:
                        print("条件全部达成，退出寻优~")
                        OSC_meas.set_timebase_scale(2e-6)
                        time.sleep(1)
                        OSC_meas.stop_acquisition()
                        OSC_meas.set_timebase_scale(2e-7)
                        OSC_meas.take_screenshot()
                        make_osa_animation(all_spectra, filename="osa_pso.gif", fps=2)  # 动图制作
                        # 保存所有光谱数据
                        with open('all_spectra.pkl', 'wb') as f:
                            pickle.dump(all_spectra, f)
                        print("所有光谱数据已保存到 all_spectra.pkl")

                        return
                    else:
                        print("频率稳定性不达标，继续寻优！！")
                        # 用频率更新最优
                        if np.isfinite(std) and std > 10:
                            if std < personal_best_freq_scores[i]:
                                personal_best_freq_scores[i] = std
                                personal_best_positions[i] = v.copy()
                                personal_best_scores[i] = 0.1  # 同步更新，让步长变小

                            if std < global_best_freq_score:
                                global_best_freq_score = std
                                global_best_position = v.copy()
                                global_best_score = 0.1
                                print(f"[时序稳定性优化] 全局最优更新: {std:.0f} Hz ⭐")

                        # ---- 新增：第一次 global_best < 0.25 -> 下一轮触发聚焦撒点（只触发一次）----
                        if (not focus_once) and global_best_score < 0.25:
                            focus_once = True
                            focus_next = True
                            focus_center = global_best_position.copy()
                            print(
                                f"第一次 global_best < 0.25 -> 下一轮触发聚焦撒点")
                        # -------------------------------------------------------------------

                # 当光谱适应度大于0.25时，才用光谱适应度更新全局最佳
                else:
                    # 更新个体最优
                    if fitness is not None and np.isfinite(fitness) and fitness < personal_best_scores[i]:
                        personal_best_scores[i] = fitness
                        personal_best_positions[i] = v.copy()

                    # 更新全局最优
                    if np.isfinite(personal_best_scores[i]) and personal_best_scores[i] < global_best_score:
                        global_best_score = personal_best_scores[i]
                        global_best_position = personal_best_positions[i].copy()

            #若全局最佳是0.5，每三轮更新一次
            if iteration % 3 == 0 and global_best_score == 0.5:
                global_best_position = latest_transit_pos.copy()  # 把吸引中心挪到最新过渡态点
                print("全局最佳更新")

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
                        local_span = 5 # 比如 ±5V 的小立方体
                        particles[i] = global_best_position + np.random.uniform(-local_span, local_span, 4)
                        particles[i] = np.clip(particles[i], v_min, v_max)

                    personal_best_positions[i] = particles[i]
                    continue

                # ===== 根据适应度调节最大步长：适应度越小，步长越小 =====
                score = personal_best_scores[i]

                # 设定一个“好到什么程度”的参考尺度，比如 0.05
                # 小于它就认为已经很不错了，进入很小步长微调区间
                score_ref = 0.5

                # 把 score 截断到 [0, score_ref]
                score_clipped = min(max(score, 0.0), score_ref)

                # 映射到一个 [step_min_factor, 1] 的因子：
                #   score_clipped = score_ref 时 → factor = 1 （很差，步长最大）
                #   score_clipped → 0 时         → factor → step_min_factor（很好，步长最小）
                step_min_factor = 0.1  # 最小步长比例（防止完全不动）
                factor = step_min_factor + (1.0 - step_min_factor) * (score_clipped / score_ref)

                # 电压每次的最大步长基准，比如 4 V（你可以自己调 1~5 V 看效果）
                v_step_max_base = 10.0
                if personal_best_scores[i] < 0.25:
                    v_step_max = 4  # 中步找稳定
                else:
                    v_step_max = v_step_max_base * factor
                # ===================================================
                if personal_best_scores[i] < 0.25:
                    w = 0.65
                    c1 = 1.9
                    c2 = 1.9
                else:
                    w = 0.5
                    c1 = 1.5
                    c2 = 1.5
                r1 = np.random.rand(4)
                r2 = np.random.rand(4)

                velocities[i] = (w * velocities[i]
                                 + c1 * r1 * (personal_best_positions[i] - particles[i])
                                 + c2 * r2 * (global_best_position - particles[i]))

                # 用适应度决定的最大步长限制速度
                velocities[i] = np.clip(velocities[i], -v_step_max, v_step_max)
                if global_best_score == 0.5:
                    velocities[i] += np.random.uniform(-1, 1, 4)
                # 更新粒子位置前，记录旧位置(用于打印步长)
                old_pos = particles[i].copy()

                # 更新粒子位置
                particles[i] += velocities[i]
                particles[i] = np.clip(particles[i], v_min, v_max)

                # 计算并打印实际步长
                step_vec = particles[i] - old_pos
                step_norm = np.linalg.norm(step_vec)
                print(f"Particle {i} step norm = {step_norm:.2f} V, ")

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


def find_freq_cmd(osc):
    osc.timeout = 20000
    osc.read_termination = '\n'
    osc.write_termination = '\n'
    osc.write("*CLS")

    cand = [
        "MEASure:FREQuency?",          # 一些R&S也支持
        "MEASure:ITEM? FREQuency,C2",  # 常见“item”风格
        "CALCulate:MEASure:FREQuency? C2",
        "CALCulate:MARKer1:X?",        # 如果需要用marker体系
    ]

    for c in cand:
        try:
            print("TRY", c)
            r = osc.query(c).strip()
            print("OK ", c, "=>", r)
        except Exception as e:
            try:
                err = osc.query("SYST:ERR?").strip()
            except Exception:
                err = "ERR? failed"
            print("NO ", c, "=>", e, "|", err)


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

    # frequencies = []
    # OSC_meas = RTP_Oscilloscope()
    # for _measfre_ in range(20):
    #     freq = OSC_meas.measure_channel1_frequency()
    #     if freq > 1e9 or np.isnan(freq):
    #         std = np.nan
    #         break
    #     time.sleep(0.05)
    #     frequencies.append(freq)
    # if len(frequencies) == 20:
    #     std = np.std(frequencies)
    #     print(frequencies)
    #     print(f"当前频率稳定性std = {std}")
    # OSC_meas.take_screenshot()
    # OSC_meas.close()

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

