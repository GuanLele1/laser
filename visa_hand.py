
import serial
import time
import numpy as np
import pyvisa
import matplotlib.pyplot as plt


class PCDM02DigitalController:
    """
    PCD-M02数字控制模式接口
    通过STM32发送数字控制信号
    """

    def __init__(self, port='COM14', baudrate=115200):
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

    def __init__(self, visa_address='USB0::0x1AB1::0x0588::DS1ET144700964::INSTR'):
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

a = PCDM02DigitalController()
b = MeasurementSystem()

for i in range(140):
    a.set_voltage(1,i)
    c = b.get_frequency()
    print(i)
    print(c)
    time.sleep(0.2)
