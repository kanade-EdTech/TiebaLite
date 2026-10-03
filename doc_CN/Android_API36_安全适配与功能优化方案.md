# Tieba Lite Android API 36 安全适配与功能优化方案

> 编写日期：2026-10-03  
> 评估基线：`4e96c26ecbdfd81d9ddffba1eb3a3f1d2a455163`  
> 适用范围：Tieba Lite Android 客户端  
> 目标：在控制安全风险和功能回归的前提下，将项目升级到 Android 16（API 36），并改善可维护性、稳定性与用户体验。

## 1. 背景与结论

项目当前使用 `compileSdkVersion 29`、`targetSdkVersion 29`、Android Gradle Plugin 3.5.3、Gradle 5.5 和 Kotlin 1.3.72。当前构建链、依赖和部分 Android 平台调用已明显落后，无法通过仅修改 `targetSdkVersion` 的方式安全升级到 API 36。

截至 2026 年 10 月，Google Play 对手机和平板应用执行以下要求：

- 新应用和应用更新必须以 Android 16（API 36）或更高版本为目标。
- 现有应用至少需要以 Android 15（API 35）为目标，才能继续向较新 Android 设备上的新用户提供。
- API 36 会启用预测性返回、Intent 安全检查、大屏自适应等新行为；此前 Android 12—15 的组件导出、通知权限、后台任务、媒体权限和 Edge-to-Edge 规则也必须同步处理。

官方参考：

- [Google Play 目标 API 要求](https://support.google.com/googleplay/android-developer/answer/11926878?hl=en)
- [Android 16 SDK 配置](https://developer.android.com/about/versions/16/setup-sdk)
- [Android 16 目标行为变更](https://developer.android.com/about/versions/16/behavior-changes-16)

总体结论：当前代码不适合直接切换到 API 36。必须先完成安全止血和构建系统升级，再分阶段提高 Target API，并在每个阶段执行独立回归测试。

## 2. 当前技术基线

### 2.1 构建环境

| 项目 | 当前状态 | 目标状态 |
|---|---:|---:|
| compileSdk | 29 | 36 |
| targetSdk | 29 | 36 |
| minSdk | 21 | 初期保持 21，后续按用户占比评估 |
| Android Gradle Plugin | 3.5.3 | 9.4.x 稳定版 |
| Gradle | 5.5 | 9.6.x |
| JDK | 旧版本兼容模式 | JDK 17 |
| Kotlin | 1.3.72 | 与目标 AGP 兼容的稳定版本 |

相关文件：

- `build.gradle`
- `gradle/wrapper/gradle-wrapper.properties`
- `app/build.gradle`

### 2.2 主要运行时模块

- UI：Activity、Fragment、Adapter、自定义 View。
- API 门面：`ITiebaApi`、`TiebaApi`、`MixedTiebaApiImpl`。
- 网络：Retrofit、OkHttp、MyOkHttp、WebView Cookie。
- 本地存储：LitePal、SharedPreferences、外部缓存文件。
- 后台任务：AlarmManager、BroadcastReceiver、JobService、IntentService。
- Web 内容：WebView、JavaScript 注入、`TiebaLiteJsBridge`。

## 3. 优先安全风险

### 3.1 P0：Cookie 和 BDUSS 写入日志

`LoginActivity` 会输出完整 Cookie 和解析后的 BDUSS。日志可能被调试工具、崩溃收集组件、测试设备或具备相应权限的环境读取。

位置：

- `app/src/main/java/com/huanchengfly/tieba/post/activities/LoginActivity.java:57`
- `app/src/main/java/com/huanchengfly/tieba/post/activities/LoginActivity.java:65`

处理要求：

1. 立即删除 Cookie、BDUSS、STOKEN、请求体和用户隐私数据日志。
2. 建立统一日志封装，Release 构建关闭调试日志。
3. 对必须保留的标识符进行不可逆脱敏，例如仅记录哈希前 8 位。
4. 禁止将凭据写入崩溃报告和分析事件。

### 3.2 P0：认证数据可能经 HTTP 明文发送

`RetrofitTiebaApi` 为多个请求加入 BDUSS、设备信息和签名参数，但部分基础地址仍为 `http://c.tieba.baidu.com/`。全局网络配置同时允许明文流量。

位置：

- `app/src/main/java/com/huanchengfly/tieba/post/api/retrofit/RetrofitTiebaApi.kt:31`
- `app/src/main/java/com/huanchengfly/tieba/post/api/retrofit/RetrofitTiebaApi.kt:50`
- `app/src/main/res/xml/network_security_config.xml:3`

风险：同一网络内的攻击者可能读取或篡改请求，导致账户凭据泄漏、响应数据被替换或用户操作被冒用。

处理要求：

1. 验证所有贴吧端点是否支持 HTTPS。
2. 将可用端点全部切换到 HTTPS。
3. 将 `cleartextTrafficPermitted` 默认值改为 `false`。
4. 如某认证接口只能使用 HTTP，不得继续发送 BDUSS 或其他登录凭据；应停用、替换该能力或改用安全端点。
5. 统一配置连接、读取和写入超时，禁止无限等待。

官方参考：[Android 明文通信风险](https://developer.android.com/privacy-and-security/risks/cleartext-communications)

### 3.3 P0：WebView 原生桥暴露范围过大

当前 WebView 同时启用了：

- JavaScript；
- 文件访问；
- `file://` 跨域访问；
- 混合内容；
- `addJavascriptInterface`；
- Cookie 注入；
- 页面脚本注入。

位置：`app/src/main/java/com/huanchengfly/tieba/post/fragments/WebViewFragment.java:238`

`TiebaLiteJsBridge` 还提供了通用 SharedPreferences 读写能力：

- `app/src/main/java/com/huanchengfly/tieba/post/utils/TiebaLiteJavaScript.java:40`

风险：如果 WebView 打开恶意页面、页面包含不可信 iframe，或 HTTP 响应被篡改，页面脚本可能调用原生桥，在应用权限上下文内读取或修改本地状态。

处理要求：

1. 设置 `setAllowFileAccess(false)`。
2. 设置 `setAllowFileAccessFromFileURLs(false)`。
3. 设置 `setAllowUniversalAccessFromFileURLs(false)`。
4. 使用 `MIXED_CONTENT_NEVER_ALLOW`。
5. 使用 `WebViewAssetLoader` 加载本地资源。
6. 只在经过精确校验的 HTTPS 域名中挂载 JS Bridge。
7. 页面跳转到非白名单域名前调用 `removeJavascriptInterface`。
8. 删除通用 `putString/getString/putInt/getInt`，改成固定功能命令。
9. 对 Bridge 参数进行类型、长度和字符集限制。
10. 普通外链改用 Custom Tabs 或外部浏览器。

官方参考：[WebView Native Bridge 安全风险](https://developer.android.com/privacy-and-security/risks/insecure-webview-native-bridges)

### 3.4 P0：Cookie 注入缺少域名约束

`WebViewFragment.onPageStarted()` 会向当前 URL 写入 BDUSS Cookie，但未在写入前严格限制 scheme 和 host。

位置：`app/src/main/java/com/huanchengfly/tieba/post/fragments/WebViewFragment.java:348`

处理要求：

- 仅允许 `https`。
- host 必须进行精确匹配，例如 `tieba.baidu.com`、`wappass.baidu.com`，不能仅使用 `contains` 或不安全的字符串后缀判断。
- 非白名单页面不得注入 Cookie、脚本或原生桥。
- 重定向后再次执行域名校验。

### 3.5 P1：账户凭据明文持久化且可能进入备份

`Account` 模型直接保存完整 Cookie；Manifest 开启了应用备份，而当前备份规则只排除了 `crash.xml`。

位置：

- `app/src/main/java/com/huanchengfly/tieba/post/models/database/Account.java:15`
- `app/src/main/AndroidManifest.xml:34`
- `app/src/main/res/xml/backup_descriptor.xml`

处理要求：

1. Cookie、BDUSS、STOKEN 与普通账户资料分离存储。
2. 使用 Android Keystore 管理加密密钥，对凭据数据执行 AES-GCM 加密。
3. 凭据不得进入 Auto Backup 或设备迁移备份。
4. 账户退出时清理数据库、WebView Cookie 和内存缓存。
5. 为旧数据库设计一次性迁移：读取旧值、加密写入、验证成功后删除旧字段。

## 4. Android API 分阶段适配

### 4.1 Android 12 / API 31

#### 组件导出

所有包含 Intent Filter 的 Activity、Service 和 Receiver 必须显式设置 `android:exported`。缺失时，应用可能无法安装。

原则：

- Launcher Activity：`android:exported="true"`。
- 必须接收外部深链的 Dispatch Activity：`true`，同时严格验证 URI。
- 仅供应用内部调用的组件：`false`。
- 不需要导出的 Receiver、Service：`false`。

#### PendingIntent 可变性

所有 `PendingIntent` 必须明确指定 `FLAG_IMMUTABLE` 或 `FLAG_MUTABLE`。

需检查：

- `TiebaUtil.kt`
- `BootCompleteSignReceiver.kt`
- `CrashUtil.java`
- `OKSignService.kt`
- `NotifyJobService.kt`

默认写法：

```kotlin
val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
```

只有内容确实需要由系统或其他进程修改时才使用 `FLAG_MUTABLE`。

官方参考：[Android 12 行为变更](https://developer.android.com/about/versions/12/behavior-changes-12)

### 4.2 Android 13 / API 33

#### 通知权限

消息提醒和签到前台通知需要声明并按场景申请 `POST_NOTIFICATIONS`。用户拒绝时，功能应继续安全运行，并在应用内提供状态反馈。

#### 媒体权限

删除对 `READ_EXTERNAL_STORAGE` 和 `WRITE_EXTERNAL_STORAGE` 的长期依赖：

- 用户选图：Photo Picker 或 Storage Access Framework。
- 保存图片：MediaStore。
- 应用私有缓存：`cacheDir` 或 `externalCacheDir`。
- 分享临时文件：FileProvider + 应用专用缓存目录。

如果只是选择图片或视频，应优先使用系统 Photo Picker，而不是申请整个媒体库权限。

官方参考：[Android Photo Picker](https://developer.android.com/training/data-storage/shared/photo-picker)

#### 权限最小化

重新核对并尽量删除：

- `READ_PHONE_STATE`
- `ACCESS_FINE_LOCATION`
- `ACCESS_COARSE_LOCATION`
- 旧存储权限
- 非核心功能使用的设备标识权限

设备标识应改为应用作用域随机 ID，不应依赖 IMEI。

### 4.3 Android 14 / API 34

#### 动态广播接收器

动态注册 Receiver 时必须声明是否对其他应用可见。以下内部广播应使用 `RECEIVER_NOT_EXPORTED`：

- 新消息广播；
- 账户切换广播；
- 回复成功广播。

推荐使用：

```kotlin
ContextCompat.registerReceiver(
    context,
    receiver,
    filter,
    ContextCompat.RECEIVER_NOT_EXPORTED
)
```

需修改：

- `MainActivity.kt`
- `ThreadActivity.kt`
- `FloorActivity.kt`
- `FloorFragment.kt`

#### 前台服务类型

Android 14 要求前台服务声明与实际用途匹配的类型和权限。签到属于短时网络任务，更适合迁移到 WorkManager；不要为了绕过后台限制随意声明不匹配的前台服务类型。

官方参考：[Android 14 行为变更](https://developer.android.com/about/versions/14/behavior-changes-14)

### 4.4 Android 15 / API 35

#### Edge-to-Edge

目标 API 35 后，应用默认采用 Edge-to-Edge。需要统一处理：

- 状态栏 Insets；
- 导航栏 Insets；
- 输入法 Insets；
- 刘海和打孔区域；
- 三键导航与手势导航；
- 横屏、分屏和自由窗口。

建议：

1. 在 Activity 基类中统一启用 Edge-to-Edge。
2. 使用 `WindowInsetsCompat` 分发 Insets。
3. 删除固定状态栏高度和手工偏移逻辑。
4. 检查 Toolbar、BottomNavigationView、FAB、RecyclerView 和 Dialog。

官方参考：[Android 15 行为变更](https://developer.android.com/about/versions/15/behavior-changes-15)

### 4.5 Android 16 / API 36

#### 预测性返回

项目中仍有自定义 `onBackPressed()` 逻辑。应迁移至 AndroidX `OnBackPressedDispatcher`，并逐页确认：

- WebView 返回历史；
- 搜索框关闭；
- Dialog 和抽屉关闭；
- Fragment 返回栈；
- Activity 跨任务返回。

#### 大屏和自适应布局

Android 16 在大屏设备上可能忽略方向、宽高比和可调整尺寸限制。页面不能依赖固定屏幕尺寸。

测试范围：

- 600dp 以上平板；
- 折叠屏展开和折叠状态；
- 横屏；
- 分屏；
- 桌面窗口模式。

#### Intent 安全

- 显式 Intent 应与目标组件 Intent Filter 匹配。
- 外部深链必须校验 scheme、host、path 和业务参数。
- 禁止直接转发外部 Intent 中的嵌套 Intent。
- 调试构建启用 `StrictMode.detectUnsafeIntentLaunch()`。

#### JobScheduler 配额

Android 16 会进一步约束任务运行配额。消息刷新和签到任务不能假设固定时间必然执行，应允许延迟、重试和系统停止。

## 5. 构建系统升级方案

### 5.1 不建议直接从 AGP 3.5 升到 9.4

直接升级会同时触发 DSL、插件、Kotlin、Java、资源处理和依赖兼容问题，难以定位回归来源。

建议拆为两个主要阶段：

#### 阶段 A：AGP 3.5 → AGP 7.4

- 升级 Gradle 和 JDK 到对应兼容版本。
- 移除 `kotlin-android-extensions`，迁移 ViewBinding。
- 清理已废弃的 `jcenter()`。
- 替换或移除不兼容的 AndResGuard、Paranoid 插件。
- 删除固定 `buildToolsVersion`。
- 更新旧 Support Annotations，统一 AndroidX。
- 保持业务行为和 targetSdk 不变。

#### 阶段 B：AGP 7.4 → AGP 9.4

- 使用 JDK 17 和 Gradle 9.6。
- 增加 `namespace`。
- 迁移到现代 Plugins DSL。
- 处理 AGP 9 内置 Kotlin 和新 DSL 行为。
- 启用配置缓存前先处理旧插件。
- 使用版本目录集中管理依赖。

官方参考：

- [Android Gradle Plugin 版本信息](https://developer.android.com/reference/tools/gradle-api)
- [AGP 9 升级说明](https://developer.android.com/build/releases/agp-9-0-0-release-notes)

## 6. 功能与架构优化

### 6.1 统一网络层

当前同时使用 Retrofit、OkHttp、MyOkHttp 和 WebView Cookie，配置和错误处理分散。

建议：

- 只维护一个受控的 OkHttpClient 工厂。
- Retrofit API、图片请求和下载共享统一 TLS、超时和网络策略。
- 更新检查也迁移到 Retrofit，移除 MyOkHttp。
- 使用统一错误类型：网络错误、HTTP 错误、业务错误、登录失效、解析错误。
- GET 请求仅对幂等场景执行有限重试。
- 对 429、5xx 使用带抖动的指数退避。
- 日志拦截器不得输出 Cookie、Authorization、BDUSS、STOKEN 或请求签名。

### 6.2 拆分超大 API 接口

将 `ITiebaApi` 按业务域拆分：

- `AuthApi`
- `ForumApi`
- `ThreadApi`
- `MessageApi`
- `UserApi`
- `MediaApi`
- `UpdateApi`

在兼容期保留原门面，通过适配器逐个迁移调用点，避免一次性修改所有页面。

### 6.3 引入 Repository 与 ViewModel

Activity 和 Fragment 不应直接承担网络调用、数据库访问和错误转换。

推荐分层：

```text
Activity / Fragment
        ↓
ViewModel / UI State
        ↓
Use Case / Repository
        ↓
Remote Data Source + Local Data Source
```

迁移顺序建议从高频页面开始：

1. 首页；
2. 帖子列表；
3. 帖子详情；
4. 消息；
5. 用户中心；
6. 登录和账户管理。

### 6.4 数据存储现代化

- 历史、草稿、屏蔽列表：迁移到 Room。
- 普通设置：迁移到 DataStore。
- Cookie、BDUSS、STOKEN：使用 Android Keystore 加密后单独保存。
- 临时缓存：使用应用缓存目录，并设置大小上限和淘汰策略。
- 所有数据库迁移必须编写自动化迁移测试。

### 6.5 后台任务统一为 WorkManager

将以下逻辑迁移至 WorkManager：

- 消息刷新；
- 每日签到；
- 非即时缓存清理；
- 更新信息刷新。

原则：

- 用户手动触发的签到可立即执行。
- 自动签到采用时间窗口，不保证精确到分钟。
- 网络不可用时等待约束满足。
- 登录失效时停止重试并通知用户。
- 服务端限流时使用指数退避。
- 任务必须幂等，避免重复签到或重复通知。

WorkManager 是 Android 官方推荐的持久后台任务方案：[WorkManager](https://developer.android.com/reference/androidx/work/WorkManager)

### 6.6 用户体验改进

- 使用统一加载、空状态、离线状态和错误状态组件。
- 帖子和楼层列表支持分页状态恢复。
- 网络失败提供明确的重试入口。
- 登录失效只触发一次全局事件，避免多个页面重复弹窗。
- 图片加载增加流量模式和磁盘缓存上限。
- 自动签到和消息提醒提供独立开关、最近执行状态及失败原因。
- 更新检查失败不得阻塞应用启动。

## 7. 建议实施计划

### 里程碑 0：建立基线

- 固定当前可构建提交。
- 记录 APK 大小、冷启动时间、崩溃率和关键页面截图。
- 建立登录、首页、看帖、回复、图片、消息、签到验收清单。
- CI 增加 Debug 构建、Lint 和单元测试。

验收标准：当前功能在 API 29 和 API 36 设备上有可重复的基准结果。

### 里程碑 1：安全止血

- 删除敏感日志。
- 禁止默认明文流量。
- 收紧 WebView 和 JS Bridge。
- 建立 URL 白名单。
- 加密凭据并排除备份。
- 验证所有 API 的 HTTPS 能力。

验收标准：抓包和日志中不存在 Cookie、BDUSS、STOKEN 明文；恶意域名不能调用原生桥。

### 里程碑 2：构建系统现代化

- 完成 AGP 分阶段升级。
- 使用 JDK 17。
- 移除过时插件和仓库。
- 更新核心 AndroidX、Retrofit、OkHttp、Glide 等依赖。
- 开启依赖锁定和版本审查。

验收标准：Debug/Release 构建通过，签名、混淆、资源压缩与安装流程正常。

### 里程碑 3：适配 API 31—34

- 补齐 `android:exported`。
- 修复 PendingIntent flags。
- 完成通知和媒体权限迁移。
- 修复动态 Receiver 注册。
- 后台任务迁移到 WorkManager。

验收标准：API 31、33、34 的安装、通知、分享、选图、签到和消息功能通过。

### 里程碑 4：适配 API 35—36

- 全面适配 Edge-to-Edge。
- 迁移预测性返回。
- 修复大屏和分屏布局。
- 开启 Intent 安全检查。
- 验证 JobScheduler/WorkManager 限制。

验收标准：API 35 和 36 上无系统栏遮挡、返回异常、后台任务崩溃和 Intent 安全错误。

### 里程碑 5：发布准备

- 执行依赖漏洞扫描、Android Lint 和静态安全扫描。
- 检查 Play Data Safety、隐私政策和权限声明。
- 执行覆盖安装及数据库迁移测试。
- 分阶段灰度发布。
- 建立崩溃率、ANR、登录失败率和 API 错误率监控。

## 8. 测试矩阵

| 范围 | 必测项目 |
|---|---|
| 系统版本 | API 21、29、31、33、34、35、36 |
| 安装 | 全新安装、覆盖升级、卸载重装 |
| 账户 | 登录、切换账户、退出、Cookie 过期、数据库迁移 |
| 网络 | Wi-Fi、移动网络、断网、弱网、证书错误、HTTP 重定向 |
| WebView | 登录页、贴吧页、恶意外链、iframe、文件 URL、混合内容 |
| 媒体 | 选图、拍照、上传、保存、分享、权限拒绝 |
| 后台 | 自动签到、消息轮询、重启、低电量、后台限制、强制停止 |
| 通知 | 首次授权、拒绝、撤销、通知渠道关闭 |
| UI | 手势导航、三键导航、横屏、分屏、平板、折叠屏、输入法 |
| 返回 | WebView 历史、Fragment 返回栈、跨 Activity、预测性返回 |
| 稳定性 | 进程重建、旋转、内存压力、重复快速操作 |

## 9. 发布阻断条件

满足任一条件时不得发布：

- 日志、崩溃报告或网络抓包中出现 Cookie、BDUSS、STOKEN。
- 认证请求仍通过 HTTP 明文发送。
- 非白名单网页可以访问 JavaScript Bridge。
- API 31 及以上存在缺少 PendingIntent mutability flag 的调用。
- API 34 及以上动态 Receiver 未声明导出策略。
- API 35 页面被状态栏、导航栏或输入法遮挡。
- API 36 返回手势导致数据丢失、崩溃或导航错误。
- 数据库升级会丢失账户、草稿、历史或屏蔽列表。
- 自动签到或消息任务存在无限重试、重复执行或明显耗电。

## 10. 初步安全评分与最终判定

本评分来自静态代码和配置审查，不等同于完整渗透测试。

| 领域 | 当前评分 |
|---|---:|
| 凭据与密钥管理 | 20/100 |
| 输入、URL 与深链验证 | 40/100 |
| 身份与会话管理 | 35/100 |
| 数据保护 | 30/100 |
| 网络安全 | 20/100 |
| 稳定性与后台任务 | 45/100 |
| 依赖与供应链 | 20/100 |
| 监控与隐私 | 35/100 |

综合安全就绪度约为 **29/100**。

判定：**当前版本不具备直接升级到 API 36 并发布的安全条件**。完成 P0 安全修复、构建链升级、API 分阶段适配以及测试矩阵验收后，才能进入灰度发布阶段。

