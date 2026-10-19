# M0 Lint 门禁恢复与权限边界复核

> 日期：2026-10-19
> 状态：本批通过，严格 Lint 与双 API 页面回归全部成功
> 分支：`codex/m0-baseline`

## 1. 范围与原始问题

针对已确认的 7 个远端 Lint Error：1 个 `MissingPermission`、6 个 `UseRequireInsteadOfGet`。不升级构建工具或 Target API，也不把本批完成视为 M0 全部验收通过。

| 区域 | 原始问题 | 处理 |
|---|---|---|
| `SearchThreadFragment` / `SearchUserFragment` | 可选参数经过两次读取后使用 `!!` | 使用 `arguments?.let`，保留无参数时不覆盖当前关键字的行为 |
| `SettingsFragment` | 检查 `view` 后再次使用 `view!!` | 使用 `view?.let` 获取同一份视图，仅在视图存在时显示 Snackbar |
| `MobileInfoUtil` | SDK 29 将 `getDeviceId()` 标记为需要特权权限 | 保留 Android 10+ 占位值；旧系统增加显式电话权限检查，并将惰性读取策略提取为可单测逻辑 |

设置页两处表达式在远端报告中合计产生四项诊断，因此六项 Fragment Error 对应四处表达式。

## 2. 设备标识边界与兼容注解

- 调用链为 `MobileInfoUtil.getIMEI()` → 贴吧 `_phone_imei` 参数和旧版 CUID 拼装。现有接口格式和占位值 `000000000000000` 保持不变，避免未经账号回归就改变旧版请求身份。
- Android 10 / API 29 及以上提前返回占位值，不获取电话服务、不尝试读取 IMEI。
- API 21—28 只有已经授予 `READ_PHONE_STATE` 时才执行读取，不新增权限申请。Manifest 现有电话权限仍限制在 `maxSdkVersion=28`。
- 权限不足、服务缺失、返回 `null`、权限在检查后被撤销及读取异常，均回退占位值，不将标识写入日志。
- 仍保留方法范围的 `@SuppressLint({"HardwareIds", "MissingPermission"})`：这是 SDK 29 注解对旧系统兼容路径的局部说明，不是全局关闭权限检查。本地试验确认，仅增加 `READ_PHONE_STATE` 检查仍会报需要 `READ_PRIVILEGED_PHONE_STATE`；普通应用不能通过声明特权权限解决此问题。
- 若后续决定完全移除旧系统硬件标识，应单独验证账号、CUID 和设备关联兼容性，再删除旧版读取分支与局部注解。

依据：[Android 10 不可重置标识限制](https://developer.android.com/about/versions/10/privacy/changes#non-resettable-device-ids)、[TelephonyManager API](https://developer.android.com/reference/android/telephony/TelephonyManager#getDeviceId())。

## 3. 007 局部安全复核

本批按 007 自动守护模式仅复核改动组件，不进行整项目安全评分或发布审批。

| 环节 | 结论与证据要求 |
|---|---|
| 攻击面 | 输入为系统版本、权限和电话服务；输出进入旧协议标识字段；测试使用合成值，不接触真实凭据 |
| 威胁模型 | 信息泄露：未授权读取；拒绝服务：缺失参数、视图销毁或服务异常导致崩溃；兼容性：标识变化影响账号设备关联 |
| 技术检查 | 不新增特权权限、敏感日志、网络端点、依赖或数据迁移；不修改现有 CUID 格式 |
| 反向场景 | Android 10+ 即使权限标记为真也不调用读取源；旧版拒绝权限时不调用；检查后撤权时回退 |
| 防护 | 版本与权限双重约束、惰性读取、异常回退、可空 Fragment 状态的单次快照 |
| 判定 | 本地与远端单测、严格 Lint 和双 API 页面回归通过；不据此认定凭据日志、网络或 WebView 安全问题已解决 |

旧系统真实电话服务行为未经过实体设备验证；单测证明策略边界，不替代所有旧设备、运营商和账号兼容性测试。

## 4. 验证与门禁

新增 `MobileInfoUtilTest` 六项测试：

1. API 29 / 30 / 33 / 36 不调用标识读取源，不受普通电话权限布尔值影响。
2. API 21 / 22 / 23 / 28 未授权时不调用读取源。
3. 旧系统已授权时保留合成标识，且只读取一次。
4. 无标识时回退。
5. 读取期间权限撤销时回退。
6. 电话服务异常时回退。

测试使用 JVM 替身模拟系统输入和服务结果，没有读取硬件标识。完整入口仍由 API 29 / API 36 的既有真实页面流程回归；联网搜索、账号操作、旧系统真实电话服务仍不在本批自动化证明范围内。

本地 Lint 已无 Error/Fatal，工作流已移除 `continue-on-error`，任何新的 Lint Error 都将阻断构建作业及设备验证。Warning 继续保留在报告中；未生成排除基线，未修改 `abortOnError`，兼容性抑制仅限第 2 节所述旧版读取方法。

本地执行：`testDebugUnitTest assembleDebug lintDebug --offline --no-daemon --console=plain`，结果 `BUILD SUCCESSFUL in 2m 2s`，37 个任务中 15 个执行、22 个为最新状态。XML 报告为 **0 Error/Fatal、259 Warning**。应用单测 7 项通过（原模板 1 项、新增权限策略 6 项）；UI 辅助测试 12 项通过。

代码提交：`e946acdfa6e50a0e7c955049f5e7f15d66e0d269`，[远端 CI](https://github.com/kanade-EdTech/TiebaLite/actions/runs/39238593167) 的构建作业已成功，`Run required Lint check` 没有允许失败设置。

已下载核验 `m0-reports`：Lint XML 为 **0 Error/Fatal、269 Warning**；单测 HTML 为 7 项测试、0 失败、0 忽略。主机 UI 辅助测试仍为 12 项。远端与本地 Warning 数量分别记录，不混用。

双 API 页面回归已成功，设备证据均已下载核验：API 29 为 7 项通过、1 项通知权限不适用；API 36 拒绝和允许场景各 8 项通过，合计 23 项通过、无失败。两个设备脚本退出码均为 `0`。

热启动进程保持断言通过：API 29 PID `3971`；API 36 拒绝场景 PID `2120`、允许场景 PID `5401`。通知实际状态分别为拒绝 `granted=false` 和允许 `granted=true`，主题与引导完成标记在进程重启后保留。

## 5. 本批判定与剩余边界

本批变更通过验收：版本和权限策略有合成输入单测，编译与严格 Lint 成功，双 API 无账号流程回归通过，未新增权限、敏感日志或依赖。局部兼容注解已公开记录，不能将其理解为完全移除了旧版硬件标识读取。

M0 整体仍未完成：联网搜索、实际登录、账号切换、写操作、旧系统真实电话服务以及完整设置/导航视觉仍需验收。Warning 仍有 269 项；本次局部安全复核不构成整项目安全认证或发布批准。
