"""打包脚本：生成单文件 exe（内置 ffmpeg / ffprobe）。

用法：在项目根目录运行  python build/build.py
产出：dist/BiliAutoUpload.exe
"""

import glob
import os
import shutil
import subprocess
import sys


def find_ffmpeg_dir() -> str:
    """定位 ffmpeg/ffprobe 所在目录。"""
    env = os.environ.get("FFMPEG_DIR")
    if env and os.path.isdir(env):
        return env
    # WinGet 常见安装路径
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
    for pkg in sorted(glob.glob(os.path.join(base, "Gyan.FFmpeg*"))):
        for bin_dir in glob.glob(os.path.join(pkg, "ffmpeg-*", "bin")):
            if os.path.isfile(os.path.join(bin_dir, "ffmpeg.exe")):
                return bin_dir
    # 系统 PATH
    p = shutil.which("ffmpeg.exe")
    if p:
        return os.path.dirname(p)
    return ""


def make_icon(path: str) -> None:
    """生成一个淡蓝色「B」图标 .ico。"""
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (256, 256), (91, 155, 213))
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arialbd.ttf", 170)
        except OSError:
            font = ImageFont.load_default()
        bbox = d.textbbox((0, 0), "B", font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((256 - w) / 2 - bbox[0], (256 - h) / 2 - bbox[1]), "B", fill="white", font=font)
        img.save(path)
    except Exception as e:  # noqa: BLE001
        print("生成图标失败（跳过）：", e)


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ffmpeg_dir = find_ffmpeg_dir()
    if not ffmpeg_dir:
        print("未找到 ffmpeg，请设置环境变量 FFMPEG_DIR 指向 ffmpeg/bin 目录")
        sys.exit(1)
    ffmpeg = os.path.join(ffmpeg_dir, "ffmpeg.exe")
    ffprobe = os.path.join(ffmpeg_dir, "ffprobe.exe")
    if not (os.path.isfile(ffmpeg) and os.path.isfile(ffprobe)):
        print("ffmpeg.exe / ffprobe.exe 不存在于", ffmpeg_dir)
        sys.exit(1)

    icon_path = os.path.join(root, "build", "app.ico")
    if not os.path.isfile(icon_path):
        make_icon(icon_path)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile", "--windowed",
        "--name", "BiliAutoUpload",
        "--add-binary", f"{ffmpeg};.",
        "--add-binary", f"{ffprobe};.",
        "--collect-all", "curl_cffi",
        "--collect-all", "bilibili_api",
        "main.py",
    ]
    if os.path.isfile(icon_path):
        cmd[cmd.index("--onefile") + 1:1] = ["--icon", icon_path]

    print("ffmpeg 目录:", ffmpeg_dir)
    print("执行打包（可能耗时几分钟）…")
    os.chdir(root)
    subprocess.run(cmd, check=True)
    print("打包完成：dist/BiliAutoUpload.exe")


if __name__ == "__main__":
    main()
