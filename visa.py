import serial
import time
import numpy as np
import pyvisa
import matplotlib.pyplot as plt

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

    def close(self):
        if self.osc:
            self.osc.close()
frequencies = []
meas = MeasurementSystem()
freq = meas.get_frequency()
for i in range(30):
    freq = meas.get_frequency()
    frequencies.append(freq)
    time.sleep(0.1)
std = np.std(frequencies)
print(frequencies)
print(std)