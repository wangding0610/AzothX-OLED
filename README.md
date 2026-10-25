# AzothX-OLED

**ROG 夜魔 X OLED 通信协议逆向与自定义显示工具。**

通过 ROG OMNI 接收器向键盘的小屏上传自定义画面。项目包含主机端通信、208×64 灰度页面绘制、字体毛刺修复和验证工具。

已在一台 ROG Azoth X 的 USB 有线和 2.4G 接收器连接下验证。使用现有显示接口，不需要拆机或刷写键盘固件。

![北京时间时钟模拟预览](docs/beijing-clock-preview.png)

上图为北京时钟的软件解码放大预览，不是实物照片。时钟固定采用北京时间（UTC+8），并沿用此前已由用户确认清楚的像素编码修复。

也支持将 Codex 输入栏中的轮数、步数、最新速度和累计 tokens 实时显示在小屏上。双击 `启动Codex统计.vbs` 切换；双击 `启动北京时钟.vbs` 切回时钟。两个页面共用无窗口后台。详见 [Codex 统计说明](docs/CODEX_STATS.md)。

Claude Code 的状态栏也能显示在小屏上：本轮状态、速度、上下文、5 小时和本周额度，等待权限确认时顶行反色提醒。详见 [Claude 状态说明](docs/CLAUDE_STATS.md)。

本机还可用拨杆切换：进入“自定义”功能后，上拨显示北京时间，下拨在 Codex 与 Claude 之间轮流切换。程序没打开时显示“未启动”，只读本机数据，不联网。配置与使用见 [拨杆切换说明](docs/ROCKER_SWITCH.md)。

## 可以显示什么

| 页面 | 内容 |
|---|---|
| `clock` | 北京时间（UTC+8）、秒数、日期、星期、分钟刻度 |
| `stats` | CPU、内存占用和历史曲线 |
| `net` | 上传、下载速率和曲线 |
| `pomodoro` | 专注倒计时和进度 |
| `text` | 自定义文字和副标题 |
| `blank` | 黑屏画面 |

另有静态图片和点阵文字入口。GIF 载荷构造已有实现，多帧播放时序和较长动画的可靠性仍需实物验证。

## 安装与使用

本机验证环境为 Windows、Python 3.12。安装依赖后，用 USB 线或 2.4G 接收器连接键盘，并按键唤醒。

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

Windows 下也可以在项目根目录双击 `启动北京时钟.vbs`，无终端弹窗地启动后台时钟，默认每秒更新。启动后会在当前用户登录 Windows 时自动运行，时钟进程退出后也会重新启动。时钟采用实时位图与重绘通道，用户已确认秒数在原位更新，没有滚动或刷新闪黑。双击 `停止北京时钟.vbs` 停止更新并禁用登录启动。运行日志保存在本机 `.runtime/`，不提交到 Git。详细用法见 [北京时钟说明](docs/BEIJING_CLOCK.md)。

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

检查覆盖像素格式、65,536 种灰度组合、北京时区与换日、实时位图的单帧分包和重绘、旧动画双帧路径，以及失败处理。数据路径测试使用模拟 ACK，实物显示另由用户确认。

在 Windows 上生成修复对比图：

```powershell
python evidence/font-fix/generate_comparison.py
```

## 使用边界

- 绘图区使用 208×64，每像素 4bit；这些参数针对本机验证的型号和连接方式。
- 默认时钟采用 `0x67` 实时位图通道：一帧 6656 字节，113 个数据包，完成后发送重绘触发命令。其他页面暂沿用 `0x61` 动画路径，双帧 226 个数据包。
- 键盘未响应时先检查唤醒状态和连接模式；持续上传不能保证唤醒或阻止固件息屏。
- 默认页面入口按型号及配对信息识别 Azoth X；接收器未就绪时等待，连接失效后重新识别，不会将笔记本内置 ASUS 键盘误当作 OLED。
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
