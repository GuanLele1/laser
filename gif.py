from PIL import Image, ImageSequence

def change_gif_durations(
    input_gif: str,
    output_gif: str = "osa_pso_new.gif",
    normal_ms: int = 100,   # 前面每帧 0.05s = 50ms
    last_ms: int = 10000    # 最后一帧 3s = 3000ms
):
    """
    将 GIF 的前 n-1 帧设置为 normal_ms，最后一帧设置为 last_ms
    """
    im = Image.open(input_gif)

    # 读取所有帧
    frames = [frame.copy() for frame in ImageSequence.Iterator(im)]
    n = len(frames)
    if n == 0:
        raise ValueError("GIF 中没有任何帧。")

    # 为每一帧设置对应的播放时间（单位：毫秒）
    durations = [normal_ms] * (n - 1) + [last_ms]

    # 保存新 GIF
    frames[0].save(
        output_gif,
        save_all=True,
        append_images=frames[1:],
        duration=durations,  # 关键参数：每帧时长列表
        loop=0,              # 循环播放
        disposal=2           # 尽量避免残影问题
    )
    print(f"已生成新的 GIF：{output_gif}，共 {n} 帧。")


# 使用示例：
# 假设你原来保存的是 "osa_pso.gif"，282 帧：
# 前 281 帧 0.05s，最后一帧 3s
if __name__ == "__main__":
    change_gif_durations(
        "osa_pso.gif",
        "osa_pso_slow_last.gif",
        normal_ms=80,
        last_ms=8000
    )