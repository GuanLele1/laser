import numpy as np
import serial
import time
import numpy as np
import pyvisa
from typing import Optional, Literal, List

#正交化相关函数
Strategy = Literal["pairwise+cyclic", "pairwise", "cyclic", "random"]

def orthonormalize_qr(candidate_dirs: np.ndarray, *, dim: int, tol: float = 1e-10) -> np.ndarray:
    """
    使用数值稳定的 QR 分解实现 Gram-Schmidt 正交化，返回单位正交基（每行为一个方向）。
    满足论文要求：
      1) 返回 dim 个方向（满秩覆盖变量空间）；
      2) 两两正交；
      3) 每个方向 L2 范数 = 1。
    """
    C = np.asarray(candidate_dirs, dtype=float)
    assert C.ndim == 2 and C.shape[1] == dim, f"candidate_dirs 必须是 (m, {dim})，实际 {C.shape}"

    # 在列上做 QR：C.T 的列是候选向量 → Q 的列正交
    Q, _ = np.linalg.qr(C.T)    # Q: (dim, k), k = min(m, dim)
    dirs = Q.T                  # 转回行向量

    # 若返回不足 dim 个方向（极少见），补随机向量后再做一次 QR
    if dirs.shape[0] < dim:
        need = dim - dirs.shape[0]
        extra = np.random.randn(need, dim)
        more = np.vstack([dirs, extra])
        Q2, _ = np.linalg.qr(more.T)
        dirs = Q2.T[:dim, :]

    # 单位化（QR 理论上已归一，这里做数值保护）
    norms = np.linalg.norm(dirs, axis=1, keepdims=True)
    norms[norms < tol] = 1.0
    dirs = dirs / norms
    return dirs

def build_candidates(old_dirs: np.ndarray,
                     *,
                     strategy: Strategy = "pairwise+cyclic",
                     noise_scale: float = 0.25,
                     rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """
    根据上轮方向构造“整组”候选方向（m>=dim），用于一轮全失败后的方向重构。
    默认采用 pairwise+cyclic 组合并加入微小高斯扰动，以降低秩亏风险。
    """
    rng = rng or np.random.default_rng()
    D = np.asarray(old_dirs, dtype=float)
    assert D.ndim == 2 and D.shape[0] == D.shape[1], f"old_dirs 必须是 (dim, dim)，实际 {D.shape}"
    dim = D.shape[0]

    cands: List[np.ndarray] = []

    if strategy in ("pairwise", "pairwise+cyclic"):
        # 相邻对：d_i + d_{i+1}
        for i in range(dim - 1):
            cands.append(D[i] + D[i + 1])
        # 跳一位：d_i + d_{i+2}
        for i in range(dim - 2):
            cands.append(D[i] + D[i + 2])

    if strategy in ("cyclic", "pairwise+cyclic"):
        # 循环移位：d_i + d_{i+1 (mod dim)}
        for i in range(dim):
            cands.append(D[i] + D[(i + 1) % dim])

    if strategy == "random" or len(cands) == 0:
        cands = [rng.standard_normal(dim) for _ in range(dim)]

    # 至少 dim 个候选
    while len(cands) < dim:
        cands.append(rng.standard_normal(dim))

    C = np.stack(cands, axis=0)

    # 小扰动帮助避免候选集合退化到秩亏
    if noise_scale > 0:
        C = C + rng.standard_normal(C.shape) * noise_scale
    return C

def reconstruct_directions(old_dirs: np.ndarray,
                           *,
                           strategy: Strategy = "pairwise+cyclic",
                           noise_scale: float = 0.25,
                           tol: float = 1e-10,
                           rng: Optional[np.random.Generator] = None) -> np.ndarray:
    """
    “一轮全失败 → 方向重构”的完整流程：
      1) 生成候选整组；
      2) QR 正交化；
      3) 返回单位正交基。
    """
    rng = rng or np.random.default_rng()
    C = build_candidates(old_dirs, strategy=strategy, noise_scale=noise_scale, rng=rng)
    dim = old_dirs.shape[0]
    new_dirs = orthonormalize_qr(C, dim=dim, tol=tol)
    return new_dirs



#设置电压
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


    def get_waveform_data(self):
        """获取示波器采集的波形数据"""
        if not self.osc:
            return None

        try:
            self.osc.write(':ACQuire:MDEPth:AUTO OFF')  # 关闭自动模式

            # 设置波形格式为字节数据
            self.osc.write(":WAV:FORM BYTE")
            self.osc.write(":WAV:MODE RAW")  # 设置为RAW模式

            # 获取波形数据
            self.osc.write(":WAV:POIN MAX")
            self.osc.write(":WAV:DATA?")
            waveform_data = self.osc.read_raw()

            # 解析返回的波形数据
            # 解析前缀（获取实际点数）
            prefix = waveform_data[0:1].decode()
            if prefix != '#':
                raise ValueError("数据格式错误")
            n = int(waveform_data[1:2].decode())
            length_str = waveform_data[2:2 + n].decode()
            data_length = int(length_str)
            valid_data = waveform_data[2 + n: 2 + n + data_length]
            waveform_array = np.frombuffer(valid_data, dtype=np.uint8)
            print(f"实际点数: {len(waveform_array)}")

            # 将波形数据转换为电压值
            # 你需要根据示波器的设置（YUNIT）来调整这个比例
            # voltage_scale = 0.01  # 假设单位是0.01V/单位，根据实际情况调整
            # waveform_array = (waveform_array - 128) * voltage_scale  # 归一化和电压换算

            return waveform_array

        except pyvisa.Error as e:
            print(f"获取波形数据失败: {str(e)}")
            return None

    def close(self):
        if self.osc:
            self.osc.close()


def dual_region_count_once(data, Nperiod_pts, pulse_width_pts=10, threshold1=0.8, threshold2=0.5):
    """
    双区域计数法实现
    data: 采集到的波形数据，numpy数组
    Nperiod_pts: 一个脉冲周期的采样点数
    pulse_width_pts: 脉冲主峰附近作为绿色区的采样点宽度
    threshold1: 主脉冲检测阈值（占最大值的比例，如0.7）
    threshold2: 噪声检测阈值（占最大值的比例，如0.2）
    返回值: (绿色区计数, 非绿色区计数, 各周期主峰索引)
    """
    max_val = max(140, np.max(data))
    th1 = threshold1 * max_val
    th2 = threshold2 * max_val

    total_periods = len(data) // Nperiod_pts
    green_counts = 0
    nongreen_counts = 0
    main_peak_indices = []

    for i in range(total_periods):
        #获取这段脉冲的区间
        period_start = i * Nperiod_pts
        period_end = period_start + Nperiod_pts
        period_data = data[period_start:period_end]

        # 找到主脉冲峰位置（绿色区中心）
        peak_idx = np.argmax(period_data)
        main_peak_indices.append(period_start + peak_idx)

        # 绿色区范围 50%
        green_start = max(0, peak_idx - pulse_width_pts // 2)
        green_end = min(Nperiod_pts, peak_idx + pulse_width_pts // 2 + 1)

        # 绿色区与非绿色区
        green_region = period_data[green_start:green_end]
        nongreen_region = np.concatenate([period_data[:green_start], period_data[green_end:]])

        # 绿色区：有大于th1的点就计1，否则0
        if np.any(green_region > th1):
            green_counts += 1

        # 非绿色区：有大于th2的点就计1，否则0
        if np.any(nongreen_region > th2):
            nongreen_counts += 1



    return green_counts, nongreen_counts, main_peak_indices




def     compute_fml_objective(data, Nperiod_pts = 406, pulse_width_pts=10, threshold1=0.9, threshold2=0.7):
    """
    计算 FML 模式下的目标函数值（严格按照绿色区判断，不采用主峰简化优化）

    参数说明：
    - data: 波形数据（1D numpy 数组）
    - Nperiod_pts: 一个脉冲周期所对应的采样点数量
    - pulse_width_pts: 绿色区宽度（主峰附近多少个采样点）
    - threshold1: 主峰判断阈值（占波形最大值的比例）
    - threshold2: 非绿色区噪声判断阈值（用于双区域计数）

    返回：
    - FML目标函数值（平均有效主峰幅值）；无有效主峰则返回 0.0
    """
    C_ideal = len(data) // Nperiod_pts  # 理想周期数（论文公式）

    # 调用双区域计数，获取绿色区脉冲个数、主峰索引
    green_counts, nongreen_counts, main_peak_indices = dual_region_count_once(
        data, Nperiod_pts, pulse_width_pts, threshold1, threshold2
    )

    if green_counts < C_ideal or nongreen_counts > 0:
        return 0

    max_val = np.max(data)
    th1 = threshold1 * max_val
    Ai_list = []

    for idx in main_peak_indices:
        # 计算绿色区（以主峰为中心的窗口）
        green_start = max(0, idx - pulse_width_pts // 2)
        green_end = min(len(data), idx + pulse_width_pts // 2 + 1)
        green_region = data[green_start:green_end]

        # 判断是否有任何点超过主峰阈值
        if np.any(green_region > th1):
            Ai = np.max(green_region)
            Ai_list.append(Ai)

    return np.mean(Ai_list) if Ai_list else 0.0






#以下是搜寻过程
def advanced_rosenbrock_search(
    param_bounds = [(1,130), (1,130), (1,130), (1,130)],
    objective_func = compute_fml_objective,
    init_step_size=1.0,
    reward_factor= 2.0,
    punish_factor= -0.8,
    patience_limit=5,
    max_iter=100
):
    """
    实现论文中“高级 Rosenbrock 搜索算法（ARS）”，用于智能锁模算法中的参数优化。

    参数说明：
    ----------
    - objective_func: callable，目标函数，输入参数数组，输出一个数值（目标值）
    - init_params: 初始参数向量（如 [v1, v2, v3, v4]）
    - param_bounds: 每个参数的边界范围，形如 [(0, 5000), (0, 5000), ...]
    - init_step_size: 初始搜索步长
    - reward_factor: 奖励因子 α（成功时放大步长）
    - punish_factor: 惩罚因子 β（失败时缩小步长）
    - patience_limit: 最大容忍失败轮数
    - max_iter: 最大迭代次数（防止死循环）

    返回值：
    -------
    - best_params: 最优参数值
    - best_score: 对应的目标函数值
    - history: 搜索轨迹（每次成功后的参数和目标值）
    """
    ctrl = PCDM02DigitalController(port='COM7')

    meas = MeasurementSystem()
    np.set_printoptions(threshold=np.inf)

    params  = np.array([np.random.uniform(low, high) for (low, high) in param_bounds])
    for i in range(4):
        ctrl.set_voltage(i + 1, params[i])
    time.sleep(1)
    data = meas.get_waveform_data()
    green_score, nongreen_counts, main_peak_indices = dual_region_count_once(data, 406)
    print(green_score)

    while green_score == 0 :
        print(f"⚠️ green_score = {green_score}，重启搜索（没有达到双区域计数条件）")
        params = np.array([np.random.uniform(low, high) for (low, high) in param_bounds])
        print(f"刷新电压:{params}")
        for i in range(4):
            ctrl.set_voltage(i + 1, params[i])
        time.sleep(1)
        data = meas.get_waveform_data()
        green_score, nongreen_counts, main_peak_indices = dual_region_count_once(data, 406)

    print(f"双区域计数成功，电压为：{params}")

    dim = len(params)
    best_params = params
    data = meas.get_waveform_data()
    best_score = objective_func(data)
    step_sizes = np.ones(dim) * init_step_size
    directions = np.eye(dim)  # 初始正交基方向（单位向量）
    # array([[1., 0., 0., 0.],
    #        [0., 1., 0., 0.],
    #        [0., 0., 1., 0.],
    #        [0., 0., 0., 1.]])
    patience = patience_limit

    if best_score > 120:
        return best_params, best_score

    iter_count = 0

    while iter_count < max_iter:
        print(f"=============第{iter_count}轮探索=============")
        improved = False

        for i in range(dim):
            # 当前探索方向
            print(f"--------通道{i+1}探索中--------")
            direction = directions[i]
            delta = step_sizes[i] * direction

            # 前向尝试
            forward_params = params + delta
            forward_params = np.clip(forward_params, [low for (low, _) in param_bounds], [high for (_, high) in param_bounds])

            # 设置电压
            for j in range(4):
                ctrl.set_voltage(i + 1, forward_params[i])
            time.sleep(0.8)
            data = meas.get_waveform_data()
            forward_score = objective_func(data)

            print(f"前向尝试电压{forward_params}")
            print(f"前向分数{forward_score}")

            if forward_score > best_score:
                # 成功：更新状态并奖励
                params = forward_params
                best_score = forward_score
                best_params = params.copy()
                step_sizes[i] *= reward_factor
                print(f"前向尝试成功，更新并奖励步长{step_sizes[i]}")
                improved = True
                continue

            else:
                # 失败：缩小步长
                step_sizes[i] = step_sizes[i] * punish_factor
                print(f"前向尝试失败，通道{i}惩罚步长：{step_sizes[i]}")

        iter_count += 1
        if best_score > 120:
            return  best_params, best_score

        if not improved:
            # 所有方向都失败：进行方向重构，并扣除耐心
            new_direction = np.random.randn(dim)
            directions  = reconstruct_directions(directions, strategy="pairwise+cyclic", noise_scale=0.2)
            patience -= 1
            if patience <= 0:
                # 耐心耗尽，重启整个过程
                while green_score == 0:
                    print(f"⚠️ green_score = {green_score}，重启搜索（Patience耗尽）")
                    params = np.array([np.random.uniform(low, high) for (low, high) in param_bounds])
                    for i in range(4):
                        ctrl.set_voltage(i + 1, params[i])
                    time.sleep(1)
                    meas = MeasurementSystem()
                    np.set_printoptions(threshold=np.inf)
                    data = meas.get_waveform_data()
                    green_score, nongreen_counts, main_peak_indices = dual_region_count_once(data, 406)

                best_params = params.copy()
                data = meas.get_waveform_data()
                best_score = objective_func(data)
                step_sizes = np.ones(dim) * init_step_size
                directions = np.eye(dim)
                patience = patience_limit


    return best_params, best_score


def advanced_rosenbrock_search2(
    param_bounds = [(1,130), (1,130), (1,130), (1,130)],
    objective_func = compute_fml_objective,
    init_step_size=10.0,
    reward_factor= 2,
    punish_factor= -0.5,
    patience_limit=5,
    max_iter=100
):
    """
    实现论文中“高级 Rosenbrock 搜索算法（ARS）”，用于智能锁模算法中的参数优化。

    参数说明：
    ----------
    - objective_func: callable，目标函数，输入参数数组，输出一个数值（目标值）
    - init_params: 初始参数向量（如 [v1, v2, v3, v4]）
    - param_bounds: 每个参数的边界范围，形如 [(0, 5000), (0, 5000), ...]
    - init_step_size: 初始搜索步长
    - reward_factor: 奖励因子 α（成功时放大步长）
    - punish_factor: 惩罚因子 β（失败时缩小步长）
    - patience_limit: 最大容忍失败轮数
    - max_iter: 最大迭代次数（防止死循环）

    返回值：
    -------
    - best_params: 最优参数值
    - best_score: 对应的目标函数值
    - history: 搜索轨迹（每次成功后的参数和目标值）
    """
    ctrl = PCDM02DigitalController(port='COM7')

    meas = MeasurementSystem()
    np.set_printoptions(threshold=np.inf)

    #初始化电压，并加到epc上
    params  = np.array([np.random.uniform(low, high) for (low, high) in param_bounds])
    for i in range(4):
        ctrl.set_voltage(i + 1, params[i])
    time.sleep(1.5)
    data = meas.get_waveform_data()

    post_count = 1  #统计选了多少个位置
    dir_count = 1   #统计这是重构的第几个方向

    print(f"================第{post_count}个位置=================")
    dim = len(params)
    best_params = params
    best_score = objective_func(data)
    step_sizes = np.ones(dim) * init_step_size
    directions = np.eye(dim)  # 初始正交基方向（单位向量）
    # array([[1., 0., 0., 0.],
    #        [0., 1., 0., 0.],
    #        [0., 0., 1., 0.],
    #        [0., 0., 0., 1.]])
    patience = patience_limit

    if best_score > 120:
        return best_params, best_score

    iter_count = 0

    while iter_count < max_iter:

        improved = False
        print(f"---------第{dir_count}个方向组----------")
        for i in range(dim):
            # 当前探索方向
            print(f"通道{i+1}探索中")
            direction = directions[i]
            delta = step_sizes[i] * direction

            # 前向尝试
            forward_params = params + delta
            forward_params = np.clip(forward_params, [low for (low, _) in param_bounds], [high for (_, high) in param_bounds])

            # 设置电压
            for j in range(4):
                ctrl.set_voltage(i + 1, forward_params[i])
            time.sleep(0.8)
            data = meas.get_waveform_data()
            forward_score = objective_func(data)

            print(f"前向尝试电压{forward_params}")
            print(f"前向分数{forward_score}")

            if forward_score > best_score:
                # 成功：更新状态并奖励
                params = forward_params
                best_score = forward_score
                best_params = params.copy()
                step_sizes[i] *= reward_factor
                print(f"前向尝试成功，更新并奖励步长{step_sizes[i]}")
                improved = True

                if best_score > 120:
                    return best_params, best_score
                continue

            else:
                # 失败：缩小步长
                step_sizes[i] = step_sizes[i] * punish_factor
                print(f"前向尝试失败，通道{i}惩罚步长：{step_sizes[i]}")

        iter_count += 1
        if best_score > 120:
            return  best_params, best_score

        if not improved:
            # 所有方向都失败：进行方向重构，并扣除耐心
            patience -= 1
            if patience > 0:
                directions  = reconstruct_directions(directions, strategy="pairwise+cyclic", noise_scale=0.2)
                step_sizes = np.ones(dim) * init_step_size
                print(f"所有方向均失败，方向重构!!")
                dir_count += 1
            else :
                # 耐心耗尽，重启整个过程
                print(f"!!耐心耗尽，重启!!")
                params = np.array([np.random.uniform(low, high) for (low, high) in param_bounds])
                for i in range(4):
                        ctrl.set_voltage(i + 1, params[i])
                time.sleep(1)
                data = meas.get_waveform_data()

                post_count += 1
                best_params = params.copy()
                best_score = objective_func(data)
                step_sizes = np.ones(dim) * init_step_size
                directions = np.eye(dim)
                patience = patience_limit
                print(f"================第{post_count}个位置=================")


    return best_params, best_score


if __name__ == "__main__":
    advanced_rosenbrock_search2()
    meas = MeasurementSystem()
    np.set_printoptions(threshold=np.inf)
    data = meas.get_waveform_data()
    forward_score = compute_fml_objective(data)
    print(forward_score)

