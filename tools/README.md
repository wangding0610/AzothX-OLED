# 工具入口

日常显示使用 `show.py`，先确认键盘已唤醒并处于 2.4G 模式。

| 文件 | 用途 |
|---|---|
| `show.py` | 北京时钟（UTC+8）、CPU/内存、网速、番茄钟、文字、黑屏 |
| `clock_control.ps1` | 通过 Windows 计划任务运行北京时钟；登录启动、退出重启、停止和状态查询 |
| `clock_service.py` | pythonw 无窗口后台；独占锁、时钟子进程管理和日志 |
| `codex_stats.py` | 读取已安装的输入栏统计插件，跟随当前对话显示四项统计；管理时钟、Codex、Claude 三页切换 |
| `claude_status.py` | Claude Code 状态栏包装与钩子（WSL 侧写快照），以及显示端只读的会话读取器 |
| `rocker_switch.py` | 接收拨杆映射的小键盘加减键：上拨时钟，下拨在 Codex 与 Claude 之间轮流 |
| `clock_silent.vbs` | 根目录启动、停止入口共用的无弹窗启动器 |
| `clock_start.cmd` / `clock_stop.cmd` | 命令行备用入口；日常双击使用根目录的 `.vbs` |
| `pages.py` | 208×64 页面绘制 |
| `oled.py` | HID 通信、像素编码、图片上传、设备枚举 |
| `pxfont.py` | 5×7 点阵字体 |
| `push.py` / `push_pixel.py` | 自定义文字 |
| `name.py` | 固定示例名字卡 |
| `make_sheet.py` | 在本地生成页面预览 |
| `generate_doc_previews.py` | 用固定虚构数据生成三张公开预览，并校验像素编码；不读取真实会话或访问键盘 |
| `pair_info.py` / `find_channel.py` / `hid_scan.py` / `link_check.py` | 设备与通道诊断，输出可能包含本机设备标识 |
| `strings_dump.py` / `scan_strings.py` | 分析用户自行提供的本地文件 |

`blink.py`、`recover.py`、`probe.py`、`push1bpp.py`、`matrix.py`、`geo_probe.py`、`mode_probe.py`、`opcode_map.py` 和旧 `stats.py` 是历史实验脚本。部分仍采用 256 像素宽度、不同打包方式或旧工作目录，不能直接当作本机可靠的日常命令。运行前阅读源码。系统参数页面使用 `show.py stats`。

测试和比较图生成脚本不会向硬件上传。其他会发命令的脚本应在检查参数后运行。
