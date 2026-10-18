# M0 无账号 UI 自动化验收

> 更新日期：2026-10-18
> 状态：双 API 离线页面验收通过（本批限定范围）
> 验证提交：`76c90383adc922f595ee71f2e0550a3283c9e387`
> 工作分支：`codex/m0-baseline`

## 1. 验收范围

测试使用真实 APK、系统权限弹窗和页面控件；在临时模拟器中关闭 Wi-Fi 和移动数据，只验证本地流程，不注入已登录账号，不提交登录凭据或执行发帖、回复、签到。

| 检查 | 验证依据 | API 29 | API 36 |
|---|---|---|---|
| 首次冷启动 | 欢迎页控件与截图 | 通过 | 两场景通过 |
| 通知允许 / 拒绝 | 点击系统弹窗，核对实际运行时授权状态 | 不适用 | 拒绝为 `false`、允许为 `true`，均通过 |
| 引导页系统返回 | 进入习惯设置，按系统返回，回到欢迎页 | 通过 | 两场景通过 |
| 日间主题选择 | 点击“少女粉”，核对保存值 `pink` 与截图 | 通过 | 两场景通过 |
| 夜间主题选择 | 点击“静谧蓝”，核对保存值 `dark` 与截图 | 通过 | 两场景通过 |
| 完成全部引导 | 显示完成页，完成后进入登录 Activity，`first=false` | 通过 | 两场景通过 |
| 热启动 | 回到桌面后从启动入口恢复，进程 PID 保持，回到登录 Activity | 通过 | 两场景通过 |
| 进程重启后保留设置 | 强制停止后重开，不重做引导，主题仍为 `dark` | 通过 | 两场景通过 |

流程结束于登录入口，不将登录页面能够打开视为登录成功。系统手势返回、横竖屏、跟随系统夜间模式、全部主题的视觉效果、账号迁移与覆盖安装不在本批范围内。

## 2. 执行与保护

- 入口：`.github/scripts/m0-device-smoke.sh`；页面流程：`.github/scripts/m0-ui-flows.py`。
- GitHub Actions 构建作业先运行 12 项辅助测试，APK 构建成功后进入 API 29 / API 36 设备矩阵。
- 页面脚本依赖 Python 标准库和 Android SDK 自带的 ADB / UI Automator 命令，无新增应用依赖，也不修改应用业务代码。
- 每个场景以卸载重装开始，隔离设置与权限选择。执行前必须同时满足 `GITHUB_ACTIONS=true`、显式 `emulator-*` 序列号、设备仿真标记及目标 API 匹配；不允许直接用于个人手机。
- 控件点击位置来自实时 UI XML 的资源 ID、文本和边界，不固定屏幕坐标。
- ADB 命令、页面等待和整段流程均有限时。失败会生成非零退出码，并尽力保留当前 UI、Activity 和 Logcat。
- APK 安装只对超时额外重试一次；明确的安装错误直接失败。移除重复的预安装步骤，各场景自行安装同一 APK。
- 模拟器使用 `-gpu swiftshader -feature -Vulkan`。旧的 `swiftshader_indirect` 已弃用；关闭 Vulkan 是针对图形问题的测试环境调整，参考 [Android 软件渲染说明](https://developer.android.com/studio/run/emulator-acceleration) 和 [模拟器故障排查](https://developer.android.com/studio/run/emulator-troubleshooting)。

## 3. 证据与结果

设备产物沿用 `m0-device-evidence-api-29` / `m0-device-evidence-api-36`，新增内容位于 `flows/`：

- `results.json`：每项检查的场景、状态和必要的断言结果。
- `legacy/`：API 29 场景；通知运行时选择记录为 `not-applicable`。
- `deny/`、`allow/`：API 36 的拒绝与允许场景，均需真实点击系统通知弹窗。
- 各场景包含欢迎页、主题选择、引导完成的截图与 UI XML。登录入口、热启动和进程重启采用 Activity 断言及截图，不等待外部登录网页的 UI 闲置状态；另保存最终 Activity / Logcat。

本地辅助测试命令：

```text
python -B -m unittest discover -s .github/scripts -p test_m0_ui_flows.py -v
```

本地结果：12 项通过；Bash 与工作流 YAML 语法检查通过。辅助测试验证控件定位、权限解析、安装重试边界和设备重置保护，不替代设备功能验收。尚未采集应用代码行覆盖率或分支覆盖率，本批也不据此声称业务覆盖率达标。

## 4. 远端执行记录

- 首轮提交 `f18cf780`：[运行记录](https://github.com/kanade-EdTech/TiebaLite/actions/runs/39119671924)。构建通过；API 29 在预安装时超时，尚未运行 UI 流程。API 36 已通过冷启动、通知拒绝、引导页系统返回、日间主题和夜间主题五项检查，随后在登录页附近发生 UI 取证超时及模拟器断开，允许场景因此未完成。
- 日志中出现 `bad color buffer handle`；API 29 的 Logcat 同时存在 Google 服务后台初始化和网络超时。上述现象用于指导测试环境隔离，不据此断言已找到唯一根因，也不归类为 API 迁移回归。
- 调整提交 `76c90383`：关闭模拟器网络，采用当前软件渲染及禁用 Vulkan，减少重复安装并增加一次安装超时重试，登录入口使用 Activity 状态验证。[第二轮运行](https://github.com/kanade-EdTech/TiebaLite/actions/runs/39126115424) 整体成功，构建、API 29 和 API 36 三个作业均通过。

## 5. 验证结论

| 层级 / 场景 | 通过 | 失败 | 不适用 | 证据 |
|---|---:|---:|---:|---|
| 主机辅助测试 | 12 | 0 | 0 | 本地与 CI 的单元测试输出 |
| API 29 `legacy` | 7 | 0 | 1 | `m0-device-evidence-api-29/flows/results.json` |
| API 36 `deny` | 8 | 0 | 0 | `m0-device-evidence-api-36/flows/results.json` |
| API 36 `allow` | 8 | 0 | 0 | 同上，独立全新安装场景 |

两份设备产物均已下载核验，设备脚本退出码均为 `0`。热启动 PID：API 29 为 `3875`，API 36 拒绝场景为 `2204`、允许场景为 `5469`；各场景回到前台后 PID 保持不变。进程重启后首次引导标记与夜间主题仍保留。

已查看 API 29 的日间主题、API 36 的夜间主题和拒绝通知后的热启动截图，主题选择标记与页面外观符合相应预设。离线登录入口只显示应用登录页面框架，未验证百度网页内容、联网加载或账号认证。

最新 Lint 产物仍为 7 Error、269 Warning；CI 的允许失败策略继续保留。本批按 Quinn 的要求区分真实页面断言、辅助测试和未覆盖业务，不使用代码行覆盖率代替验收结论。

本批无需账号的启动与权限验收完成。M0 整体仍需联网与账号相关流程留证，以及验收签字。
