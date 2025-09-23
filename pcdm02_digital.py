import serial
import time
import numpy as np
import pyvisa
import sys
import os
import matplotlib.pyplot as plt


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


class MeasurementSystem:
    """
    测量系统（示波器接口）
    """

    def __init__(self, visa_address='USB0::0x1AB1::0x04B1::DS4B201100033::INSTR'):
        self.rm = pyvisa.ResourceManager()
        try:
            self.osc = self.rm.open_resource(visa_address)
            self.osc.timeout = 5000  # 设置5秒超时
        except pyvisa.Error as e:
            print(f"示波器连接失败: {str(e)}")
            self.osc = None

    def get_frequency(self):
        """获取通道2的频率测量值"""
        if not self.osc:
            return np.nan
        try:
            self.osc.write(':MEASure:SOURce CHANnel1')
            self.osc.write(':MEASure:FREQuency?')
            result = self.osc.read().strip()
            result = float(result)
            if result == 9.9e+37:
                print("错误：未检测到有效信号或测量超限！")
                return np.nan
            return result

        except pyvisa.Error as e:
            print(f"频率测量失败: {str(e)}")
            return np.nan

    def screenshot(self, filename="rigol_ds4000_screenshot.png", color=True):
        """
        抓取当前屏幕截图并保存为 PNG 到本机文件系统。
        :param filename: 保存文件名（.png）
        :param color: True=彩色，False=黑白
        :return: 保存的文件路径；失败时返回 None
        """
        if not self.osc:
            return None
        try:
            # 尝试增大一次读取块大小，避免PNG被截断（不影响其它方法）
            try:
                #提高超时时间
                #self.osc.timeout = max(self.osc.timeout, 20000)
                self.osc.chunk_size = max(getattr(self.osc, "chunk_size", 1024 * 1024), 1024 * 1024)
            except Exception:
                pass

            # # RIGOL DS4000 系列：:DISP:DATA? {ON|OFF}[,OFF]
            # # ON=彩色；OFF=单色；第二个 OFF 表示不叠加菜单（不同固件可能忽略）
            # mode = "ON" if color else "OFF"
            self.osc.write(f":DISPlay:DATA?")

            # 读取二进制块（IEEE 488.2 block），形如 b'#9<length><payload>'
            raw = self.osc.read_raw()
            if not raw:
                return None

            # 解析二进制块头
            # 期望格式：b'#' + 1位数字(表示长度字段的位数n) + n位十进制长度 + 数据payload
            if raw[0:1] == b'#' and len(raw) >= 2:
                n_digits = int(chr(raw[1]))
                if n_digits > 0 and len(raw) >= 2 + n_digits:
                    total_len = int(raw[2:2 + n_digits].decode("ascii", errors="ignore"))
                    start = 2 + n_digits
                    payload = raw[start:start + total_len]
                else:
                    # 异常回退：尽量当作纯 PNG 处理
                    payload = raw.lstrip(b'#0123456789')
            else:
                # 没有块头时，直接当作 PNG 数据
                payload = raw

            # 保存文件
            with open(filename, "wb") as f:
                f.write(payload)

            # 简单校验 PNG 头（非致命）
            if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
                # 某些固件可能返回 BMP；你也可以在这里加一个 BMP 头判断
                pass

            #打开文件
            if sys.platform.startswith("win"):
                os.startfile(filename)
            elif sys.platform == "darwin":
                os.system(f"open '{filename}'")
            else:
                os.system(f"xdg-open '{filename}'")

            return filename

        except Exception as e:
            print(f"截图失败: {e}")
            return None

    def close(self):
        if self.osc:
            self.osc.close()


def voltage_optimization(
        channel: int = 1,
        v_min: float = 1.0,  # 实际输出电压最小值 (0V)
        v_max: float = 130.0,  # 实际输出电压最大值 (140V)
        step: float = 1.0  # 步长 (1.0V)
):
    """
    数字控制模式下的电压遍历优化
    :param channel: 目标通道 (1-4)
    :param v_min: 起始电压 (单位：V)
    :param v_max: 终止电压 (单位：V)
    :param step: 步长 (单位：V)
    """
    ctrl = PCDM02DigitalController(port='COM7')
    meas = MeasurementSystem()
    i = 0
    try:
        voltages = np.arange(v_min, v_max + step, step)
        std_results = []
        print(voltages)
        for v in voltages:
            # 电压有效性检查
            if v < 0 or v > 140:
                print(f"跳过无效电压: {v} V")
                std_results.append(np.nan)
                continue

            # 设置电压并等待稳定
            ctrl.set_voltage(channel, v)
            time.sleep(0.2)  # 等待压电元件响应
            print(v)
            #采集50个数据点计算标准差
            frequencies = []
            for i in range(25):
                freq = meas.get_frequency()
                if freq > 1e9 or np.isnan(freq):
                    std = np.nan
                    break
                frequencies.append(freq)
                time.sleep(0.2)
            print(frequencies)
            std = np.std(frequencies)
            std_results.append(std)
            print(f"电压 {v:.2f} V -> 标准差: {std:.2f} Hz")

        # 找到最优电压（最小标准差）
        valid_data = [(v, s) for v, s in zip(voltages, std_results) if not np.isnan(s)]
        if not valid_data:
            print("所有电压点均无效")
            return

        optimal_v, min_std = min(valid_data, key=lambda x: x[1])
        result_len = len(valid_data)
        # 输出结果
        print(valid_data)
        print("\n===== 优化结果 =====")
        print(f"最优电压: {optimal_v:.2f} V")
        print(f"最小标准差: {min_std:.2f} Hz")
        print(f"有效数据: {result_len:.2f} ")


        ctrl.set_voltage(channel, optimal_v)

        # 绘制结果
        # plt.figure(figsize=(10, 6))
        # plt.plot(voltages, std_results, 'r-o', linewidth=2)
        # plt.xlabel("输出电压 (V)")
        # plt.ylabel("频率标准差 (Hz)")
        # plt.title("数字控制模式电压优化曲线")
        # plt.grid(True)
        # plt.show()

    finally:
        ctrl.close()
        meas.close()



def voltage_pso_optimization(
        channel: int = 1,
        v_min: float = 0.0,
        v_max: float = 140.0,
        num_particles: int = 20,
        max_iterations: int = 5
):
    """
    用粒子群算法(PSO)自动优化输出电压，使目标频率标准差最小
    :param channel: 目标通道 (1-4)
    :param v_min: 起始电压 (单位：V)
    :param v_max: 终止电压 (单位：V)
    :param num_particles: 粒子数量
    :param max_iterations: 最大迭代次数
    """
    ctrl = PCDM02DigitalController(port='COM7')
    meas = MeasurementSystem()

    try:
        # 初始化
        particles = np.random.uniform(v_min, v_max, num_particles)
        velocities = np.zeros(num_particles)
        personal_best_positions = particles.copy()
        personal_best_scores = np.full(num_particles, np.inf)
        global_best_position = np.nan
        global_best_score = np.inf

        #max_iterations次的迭代循环
        for iteration in range(max_iterations):
            print(f"\n=== PSO迭代 {iteration+1}/{max_iterations} ===")
            #num_particles个粒子的操作
            for i in range(num_particles):
                v = particles[i]
                # 设定电压并等待稳定
                ctrl.set_voltage(channel, v)
                time.sleep(1)

                # 采样20次，计算标准差，有一次采样失败标准差就不存在
                frequencies = []
                for _ in range(20):
                    freq = meas.get_frequency()
                    if freq > 1e9 or np.isnan(freq):
                        std = np.nan
                        break
                    time.sleep(0.2)
                    frequencies.append(freq)

                if len(frequencies) == 20:
                    std = np.std(frequencies)

                # 更新个体最优
                if (std is not None) and (std > 10) and (std < personal_best_scores[i]) and (not np.isnan(std)):
                    personal_best_scores[i] = std
                    personal_best_positions[i] = v

                # 更新全局最优
                if personal_best_scores[i] < global_best_score:
                    global_best_score = personal_best_scores[i]
                    global_best_position = personal_best_positions[i]

                print(f"粒子 {i+1} 电压 {v:.2f} V -> 标准差: {std if std is not None else 'NaN'} Hz")

            # 粒子群速度与位置更新
            for i in range(num_particles):
                if np.isinf(personal_best_scores[i]):
                    print(f"[重置] 第 {i} 个粒子有个体最佳为 inf，对其重置。")
                    particles[i] = np.random.uniform(v_min, v_max)
                    personal_best_positions[i] = particles[i]
                    continue
                w = 0.5
                c1 = 1.5
                c2 = 1.5
                r1 = np.random.rand()
                r2 = np.random.rand()
                velocities[i] = (w * velocities[i]
                                 + c1 * r1 * (personal_best_positions[i] - particles[i])
                                 + c2 * r2 * (global_best_position - particles[i]))
                particles[i] += velocities[i]
                particles[i] = np.clip(particles[i], v_min, v_max)  # 限定范围

            print(f"当前最优电压: {global_best_position:.2f} V  最小标准差: {global_best_score:.2f} Hz")

        # 输出最终最优解
        print("\n===== 粒子群优化结果 =====")
        print(f"最优电压: {global_best_position:.2f} V")
        print(f"最小标准差: {global_best_score:.2f} Hz")

        ctrl.set_voltage(channel, global_best_position)

        # 如需可选作图
        # import matplotlib.pyplot as plt
        # plt.plot(range(1, max_iterations+1), best_scores_per_iteration, 'b-o')
        # plt.xlabel("迭代次数")
        # plt.ylabel("最小标准差 (Hz)")
        # plt.title("PSO优化收敛过程")
        # plt.grid(True)
        # plt.show()

    finally:
        ctrl.close()
        meas.close()

# 你需要保证 PCDM02DigitalController 和 MeasurementSystem 已实现，并有 set_voltage/get_frequency 方法


def voltage_pso_optimization2(
        channel: int = 1,
        v_min: float = 0.0,
        v_max: float = 140.0,
        num_particles: int = 20,
        max_iterations: int = 10
):
    """
    用粒子群算法(PSO)自动优化输出电压，使目标频率标准差最小
    :param channel: 目标通道 (1-4)
    :param v_min: 起始电压 (单位：V)
    :param v_max: 终止电压 (单位：V)
    :param num_particles: 粒子数量
    :param max_iterations: 最大迭代次数
    """
    ctrl = PCDM02DigitalController(port='COM7')
    meas = MeasurementSystem()

    try:
        # 初始化
        particles = np.random.uniform(v_min, v_max, num_particles)
        velocities = np.zeros(num_particles)
        personal_best_positions = particles.copy()
        personal_best_scores = np.full(num_particles, np.inf)
        global_best_position = np.nan
        global_best_score = np.inf

        #max_iterations次的迭代循环
        for iteration in range(max_iterations):
            print(f"\n=== PSO迭代 {iteration+1}/{max_iterations} ===")
            #num_particles个粒子的操作
            for i in range(num_particles):
                v = particles[i]
                # 设定电压并等待稳定
                ctrl.set_voltage(channel, v)
                time.sleep(1)

                # 采样20次，计算标准差，有一次采样失败标准差就不存在
                frequencies = []
                for _ in range(20):
                    freq = meas.get_frequency()
                    if freq > 1e9 or np.isnan(freq):
                        std = np.nan
                        break
                    time.sleep(0.2)
                    frequencies.append(freq)

                if len(frequencies) == 20:
                    std = np.std(frequencies)

                # 更新个体最优
                if (std is not None) :
                    if std < 300000 and (std > 10):
                        print(f"[提前终止] 粒子 {i + 1} 标准差为 {std:.2f} Hz，小于 300000 Hz，提前设置电压并终止优化。")
                        ctrl.set_voltage(channel, v)
                        return  # 或 break 两层

                    if (std > 10) and (std < personal_best_scores[i]) and (not np.isnan(std)):
                        personal_best_scores[i] = std
                        personal_best_positions[i] = v

                # 更新全局最优
                if personal_best_scores[i] < global_best_score:
                    global_best_score = personal_best_scores[i]
                    global_best_position = personal_best_positions[i]

                print(f"粒子 {i+1} 电压 {v:.2f} V -> 标准差: {std if std is not None else 'NaN'} Hz")

            # 粒子群速度与位置更新
            for i in range(num_particles):
                if np.isinf(personal_best_scores[i]):
                    print(f"[重置] 第 {i} 个粒子有个体最佳为 inf，对其重置。")
                    particles[i] = np.random.uniform(v_min, v_max)
                    personal_best_positions[i] = particles[i]
                    continue
                w = 0.5
                c1 = 1.5
                c2 = 1.5
                r1 = np.random.rand()
                r2 = np.random.rand()
                velocities[i] = (w * velocities[i]
                                 + c1 * r1 * (personal_best_positions[i] - particles[i])
                                 + c2 * r2 * (global_best_position - particles[i]))
                particles[i] += velocities[i]
                particles[i] = np.clip(particles[i], v_min, v_max)  # 限定范围

            print(f"当前最优电压: {global_best_position:.2f} V  最小标准差: {global_best_score:.2f} Hz")

        # 输出最终最优解
        print("\n===== 粒子群优化结果 =====")
        print(f"最优电压: {global_best_position:.2f} V")
        print(f"最小标准差: {global_best_score:.2f} Hz")

        ctrl.set_voltage(channel, global_best_position)

        # 如需可选作图
        # import matplotlib.pyplot as plt
        # plt.plot(range(1, max_iterations+1), best_scores_per_iteration, 'b-o')
        # plt.xlabel("迭代次数")
        # plt.ylabel("最小标准差 (Hz)")
        # plt.title("PSO优化收敛过程")
        # plt.grid(True)
        # plt.show()

    finally:
        ctrl.close()
        meas.close()


def voltage_pso_optimization3(
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
    meas = MeasurementSystem()

    try:
        # 初始化
        # 现在粒子是一个4维数组，每个粒子对应四个通道的电压
        particles = np.random.uniform(v_min, v_max, (num_particles, 4))  # 粒子数量 x 4通道
        velocities = np.zeros((num_particles, 4))  # 对应四个通道的速度
        personal_best_positions = particles.copy()  # 个体最优位置（电压）
        personal_best_scores = np.full(num_particles, np.inf)  # 个体最优分数
        global_best_position = np.nan  # 全局最优位置
        global_best_score = np.inf  # 全局最优分数

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

                # 采样20次，计算标准差，有一次采样失败标准差就不存在
                frequencies = []
                for _ in range(20):
                    freq = meas.get_frequency()
                    if freq > 1e9 or np.isnan(freq):
                        std = np.nan
                        break
                    time.sleep(0.2)
                    frequencies.append(freq)

                if len(frequencies) == 20:
                    std = np.std(frequencies)

                # 更新个体最优
                if std is not None:
                    if std < 300000 and (std > 10):
                        print(f"[提前终止] 粒子 {i + 1} 标准差为 {std:.2f} Hz，小于 300000 Hz，提前设置电压并终止优化。")
                        # 为每个通道设置电压并终止
                        for channel in range(1, 5):  # 四个通道
                            ctrl.set_voltage(channel, v[channel - 1])
                        return  # 或 break 两层

                    if (std > 10) and (std < personal_best_scores[i]) and (not np.isnan(std)):
                        personal_best_scores[i] = std
                        personal_best_positions[i] = v

                # 更新全局最优
                if personal_best_scores[i] < global_best_score:
                    global_best_score = personal_best_scores[i]
                    global_best_position = personal_best_positions[i]

                print(f"粒子 {i+1} 电压 {v} -> 标准差: {std if std is not None else 'NaN'} Hz")

            # 粒子群速度与位置更新
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

            print(f"当前最优电压: {global_best_position} V  最小标准差: {global_best_score:.2f} Hz")

        # 输出最终最优解
        print("\n===== 粒子群优化结果 =====")
        print(f"最优电压: {global_best_position} V")
        print(f"最小标准差: {global_best_score:.2f} Hz")

        # 为每个通道设置全局最优电压
        for channel in range(1, 5):  # 四个通道
            ctrl.set_voltage(channel, global_best_position[channel - 1])

    finally:
        ctrl.close()
        meas.close()


if __name__ == "__main__":
    #meas = MeasurementSystem()
    #meas.screenshot()
    voltage_pso_optimization3()

