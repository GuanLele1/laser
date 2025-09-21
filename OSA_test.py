import pyvisa

ip = "192.168.1.3"  # ⚠️ 修改成你仪器的 IP 地址
rm = pyvisa.ResourceManager()
osa = rm.open_resource(f"TCPIP0::{ip}::inst0::INSTR")  # VXI-11 接口
osa.timeout = 30000  # ms，扫描时间可能较长

# ------------------------------
# 设置波长区间和参数
# ------------------------------
osa.write(":SENSE:WAVELENGTH:START 1535NM")  # 起始波长
osa.write(":SENSE:WAVELENGTH:STOP 1590NM")   # 结束波长
osa.write(":SENSE:BANDWIDTH:RESOLUTION 0.05NM")  # 设置分辨率（可选）
osa.write(":SENSE:SENSITIVITY HIGH1")        # 灵敏度（可根据需求设 AUTO、MID、HIGH1...）

# ------------------------------
# 扫描一次
# ------------------------------
osa.write(":INIT:CONT OFF")  # 设置为单次扫描模式
osa.write(":INIT")           # 发起扫描
osa.query("*OPC?")           # 等待扫描完成

# ------------------------------
# 读取数据（Y 轴功率值）
# ------------------------------
#npts = int(osa.query(":TRACe:DATA:SNUMber?"))       # 获取数据点数
xdata = osa.query(":TRACe:DATA:X? TRA")             # 获取波长数组（单位：米）
ydata = osa.query(":TRACe:DATA:Y? TRA")             # 获取功率数组（单位：dBm）

# 转换为 float 数组
x_nm = [float(x) * 1e9 for x in xdata.strip().split(",")]  # m → nm
y_dBm = [float(y) for y in ydata.strip().split(",")]

# 打印部分数据
#print(f"共 {npts} 点")
for i in range(2000):  # 前10个点
    print(f"{x_nm[i]:.2f} nm : {y_dBm[i]:.2f} dBm")

with open("power_values.txt", "w") as f:
    for y in y_dBm:
        f.write(f"{y:.2f}\n")

print("已保存到 power_values.txt")


filename = "osa_formatted_output.txt"

with open(filename, "w") as f:
    for x, y in zip(x_nm, y_dBm):
        f.write(f"{x:.2f} nm : {y:.2f} dBm\n")

print(f"格式化数据已保存到 {filename}")

osa.close()
rm.close()