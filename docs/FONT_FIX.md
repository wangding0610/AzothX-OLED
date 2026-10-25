# OLED 文字毛刺修复记录

日期：2026-10-22。

完整原理与操作步骤见 [OLED 字体清晰化修复教程](../OLED字体清晰化修复教程.md)。

## 原因

旧版 `tools/oled.py::render_4bpp` 把相邻两个像素装进一个字节时，左右顺序写反了。这会把每行的第 0/1、2/3、4/5 个像素两两交换。斜线和曲线出现梳齿，小字号日期尤其容易变得难以辨认。

原厂代码证据来自本地 `decompiled/GearLink_KBAgent.decompiled.cs`（完整反编译源码不随仓库分发，摘要见 [PROTOCOL.md](PROTOCOL.md)）：

- 第 523–525 行：按当前列、下一列的顺序调用 `MergePixel`。
- 第 776–797 行：分别把两个像素量化到 0..15，最终返回 `IntToBits(num2) + IntToBits(num)`。
- 二进制字符串左侧是高位，因此右像素放高 4 位，左像素放低 4 位。

例如，左白右黑应该编码为 `0x0F`；旧版输出 `0xF0`，设备显示成左黑右白。此前 README、交接文档和逆向报告中的相反结论已更正。

## 修改

1. `tools/oled.py`：纠正 4bpp 像素顺序。所有调用此函数的时钟、文字、图片页面都使用修复后的编码。
2. `tools/pages.py`、`tools/show.py`：默认文字风格改为 `crisp`，文字边缘使用硬边。辅助信息仍可以使用不同亮度；`--style soft` 仍可选。消除像素错位的根本修复是第 1 项。
3. `tools/push_pixel.py`：默认宽度从遗漏的 256 改为本机绘图区宽度 208，避免使用点阵文字命令时再次出现尺寸错配。
4. 文档增加更正说明；增加 `tests/test_pixel_format.py` 防止像素顺序回归。

此次保留原来的 208×64 时钟布局、双帧格式、每包 59 字节、递减包序号和 ACK 等待逻辑。没有操作固件或 ASUS 服务。

## 验证

在仓库根目录运行：

```powershell
python -m unittest discover -s tests -v
```

4 项检查在旧代码上全部失败，修复后全部通过：

- 已知不对称像素对和跨行顺序。
- 穷举 65,536 种 8bit 灰度像素对，与原厂字符串拼接规则比对。
- 从奇数列开始绘制的点阵日期，经编码和按设备格式解码后保持一致。
- 时钟经过真实的双帧封装、59 字节分包、递减包序号，再重组解码，两帧都与目标 4bit 图像一致。该项在内存中模拟 ACK，不代表真实硬件测试。

固定 `2026-10-22 09:14:27` 的时钟样本中，旧编码按设备规则解码后有 1,348 个像素与目标图像不同。只纠正像素顺序、保留原 soft 字体时，差异即归零。最终 crisp 版本的差异也为零。比较图是软件模拟，不是修复后的实物照片。

实际上传：第一次因设备未响应失败，接收器返回 `02 FF AA`。用户确认已唤醒且处于 2.4G 模式后，再运行 `python -u show.py clock --once`，退出码为 0，226/226 个数据包全部 ACK，模式命令和显示命令均未出现 ACK 缺失提示。

实体屏幕的清晰度：用户查看上传后的大数字和右侧日期后，回复“已经清楚了”。这是用户的实物目视确认；本助手的直接验证范围为源代码、像素模拟、测试及上传 ACK。

## 文件与复用

- 修改前源文件备份：`evidence/font-fix/before-source/`。
- 修复前后测试输出：`evidence/font-fix/test-before.txt`、`test-after.txt`。
- 成功上传记录：`evidence/font-fix/hardware-upload-retry.txt`。
- 比较图：`evidence/font-fix/pixel-order-comparison.png`。
- 生成比较图：在项目根目录运行 `python evidence/font-fix/generate_comparison.py`。

显示一次：

```powershell
python tools/show.py clock --once
```

持续更新时间：

```powershell
python tools/show.py clock
```

按 `Ctrl+C` 停止持续更新。运行前确保键盘已唤醒并处于 2.4G 模式；上传不会代替物理按键唤醒。
