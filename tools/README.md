# 工具入口

日常显示使用 `show.py`，先确认键盘已唤醒并处于 2.4G 模式。

| 文件 | 用途 |
|---|---|
| `show.py` | 时钟、CPU/内存、网速、番茄钟、文字、黑屏 |
| `pages.py` | 208×64 页面绘制 |
| `oled.py` | HID 通信、像素编码、图片上传、设备枚举 |
| `pxfont.py` | 5×7 点阵字体 |
| `push.py` / `push_pixel.py` | 自定义文字 |
| `name.py` | 固定示例名字卡 |
| `make_sheet.py` | 在本地生成页面预览 |
| `pair_info.py` / `find_channel.py` / `hid_scan.py` / `link_check.py` | 设备与通道诊断，输出可能包含本机设备标识 |
| `strings_dump.py` / `scan_strings.py` | 分析用户自行提供的本地文件 |

`blink.py`、`recover.py`、`probe.py`、`push1bpp.py`、`matrix.py`、`geo_probe.py`、`mode_probe.py`、`opcode_map.py` 和旧 `stats.py` 是历史实验脚本。部分仍采用 256 像素宽度、不同打包方式或旧工作目录，不能直接当作本机可靠的日常命令。运行前阅读源码。系统参数页面使用 `show.py stats`。

测试和比较图生成脚本不会向硬件上传。其他会发命令的脚本应在检查参数后运行。
