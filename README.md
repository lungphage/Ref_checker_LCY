# Ref_checker_LCY

参考文献真实性核验工具。

原作者：李晨宇  
优化：刘梓峰

这个项目提供：

- Windows 桌面版参考文献核验工具
- 批量去重、筛选、排序、导出
- `PyInstaller onedir` 打包流程
- 基于 `onedir` 结果生成单文件 EXE 的流程

## 目录说明

- `ref_checker_windows_v5/`
  主程序源码、Windows 启动脚本、打包脚本
- `single_file_builder/`
  单文件启动器构建器
- `build_single_file.cmd`
  一键生成单文件版 EXE
- `push_to_github.ps1`
  一键同步当前项目到 GitHub 仓库

## 运行源码版

进入：

`ref_checker_windows_v5/`

推荐直接双击：

`RUN_ME_FIRST.cmd`

它会自动检查：

- Python 是否存在
- `tkinter` 是否可用
- 然后启动主程序

如果只想直接启动，也可以双击：

`双击运行.bat`

## 软件使用方法

1. 打开程序后，把参考文献粘贴进左侧输入区。
2. 建议一行一条；如果是一整段带 `[1] [2] [3]` 编号的内容，程序也会自动拆分。
3. 点击“开始核验”。
4. 在右侧查看结果：
   - 状态
   - 相似度
   - 匹配标题
   - 期刊
   - DOI
   - 建议
5. 可按状态筛选、按相似度或编号排序。
6. 可导出全部结果，或只导出当前筛选结果。
7. 双击某条结果，可打开匹配链接或谷歌学术搜索页面。

## 状态说明

- `HIGH`
  标题高度一致，且年份或 DOI 可以互相印证，通常可以认为文献真实存在。
- `MEDIUM`
  找到较接近结果，但建议人工复核作者、年份、期刊或卷期。
- `LOW`
  只找到相似文献，不建议直接引用。
- `NOT_FOUND`
  没有找到可靠匹配，建议继续人工检索。

## 批量功能

当前版本支持：

- 重复参考文献自动复用结果
- 网络失败提示
- 结果统计卡片
- 按状态筛选
- 按相似度或编号排序
- 导出 CSV / Excel

## 打包 onedir 版

进入：

`ref_checker_windows_v5/`

运行：

`打包成EXE.cmd`

默认使用 `PyInstaller --onedir`。

优点：

- 主 EXE 更小
- 更稳定
- 更适合后续生成单文件版

输出位置：

`ref_checker_windows_v5/dist/ReferenceChecker/`

主程序：

`ref_checker_windows_v5/dist/ReferenceChecker/ReferenceChecker.exe`

## 生成单文件版 EXE

前提：

先成功生成 `onedir` 版，也就是先完成上一步。

然后在仓库根目录运行：

`build_single_file.cmd`

这个流程会：

1. 把 `dist/ReferenceChecker` 打包成 `payload.zip`
2. 用 `single_file_builder/Program.cs` 编译单文件启动器
3. 生成最终单文件版 EXE

输出位置：

`ref_checker_windows_v5/dist_single/ReferenceChecker.SingleFile.exe`

说明：

- 单文件版首次运行时，会自动解压到：
  `%LOCALAPPDATA%\ReferenceCheckerSingleFile\...`
- 然后启动真正的主程序

## 生成 macOS 单文件版

### 方案 1：GitHub Actions 自动构建

仓库已经包含工作流：

`/.github/workflows/build-macos-single-file.yml`

它会在 GitHub 的 macOS runner 上：

1. 安装 Python 3.13
2. 安装 PyInstaller
3. 构建 macOS `--onefile` 版本
4. 上传构建产物

触发方式：

- 向 `main` 分支推送与 macOS 构建相关的文件更新
- 或在 GitHub 仓库的 `Actions` 页面手动运行 `Build macOS Single File`

产物位置：

- GitHub 仓库 `Actions` 页面
- 对应 workflow run 的 `Artifacts` 区域

产物内容包括：

- `ReferenceChecker`
  macOS 单文件可执行文件
- `ReferenceChecker.app.zip`
  macOS app bundle 压缩包
- `README_使用说明.txt`

### 方案 2：在 Mac 本机本地构建

进入：

`ref_checker_windows_v5/`

运行：

```bash
chmod +x build_macos_onefile.sh
./build_macos_onefile.sh
```

输出位置：

- `dist/ReferenceChecker`
- `dist/ReferenceChecker.app`

说明：

- `PyInstaller` 官方建议不同操作系统分别在对应平台上构建
- 也就是说，macOS 版本应当在 macOS 环境中构建，而不是在 Windows 上交叉打包
- GitHub Actions 里的 macOS runner 正是为此准备的

## 推荐 Python 版本

建议使用稳定版：

- Python 3.13 x64
- 或 Python 3.12 x64
- 或 Python 3.14 x64

不建议使用：

- Python 3.15 alpha/beta

因为预发布版本容易导致 PyInstaller 兼容问题。

## 更新后推送到 GitHub

在仓库根目录运行：

`powershell -ExecutionPolicy Bypass -File .\push_to_github.ps1`

如果想自定义提交信息：

```powershell
powershell -ExecutionPolicy Bypass -File .\push_to_github.ps1 -CommitMessage "your message"
```

这个脚本会：

1. 把当前工作目录内容同步到本地 Git 仓库副本
2. 自动 `git add`
3. 自动提交
4. 自动推送到：

`https://github.com/lungphage/Ref_checker_LCY`

## 常见问题

### 1. 打包时报 `pkg_resources` 错误

通常是旧版 PyInstaller 和新版 `setuptools` 的兼容问题。

项目里的 `打包成EXE.cmd` 已经尽量自动处理这类依赖问题。

### 2. 打包时报 `imp` 错误

通常说明你在用过新的 Python 版本，比如 `3.15 alpha`。

请切换到稳定版 Python 3.12 / 3.13 / 3.14。

### 3. 双击程序没反应

先运行：

`环境检查.cmd`

如果还有问题，把：

- 黑窗口报错截图
- `debug_log.txt`

一起提供出来排查。
