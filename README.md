# AzothX-OLED

**ROG 夜魔 X OLED 通信协议逆向与自定义显示工具。**

通过 ROG OMNI 接收器向键盘的小屏上传自定义画面。项目包含主机端通信、208×64 灰度页面绘制、字体毛刺修复和验证工具。

已在一台 ROG Azoth X 经 2.4G 接收器连接的 Windows 电脑上验证。使用现有显示接口，不需要拆机或刷写键盘固件。

![修复后的时钟模拟预览](evidence/font-fix/after-5x.png)

上图为软件解码后的放大预览，不是实物照片。修复后的实物显示已由用户确认清楚。

## 可以显示什么

| 页面 | 内容 |
|---|---|
| `clock` | 时间、星期、日期、秒进度条 |
| `stats` | CPU、内存占用和历史曲线 |
| `net` | 上传、下载速率和曲线 |
| `pomodoro` | 专注倒计时和进度 |
| `text` | 自定义文字和副标题 |
| `blank` | 黑屏画面 |

另有静态图片和点阵文字入口。GIF 载荷构造已有实现，多帧播放时序和较长动画的可靠性仍需实物验证。

## 安装与使用

本机验证环境为 Windows、Python 3.12。安装依赖后，将键盘切到 2.4G 模式并按键唤醒。

```powershell
git clone https://github.com/wangding0610/AzothX-OLED.git
cd AzothX-OLED
python -m pip install -r requirements.txt
cd tools
python oled.py list
python show.py clock --once
```

持续更新时间，按 `Ctrl+C` 退出：

```powershell
python show.py clock
```

其他常用命令：

```powershell
python show.py stats
python show.py net
python show.py pomodoro -m 25
python show.py text "你好" "副标题"
python push_pixel.py "YG" --scale 9
python oled.py image picture.png
```

只生成 `preview.png`，不上传：

```powershell
python show.py clock --preview
```

默认文字为 `crisp` 硬边风格；`--style soft` 可保留量化的抗锯齿边缘。字体优先使用 Windows 自带字体。

## 字体为什么变清楚

旧版把每个字节中的左右像素放反了，导致相邻像素两两交换。正确格式是**低 4 位放左像素，高 4 位放右像素**：

```python
packed = ((right_pixel // 16) << 4) | (left_pixel // 16)
```

这项修复消除了编码引起的笔画错位。硬边文字是额外的外观调整。完整说明包含原厂代码推导、前后对比图及复现步骤：

- [OLED 字体清晰化修复教程](OLED字体清晰化修复教程.md)
- [简版修复记录](docs/FONT_FIX.md)
- [通信与像素格式](docs/PROTOCOL.md)

## 检查

在仓库根目录运行，无需连接键盘：

```powershell
python -m unittest discover -s tests -v
```

检查覆盖已知像素对、65,536 种灰度组合、奇数列对齐文字，以及时钟双帧分包和重组。完整数据路径测试使用模拟 ACK。

在 Windows 上生成修复对比图：

```powershell
python evidence/font-fix/generate_comparison.py
```

## 使用边界

- 绘图区使用 208×64，每像素 4bit；这些参数针对本机验证的型号和连接方式。
- 当前静态页采用两帧相同画面，一次上传 226 个数据包。
- 键盘未响应时先检查唤醒状态和连接模式；持续上传不能保证唤醒或阻止固件息屏。
- `--wait-link` 尚未在动画上传中完整接入，不能依赖它等待设备恢复。
- 部分历史实验脚本仍有旧参数，日常使用上述入口。详见 [工具说明](tools/README.md)。

## 目录

```text
tools/                  显示程序和诊断工具
tests/                  像素格式与数据路径检查
docs/                   协议和修复说明
evidence/font-fix/      经筛选的对比图、测试记录及复现材料
OLED字体清晰化修复教程.md
requirements.txt
setup.ps1
```

`evidence/font-fix/before-source/tools/` 保存修复前代码，仅用于复现旧问题。原厂反编译文件、工具安装包、设备照片、原始字符串导出和本地交接文档不随仓库上传，仍保留在本机。
