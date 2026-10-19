# MouseTranslating

**Windows 端「复制即翻译」桌面工具：在任意软件中复制文字，自动弹出中英互译结果，基于 DeepSeek API，PyQt6 实现。**

A lightweight Windows desktop tool for instant translation on copy — copy text in any app and get the Chinese-English translation in a floating popup, powered by DeepSeek API and built with PyQt6.

## 简介

MouseTranslating 是一个常驻 Windows 托盘的轻量翻译工具。在浏览器、PDF、聊天窗口等任何软件中复制一段文字，它就会在光标附近弹出小窗，调用 DeepSeek 大模型将这段文字在中英文之间互译，译文流式输出，可一键复制。除主功能「复制即翻译」外，还提供实验性的鼠标划词翻译（长按拖动选中后自动取词）。翻译方向由程序自动判断，无需手动切换。

MouseTranslating is a lightweight Windows tray-resident translation tool. Copy text in any application — browser, PDF reader, chat window — and it pops up a small window near your cursor showing the Chinese-English translation from the DeepSeek LLM, streamed in real time and copyable with one click. Alongside the main "copy-to-translate" mode, an experimental mouse-selection translation mode (long-press and drag to capture text) is also included. The translation direction is detected automatically.

## 功能特性

- 复制即翻译：监听系统剪贴板，在任意软件中按 Ctrl+C 后自动翻译，无需切换窗口或按快捷键
- 中英自动互译：按 CJK 字符占比自动判断方向（中文译成英文，英文译成中文），无需手动选择
- 流式输出：调用 DeepSeek API 的 SSE 流式接口，译文逐段显示，弹窗先显示「翻译中…」占位
- 不抢焦点的浮窗：弹窗无边框、置顶、不夺取输入焦点，翻译过程中可以继续打字；按 Esc 或点击弹窗外任意位置关闭
- 智能定位：弹窗优先出现在选区上方（留 8px 间距），空间不足时自动翻到下方并钳制在屏幕工作区内；支持多显示器与不同 DPI 缩放
- 一键复制：译文可复制到剪贴板，复制时自动抑制一次剪贴板监听，防止自己触发自己
- 托盘常驻：托盘图标可开关两种翻译模式、打开主窗口或退出；关闭主窗口等于最小化到托盘，翻译继续生效
- 实验性鼠标划词：长按拖动选中文字后自动取词翻译（默认关闭，可在主窗口或托盘菜单开启）
- 本地缓存：相同文本与方向的翻译结果进入 LRU 缓存（200 条），重复复制不重复请求

## 运行环境

- Windows 10 / 11（x64）
- Python 3.13（开发与验证版本；3.10 及以上理论上可用，未逐一验证）
- 一个 DeepSeek API Key（在 platform.deepseek.com 申请）

## 快速开始

```bash
git clone https://github.com/Wizard0721/MouseTranslating.git
cd MouseTranslating
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy config.example.json config.json
```

然后用文本编辑器打开 config.json，把 api_key 改成自己的 Key（Git Bash 中复制命令用 `cp config.example.json config.json`）。

也可以不创建 config.json，直接启动程序，在主窗口中粘贴 Key 并保存，程序会自动创建配置文件：

```bash
python main.py
```

Windows 下也可以双击 start.bat 启动（无控制台窗口，需先建好 .venv）。

## 配置说明

配置保存在仓库根目录的 config.json（已被 .gitignore 排除，不会提交），字段与默认值如下：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| api_key | "" | DeepSeek API Key，留空时翻译会提示去配置 |
| model | deepseek-flash | 模型名（deepseek-chat 已于 2026-07-24 停用，勿填旧名） |
| max_chars | 5000 | 单次翻译的最大字符数，超出截断 |
| enabled | true | 剪贴板翻译总开关 |
| mouse_trigger | false | 鼠标划词翻译开关（实验性） |
| hold_ms | 200 | 划词判定：按住时长下限（毫秒） |
| drag_px | 12 | 划词判定：最小拖动位移（像素） |

配置文件缺失或损坏时，程序按上表默认值运行，不会崩溃。

## 使用方式

1. 启动后程序驻留托盘，主窗口显示运行状态；
2. 在任意软件中选中文字按 Ctrl+C，光标附近即弹出翻译；
3. 点击「复制译文」把译文写回剪贴板；按 Esc 或点击弹窗外任意位置关闭弹窗；
4. 关闭主窗口不会退出程序（最小化到托盘）；右键托盘图标可退出。

## 项目结构

仓库根目录各文件与文件夹说明如下。

### 根目录文件

- **README.md** — 本文件：项目简介、功能特性、使用与配置说明
- **SPEC.md** — 项目规格说明书（v1.1）：原始需求、开源方案调研（selection-hook、STranslate、pot-app）、技术方案、里程碑与已知风险对策
- **main.py** — 程序入口。设置进程 DPI 感知（PerMonitorV2），创建 Qt 应用、托盘、主窗口与翻译弹窗，并串起两条链路：主功能「剪贴板监听翻译」（Qt 原生 dataChanged 信号加 300ms 防抖）与可选功能「鼠标划词翻译」（pynput 全局监听加触发判定）。翻译在后台线程执行，通过 Qt 信号回到主线程更新界面。附带 --smoke（启动自检）与 --selftest（写剪贴板验证全链路）两个调试参数
- **main_window.py** — 主窗口（PyQt6 QMainWindow）：剪贴板翻译开关、鼠标划词开关、DeepSeek API Key 密码输入框与保存按钮；关闭窗口等于最小化到托盘
- **popup.py** — 翻译结果弹窗（PyQt6 QWidget）：无边框、置顶、不抢焦点；顶部为方向标签与关闭按钮，中部为原文（小字、可选中）与译文（流式追加，超长时内部滚动），底部为复制按钮。窗口几何统一用 Win32 API 以物理像素读写，规避 Qt 逻辑坐标与 DPI 换算问题
- **tray.py** — 系统托盘图标与菜单：打开主窗口、两个翻译开关、退出。图标由代码直接绘制（蓝底白「译」字），不依赖图片文件
- **trigger.py** — 鼠标划词触发判定（可选功能）：基于 pynput 的鼠标事件状态机，左键按下时记录起点与时间，拖动过程累计轨迹，松开时同时满足「按住时长不小于 hold_ms」与「位移不小于 drag_px」才判定为一次有意选区；guard 回调保证鼠标点在弹窗上时不触发取词
- **capture.py** — 划词取词（可选功能）：主路径为模拟 Ctrl+Insert / Ctrl+C 读取剪贴板（读取前保存原剪贴板、读取后恢复，含 I 形光标检查与前台窗口管理员权限检测），兜底路径为 UI Automation 直接读取选区文本与矩形；通过 ctypes 直连 Win32 剪贴板 API
- **locator.py** — 弹窗定位：把选区矩形换算为弹窗物理像素坐标。上方优先（留 8px 间距），上方放不下翻到下方，下方也放不下则贴工作区底边，水平方向钳制在显示器工作区内；按鼠标所在屏幕的 DPI 缩放（GetDpiForMonitor）计算弹窗物理尺寸，支持多显示器不同缩放
- **translator.py** — 翻译核心：调用 DeepSeek API（OpenAI 兼容的 /chat/completions 接口，SSE 流式）。以 CJK 字符占比是否超过 30% 判断翻译方向；系统提示词固定要求只输出译文；相同文本与方向的结果进入 LRU 缓存（200 条）；网络错误、超时与空结果统一封装为 TranslateError
- **config.py** — 配置读写：内置默认值，启动时与 config.json 合并；文件缺失或 JSON 损坏时静默回退默认值
- **config.example.json** — 配置文件模板：api_key 为空字符串，其余为默认值。使用时复制为 config.json 并填入自己的 Key
- **requirements.txt** — Python 依赖清单：pynput（全局键鼠监听）、uiautomation（UI Automation 取词兜底）、PyQt6（界面）、requests（HTTP 调用）
- **start.bat** — Windows 一键启动脚本：以 .venv 中的 pythonw.exe（无控制台窗口）启动 main.py；脚本内使用 %~dp0 相对路径，仓库移动到其他目录后依然可用
- **.gitignore** — 排除清单：虚拟环境、Python 字节码缓存、本地配置 config.json（含 API Key）、运行日志等不入库内容

### 未纳入仓库的本地内容

以下内容只存在于本机开发环境，已被 .gitignore 排除，不会随仓库分发：

- **.venv/** — Python 虚拟环境（第三方依赖安装目录），体积大且与系统相关，不入库
- **__pycache__/** — Python 字节码缓存，由解释器自动生成
- **.workbuddy/** — 本地工具链的项目数据目录
- **config.json** — 本机运行时配置，含真实 API Key；请参照 config.example.json 自行创建
- **translate.log** — 程序运行日志（翻译次数、触发坐标等），由 main.py 自动写入

## 技术栈

- 界面：PyQt6（弹窗、主窗口、托盘）
- 全局监听：pynput（鼠标事件，仅划词功能启用时使用）
- 取词：ctypes 直连 Win32 剪贴板 API，uiautomation（UI Automation）兜底
- 网络：requests（SSE 流式解析）
- 翻译服务：DeepSeek API（deepseek-flash 模型，关闭思考模式）

## 已知限制

- 仅支持 Windows，Linux 与 macOS 不在范围内
- 目前只支持中英互译，其他语种未做
- 不支持 OCR 截图翻译（扫描版 PDF 等场景）
- 以管理员权限运行的前台窗口可能无法划词取词，程序会给出提示
- 鼠标划词为实验性功能，默认关闭；主功能「复制即翻译」不受影响

## 相关文档

技术方案、调研结论与里程碑见 [SPEC.md](SPEC.md)。

## License

暂未声明 License，保留所有权利。作者后续如决定开源，会补充相应协议文件。
