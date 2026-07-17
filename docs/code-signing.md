# Windows 发布包数字签名

发布构建会同时签署内层 `ContractLedgerTool.exe` 和外层
`ContractLedgerTool_OfflineInstaller.exe`。不要在构建完成后只手工签署外层安装器，
否则安装后的应用程序仍会显示未知发布者或被应用控制策略阻止。

## 前置条件

1. 安装 Windows SDK 的 Signing Tools，确保 `signtool.exe` 可用；也可以通过
   `SIGNTOOL_PATH` 指定其绝对路径。
2. 准备带有 Code Signing EKU 和私钥的 RSA 代码签名证书。
3. 内部自签名证书必须由 IT 部署到受管电脑的“受信任的根证书颁发机构”和
   “受信任的发布者”证书库。对外分发应使用公开可信的 OV 代码签名证书。
4. 私钥、PFX 文件和密码不得提交到 Git 仓库，也不得随安装包分发。

## 使用证书库或硬件令牌签名

证书出现在 `Cert:\CurrentUser\My` 或 `Cert:\LocalMachine\My` 后，设置指纹：

```powershell
$env:CODESIGN_CERT_THUMBPRINT = "证书的 SHA-1 指纹"
$env:CODESIGN_TIMESTAMP_URL = "证书服务商提供的 RFC 3161 时间戳地址"
python build_installer.py
```

构建脚本优先从 PATH 查找 SignTool，其次查找 Windows SDK。需要显式指定时：

```powershell
$env:SIGNTOOL_PATH = "C:\Program Files (x86)\Windows Kits\10\bin\<版本>\x64\signtool.exe"
```

## 使用 PFX 签名

仅在组织的证书策略允许导出私钥时使用 PFX：

```powershell
$env:CODESIGN_PFX = "D:\secure\publisher.pfx"
$env:CODESIGN_PFX_PASSWORD = "从安全凭据系统临时注入的密码"
$env:CODESIGN_TIMESTAMP_URL = "证书服务商提供的 RFC 3161 时间戳地址"
python build_installer.py
```

不要把密码写入脚本、配置文件、GitHub Actions YAML 或构建日志。自动化发布应从
GitHub Environments、组织密钥库或硬件签名服务注入凭据。

## 发布验收

构建完成后必须验证最终文件：

```powershell
$exe = "dist\release\ContractLedgerTool_OfflineInstaller.exe"
signtool verify /pa /all /v $exe
Get-AuthenticodeSignature $exe |
    Select-Object Status, StatusMessage, SignerCertificate, TimeStamperCertificate
Get-FileHash $exe -Algorithm SHA256
```

验收条件：

- SignTool 返回退出码 0；
- Authenticode 状态为 `Valid`；
- `TimeStamperCertificate` 不为空；
- 发布的 SHA-256 与构建结束时输出的 `exe_sha256` 完全一致；
- 在一台未安装开发环境的目标 Windows 电脑上安装并运行自检。

签名或时间戳验证失败时，`build_installer.py` 会中止，不会把失败结果当作有效发布包。
