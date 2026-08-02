# 合同生成工具

[![CI](https://github.com/TianDingXingRen/ContractLedgerTool/actions/workflows/ci.yml/badge.svg)](https://github.com/TianDingXingRen/ContractLedgerTool/actions/workflows/ci.yml)
[![CodeQL](https://github.com/TianDingXingRen/ContractLedgerTool/actions/workflows/codeql.yml/badge.svg)](https://github.com/TianDingXingRen/ContractLedgerTool/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

基于模板的合同文档批量生成工具，支持 DOCX 模板制作、字段填充、批量生成、台账管理和付款计划跟踪。

## 功能

- **模板制作** — 上传 DOCX 模板文件，自动检测占位符 `{字段名}`，可视化配置文本、数字、下拉、表格和计算字段
- **采购前置** — 管理采购项目、明细和候选供应商，生成询价函及标准报价模板
- **报价与比价** — 预览确认供应商报价，支持导入后编辑、删除并重新比价，生成异常提示和澄清问题
- **成交转合同** — 确认成交建议，将项目数据预填到现有合同编辑器并建立来源关联
- **合同生成** — 支持当前填写值预览、逐个或批量生成，并自动写入台账
- **外部合同导入** — 将他人编写完成的单份 DOCX 离线识别、人工复核后写入合同台账
- **台账管理** — 搜索、筛选、状态更新、导出 Excel
- **付款计划** — 完全离线、基于规则抽取付款条款，支持人工确认、合同内编号归集和月度付款计划导出
- **投产通知** — 维护合同产品与号段，登记、修订和统计每次投产通知，并按通知金额触发付款计划
- **发票管理** — 维护发票、附件、核验/作废/红冲状态，并分摊到合同、投产通知和付款计划
- **旧版 Word 导入** — 支持 `.docx`，并可通过本机 Word/WPS 将 `.doc` 安全转换为 `.docx`
- **Excel 导出** — 付款计划和台账均可导出
- **版本管理** — 模板修改自动备份历史版本，支持回滚

## 系统要求

- **Python** 3.10+
- **操作系统** Windows 10/11（自启动功能仅 Windows）
- **Microsoft Word 或 WPS**（可选，仅用于把旧版 `.doc` 模板转换为 `.docx`）

## 安装

### 离线安装包（推荐）

下载并双击 `ContractLedgerTool_OfflineInstaller.exe`。安装包不需要 Python 或网络，会先显示安装路径，
默认安装到 `%LOCALAPPDATA%\Programs\ContractLedgerTool`，且不允许安装到桌面。桌面只创建快捷方式；
安装、启动和日常运行均不显示 CMD 或 PowerShell 黑色窗口。安装完成后直接在浏览器访问
`http://127.0.0.1:5000/`。服务默认在登录 Windows 后
静默自启动；若 5000 端口已占用，安装程序会自动选择后续可用端口。若不需要开机自启动，可运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1 -NoAutostart
```

可在 Windows“设置 → 应用 → 已安装的应用”中卸载。普通卸载保留合同、台账、模板、配置和备份；
彻底删除前请先备份数据，再运行安装目录中的 `uninstall.ps1 -RemoveData`。

### 从源码运行

```bash
git clone https://github.com/TianDingXingRen/ContractLedgerTool.git
cd 合同生成工具
pip install -r requirements.txt
```

## 启动

```bash
python app.py
```

启动后自动打开浏览器访问 `http://127.0.0.1:5000/`。

- 手动模式：`python app.py`
- 静默模式（不打开浏览器）：`python app.py --no-browser`
- 自定义端口：`python app.py --port 8080`

## 使用流程

### 采购前置闭环

1. 进入「采购前置」，新建采购项目并录入采购明细。
2. 添加候选供应商，为每家供应商下载标准报价模板。
3. 导入供应商填写的 `.xlsx`；非标准 Excel、Word 或 PDF 使用「非标准文件映射」。已确认报价可在项目详情中编辑或删除；已用于成交建议的报价会锁定以保证可追溯。
4. 执行横向比价，查看漏项、高低价和商务/技术偏离，生成澄清问题。
5. 确认成交建议，选择合同模板并进入预填后的合同编辑器。
6. 复核后生成合同，系统自动关联采购项目、成交建议和合同台账。

其他采购能力：

- 采购明细支持 Excel 复制粘贴、上传和导出。
- 支持多轮报价、降价幅度、谈判记录、谈判纪要和最终承诺表。
- 成交建议支持整包成交或按采购明细拆分给多家供应商。
- 历史价格页面提供最低价、中位价、建议目标价和谈判策略初稿。
- 成交后可输出 ERP/OA 填报摘要和项目完整归档包。

文本型 PDF 可直接识别表格。扫描 PDF OCR 需要安装 Tesseract 中文语言包；如未加入系统 PATH，可设置：

```powershell
$env:CT_TESSERACT_CMD = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
```

### 合同生成

1. **编制模板** — 点击「新建模板」→ 上传 DOCX 参考文件 → 配置字段 → 保存
2. **生成合同** — 选择模板 → 填写字段值 → 点击「生成合同」
3. **管理台账** — 在「合同台账」查看/搜索/更新合同
4. **付款跟踪** — 进入合同详情 → 付款管理 → 同步合同号段并维护逐编号金额 → 为付款计划选择合同内编号

### 月度付款计划导出

1. 在合同详情「付款管理」中同步合同号段，并维护每个合同内编号的“本编号金额”。
2. 新增或编辑付款计划时选择对应合同内编号；“待补编号”的历史计划也会导出，便于补充和复核。
3. 进入全局「付款计划」，选择报表月份并点击「导出付款计划」。
4. 工作簿按项目生成明细页，按“项目名称 + 合同内编号”成行并横向展开全部付款节点；所选月份仍未付的节点和应付汇总框以黄色标识。汇总页分别统计所选月份计划、以前月份未付余额和银行承兑金额。

编号台账和月度报表只读取合同与付款计划数据，不读取或关联投产通知。

### 批量生成

在生成页面，勾选「批量生成」，填写对方单位列表（每行一个），系统将为每个单位生成独立的合同。

### 导入外部合同

1. 在「合同台账」点击「导入合同」，上传一份 `.docx` 合同。
2. 系统在本机离线识别合同编号、名称、对方单位、金额、签订/到期日期，并展示识别依据和置信度；无法识别名称时使用文件名，合同编号不会被臆造。
3. 人工复核台账字段、状态、项目分类和付款计划。状态默认「草稿」，付款计划默认「待确认 / 未付款」，可编辑或取消勾选误识别条目。
4. 点击「确认导入」后，合同文件、台账记录和付款计划作为一个业务操作写入；列表和详情会显示「外部导入」及原文件名。

当前仅支持一次导入一份标准 DOCX，不支持旧版 DOC、PDF、加密或损坏的 Office 文件。上传文件会校验扩展名、Office ZIP 结构、内部路径、成员数量、解压体积和压缩比；正式下载返回上传 DOCX 的原始字节。

完全相同的文件按 SHA-256 摘要判重，非空合同编号按台账唯一规则判重；回收站中的记录同样参与判断。重复导入会被阻止并提供已有合同链接。暂存文件与当前浏览器会话绑定，取消、解析失败或会话过期后会自动清理，已入账文件由台账引用保护。

### 付款规则、投产通知与发票

1. 在合同详情的付款计划区域复核系统离线抽取出的付款规则；无法唯一判断的条款会标记为待人工确认。
2. 对“每次投产通知支付通知内产品总价一定比例”的条款，确认其规则类型、比例和计算基数为“投产通知总额”。
3. 进入「合同产品」维护产品、合同数量、单价以及可选的合同起止号段。
4. 进入「投产通知」新建通知，选择产品、填写本次数量和号段；发出通知后系统累计已发数量，并生成对应付款计划。
5. 进入「发票管理」登记发票，可上传附件，并把金额分摊到合同、投产通知或付款计划；核验通过的发票必须全额分摊。
6. 发票作废或全额红冲后不再占用通知和付款计划额度。已发生付款或仍有有效发票分摊的投产通知不能直接取消或修订。

## 配置

优先级：环境变量 `CT_*` > `config.json` > 默认值。配置、模板、输出、数据库和 Excel 单据默认值统一保存在运行时目录；测试或便携部署可通过 `CONTRACT_TOOL_RUNTIME_DIR` 指定该目录。

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `CT_HOST` | 127.0.0.1 | 监听地址 |
| `CT_PORT` | 5000 | 监听端口 |
| `CT_DEBUG` | 0 | 调试模式（1/true 开启） |
| `CT_ALLOW_REMOTE` | 0 | 是否允许非本机访问；启用时必须同时配置访问令牌和 TLS |
| `CT_REMOTE_ACCESS_TOKEN` | 空 | 局域网访问密码，至少16位；仅从环境变量读取 |
| `CT_REMOTE_TLS_CERT` | 空 | 局域网 HTTPS 证书文件路径；仅从环境变量读取 |
| `CT_REMOTE_TLS_KEY` | 空 | 局域网 HTTPS 私钥文件路径；仅从环境变量读取 |
| `CT_TRUSTED_HOSTS` | 本机地址 | 允许的 HTTP Host，多个值使用逗号分隔 |
| `CT_MAX_CONTENT_LENGTH_MB` | 50 | 上传文件大小限制 |
| `CT_CLEANUP_DAYS` | 7 | 文件自动清理天数 |
| `CT_LOG_LEVEL` | INFO | 日志级别 |

默认只允许本机访问。如确需局域网访问，请同时设置 `CT_ALLOW_REMOTE=1`、监听地址、至少16位的 `CT_REMOTE_ACCESS_TOKEN`、`CT_REMOTE_TLS_CERT`、`CT_REMOTE_TLS_KEY`，并把实际访问域名或 IP 加入 `CT_TRUSTED_HOSTS`。局域网模式禁止调试和明文 HTTP；浏览器弹出登录框时可使用任意用户名，并把令牌作为密码。

## 目录结构

```
合同生成工具/
├── app.py                  # Flask 主程序
├── config.py               # 配置管理
├── runtime_paths.py         # 统一运行时目录
├── docx_builder.py         # DOCX 文档写入
├── template_def.py         # 模板定义管理
├── field_eval.py           # 公式安全求值
├── ledger_store/           # SQLite 台账存取与迁移
├── procurement_store/      # 采购项目、报价、比价、澄清和成交数据
├── services/               # 采购业务服务、报价解析和合同数据映射
├── payment_extractor.py    # 付款条款提取
├── xlsx_exporter.py        # Excel 导出
├── routes/                 # 路由蓝图
├── utils/                  # 工具模块
│   ├── helpers.py          # 会话、路径、自启动
│   ├── field_utils.py      # 字段解析、标记检测
│   ├── generation_utils.py # 合同生成、批量处理
│   ├── labels.py           # 状态标签常量
│   ├── security.py         # 安全校验
│   ├── logger.py           # 日志
│   └── errors.py           # 错误响应
├── templates/              # Jinja2 HTML 模板 + 合同模板
├── static/                 # 前端静态资源
├── data/                   # 数据库和备份
├── scripts/                # 辅助脚本
└── requirements.txt        # 依赖
```

## 测试

```powershell
python -m pip install -r requirements-dev.lock
python scripts/quality_gate.py commit
python scripts/quality_gate.py ci
```

`commit` 门禁运行架构预算、Ruff 和 fast 测试；`ci` 额外运行完整测试、
72% 生产代码覆盖率、关键模块单独覆盖率、JavaScript 语法检查和 CSS 可重复构建。测试使用隔离的
数据目录，不读写正式合同、台账和配置。

## 安装升级与发布

离线安装器会先保存现有程序文件，暂存并校验新 EXE，然后运行隔离的 HTTP、
SQLite 和 schema 自检。只有自检通过才提交安装；复制、自检或替换失败时会自动
恢复上一版本。`data`、合同文件、模板和备份不属于程序文件回滚范围，不会被覆盖。

发布版本以 `version.txt` 为唯一来源，并在 `CHANGELOG.md` 中保留对应版本记录。
推送匹配版本的标签（例如 `v1.0.0`）后，GitHub Release 工作流会执行完整门禁、
构建唯一离线安装包并发布产物。正式发布必须配置代码签名证书，且内层应用和外层安装器都必须
具有有效、带可信时间戳的 Authenticode 签名。本地发布验收命令为：

```powershell
python scripts/quality_gate.py release --build-installer
```

每个 GitHub Release 同时提供 `SHA256SUMS`、CycloneDX SBOM 和 GitHub 构建来源证明。下载后可验证：

```powershell
(Get-FileHash -Algorithm SHA256 .\ContractLedgerTool_OfflineInstaller.exe).Hash
gh attestation verify .\ContractLedgerTool_OfflineInstaller.exe -R TianDingXingRen/ContractLedgerTool
```

## 前端样式开发

运行版使用已经编译好的 `static/css/app.min.css`，不在浏览器中执行 Tailwind 编译。修改模板中的 Tailwind/DaisyUI 类名后，需要重新生成并提交 CSS：

```powershell
npm install
npm run build:css
```

Node.js 只用于开发和发布构建；安装后的合同工具不依赖 Node.js。

## 安全

- CSRF 保护（所有 POST 请求）
- 路径遍历防护
- 公式安全求值（AST 白名单）
- 输入长度和类型校验
- 内存速率限制
- Session SameSite=Strict

未修复的安全漏洞请不要提交公开 Issue；请按 [安全策略](SECURITY.md) 使用 GitHub 私密漏洞报告。参与开发、测试和提交 Pull Request 的流程见 [贡献指南](CONTRIBUTING.md)。

## 许可证

本项目采用 [MIT 许可证](LICENSE) 开源。

Copyright (c) 2026 Shao。使用、复制、修改或分发本项目时，必须保留原始著作权声明和许可证文本。
