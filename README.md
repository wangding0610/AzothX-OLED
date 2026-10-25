# AzothX-OLED

**让 ROG 夜魔 X 的 OLED 显示北京时间、Codex 统计和 Claude Code 状态。**

上拨看时间，下拨切换 Codex / Claude。三个页面共用无窗口后台，文字清楚，画面在原位更新。项目包含页面绘制、HID 通信（电脑与键盘传输数据的接口）、连接恢复和像素格式修复，不需要拆机或刷写固件。

| 北京时间 | Codex 统计 | Claude Code 状态 |
|:---:|:---:|:---:|
| ![北京时间软件预览](docs/beijing-clock-preview.png) | ![Codex 统计软件预览](docs/codex-stats-preview.png) | ![Claude 状态软件预览](docs/claude-stats-preview.png) |
| 秒数、日期、星期、分钟刻度 | 轮数、步数、输出速度、累计 tokens | 当前状态、输出速度、上下文、用量额度 |

以上是按设备像素格式解码后的软件预览，全部使用虚构示例数据，不是实物照片。tokens 是模型处理文本的计量单位，`TOK/S` 表示每秒输出的 token 数。

## 当前支持

| 项目 | 范围 |
|---|---|
| 键盘 | 已在一台 ROG Azoth X（夜魔 X）上验证；绘图区为 208×64、16 级灰度 |
| 连接 | USB 有线和 ROG OMNI 2.4G 接收器已验证；蓝牙尚未验证 |
| 系统 | Windows，已验证 Python 3.12；无窗口启动需要同一安装目录下的 `python.exe` 和 `pythonw.exe` |
| 时钟 | 固定北京时间 UTC+8，每秒更新，不修改系统时区 |
| Codex | 额外依赖已安装并启用的 `codex-native-stats` **3.1.1** 插件及 Node.js |
| Claude Code | 已接入 WSL；额外依赖兼容的自定义 `statusline.py`、状态栏命令和钩子配置 |
| 拨杆 | 需在 Gear Link 设置按键映射，并启用本项目的拨杆监听 |

安装本仓库依赖即可使用时钟。Codex 插件、Claude 原始状态栏和个人配置不随仓库分发，AI 页面需要另外接入数据源。

## 快速开始

在 PowerShell 中安装：

```powershell
git clone https://github.com/wangding0610/AzothX-OLED.git
cd AzothX-OLED
python -m pip install -r requirements.txt
```

用 USB 线或 2.4G 接收器连接键盘，确认连接模式正确并按键唤醒。在项目根目录双击 **`启动北京时钟.vbs`**，即可显示北京时间。

首次启动会创建当前用户的 Windows 计划任务 `AzothX-BeijingClock`，启用登录启动和异常恢复。后台使用 `pythonw.exe`，不弹出终端。再次登录后恢复上次选择的页面；电脑关闭、未登录或后台停止时，自定义画面不会继续计时。

| 根目录入口 | 操作 |
|---|---|
| `启动北京时钟.vbs` | 启动后台，切到北京时间 |
| `启动Codex统计.vbs` | 启动后台，切到 Codex；先完成[数据源配置](docs/CODEX_STATS.md) |
| `启动Claude统计.vbs` | 启动后台，切到 Claude；先完成[状态栏接入](docs/CLAUDE_STATS.md) |
| `停止北京时钟.vbs` | **停止整个显示后台**，释放拨杆快捷键，并禁用登录启动和定时恢复 |

三个启动入口复用同一个显示后台。运行日志和页面选择保存在本机 `.runtime/`，该目录已被 Git 忽略。更多启动、停止和恢复说明见[北京时钟文档](docs/BEIJING_CLOCK.md)。

## 用拨杆切换

在 [Gear Link](https://gearlink.asus.com/) 的拨杆设置中启用“自定义”，将上拨绑定为 `Num -`，下拨绑定为 `Num +`。然后按[拨杆配置步骤](docs/ROCKER_SWITCH.md)启用监听并重启显示后台。

| 操作 | 结果 |
|---|---|
| 上拨 | 回到北京时间 |
| 从时钟下拨 | 回到上次使用的 AI 页面，首次默认为 Codex |
| 在 AI 页面下拨 | 在 Codex 与 Claude 之间轮流切换 |

Codex 或 Claude 未打开时，页面显示“未启动”，并保留可用的上次统计。数字小键盘的 `+ / -` 也会触发切换；普通数字行的 `+ / -` 不受影响。

## 其他页面与命令

以下命令均从仓库根目录执行。向键盘上传其他页面前，先双击停止入口，避免后台覆盖画面。

```powershell
python tools/oled.py list                  # 枚举设备
python tools/show.py clock --once          # 上传一次北京时间
python tools/show.py clock                 # 前台持续更新，Ctrl+C 退出
python tools/show.py stats                 # CPU、内存占用与曲线
python tools/show.py net                   # 上传、下载速率
python tools/show.py pomodoro -m 25        # 25 分钟番茄钟
python tools/show.py text "你好" "副标题"   # 自定义文字
python tools/oled.py image picture.png     # 静态图片
```

只生成本地 `preview.png`，不连接键盘：

```powershell
python tools/show.py clock --preview
```

默认文字为 `crisp` 硬边风格，`--style soft` 可保留量化的抗锯齿边缘。字体优先使用 Windows 自带字体。实验脚本的适用范围见[工具入口](tools/README.md)。

## 数据与隐私

| 功能 | 数据来源与网络行为 |
|---|---|
| 时钟、系统状态 | 读取本机时间与系统指标，不需要网络请求 |
| Codex 统计 | 调用已安装插件的统计读取器；插件可能按自身配置查询远程用量元数据，**不能视为完全离线**。Codex 未运行时，只检查本机进程并展示缓存 |
| Claude 显示端 | 只读取本机 `.runtime/claude/` 快照，不主动连接或启动 Claude。适配器会执行用户提供的原状态栏，其行为取决于该脚本 |

屏幕使用统计数字、状态和工具名，不展示提示词或回复正文。本地快照仍可能含会话标识、时间、模型名、路径及用量信息，不应直接公开。`.runtime/`、`.env`、日志、原厂反编译文件、设备原始资料和个人交接文档均不随仓库发布。

本次公开检查和历史范围见[隐私检查记录](docs/PRIVACY.md)。README 中的网络说明描述实际调用边界，不代表对外部插件或自定义状态栏的网络隔离保证。

## 字体为什么变清楚

旧实现把每个字节中的左右像素放反，造成相邻像素两两交换。正确格式是**低 4 位放左像素，高 4 位放右像素**：

```python
packed = ((right_pixel // 16) << 4) | (left_pixel // 16)
```

修正像素顺序消除了编码造成的笔画错位；硬边文字是额外的外观调整。完整推导和复现步骤见[字体清晰化教程](OLED字体清晰化修复教程.md)，通信细节见[协议说明](docs/PROTOCOL.md)。

## 验证与已知限制

在仓库根目录运行，无需连接键盘：

```powershell
python -m unittest discover -s tests -v
python tools/generate_doc_previews.py
```

自动检查覆盖像素顺序、65,536 种灰度组合、北京时间换日、两种连接的数据分包、重绘与恢复、AI 统计解析和页面切换。预览脚本只绘制固定示例并检查编码后的像素，不读取实际会话或上传到键盘。测试与通信确认不能代替实物观察。

- 时钟、Codex、Claude 三页共用实时位图与重绘通道。用户已确认自定义时钟秒数原位更新，无滚动或刷新闪黑；Codex 统计清楚且会更新。
- 电脑必须保持运行，键盘休眠后可能需要按键唤醒；持续上传不能保证阻止固件息屏。
- CPU/内存、网速、番茄钟等额外页面仍沿用动画上传，刷新可能打断显示。长动画和多帧播放时序仍待实物验证。
- 其他键盘型号、蓝牙和 Windows 原生 Claude Code 尚未验证。Codex 桥接固定为插件 3.1.1，升级插件后可能需要适配。
- `--wait-link` 尚未在动画上传中完整接入，不能依靠它等待设备恢复。

## 文档与目录

| 文档 | 内容 |
|---|---|
| [北京时钟](docs/BEIJING_CLOCK.md) | 无窗口启动、计划任务、断线恢复 |
| [Codex 统计](docs/CODEX_STATS.md) | 插件依赖、字段与刷新规则 |
| [Claude 状态](docs/CLAUDE_STATS.md) | 状态栏接口、多会话、等待提醒 |
| [拨杆切换](docs/ROCKER_SWITCH.md) | Gear Link 映射与后台监听 |
| [黑屏修复](docs/BLACK_SCREEN_FIX.md) | 实时位图、重绘与动画通道的区别 |
| [隐私检查](docs/PRIVACY.md) | 脱敏内容、审查范围和历史限制 |

```text
tools/                  显示后台、页面绘制与诊断工具
tests/                  像素、通信、恢复和统计检查
docs/                   使用说明、协议与虚构示例预览
evidence/font-fix/      可复现的字体修复对比及经脱敏的记录
.runtime/               本机配置、快照和日志（不提交）
```

`evidence/font-fix/before-source/` 只用于复现修复前的像素问题，不作为日常运行入口。
