# 合同生成工具

基于模板的合同文档批量生成工具，支持 DOCX 模板制作、字段填充、批量生成、台账管理和付款计划跟踪。

## 功能

- **模板制作** — 上传 DOCX 模板文件，自动检测占位符 `{字段名}`，可视化配置文本、数字、下拉、表格和计算字段
- **采购前置** — 管理采购项目、明细和候选供应商，生成询价函及标准报价模板
- **报价与比价** — 预览确认供应商报价，生成横向比价、异常提示和澄清问题
- **成交转合同** — 确认成交建议，将项目数据预填到现有合同编辑器并建立来源关联
- **合同生成** — 支持当前填写值预览、逐个或批量生成，并自动写入台账
- **台账管理** — 搜索、筛选、状态更新、导出 Excel
- **付款计划** — 自动从合同文本提取付款条款，支持手动确认和编辑
- **PDF 导出** — 通过 Word COM 导出 PDF（需 Microsoft Word）
- **Excel 导出** — 付款计划和台账均可导出
- **版本管理** — 模板修改自动备份历史版本，支持回滚

## 系统要求

- **Python** 3.10+
- **操作系统** Windows 10/11（自启动功能仅 Windows）
- **Microsoft Word** 2013+（可选，用于 PDF 导出）

## 安装

```bash
git clone <仓库地址>
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
3. 导入供应商填写的 `.xlsx`；非标准 Excel、Word 或 PDF 使用「非标准文件映射」。
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
4. **付款跟踪** — 进入合同详情 → 查看/编辑付款计划

### 批量生成

在生成页面，勾选「批量生成」，填写对方单位列表（每行一个），系统将为每个单位生成独立的合同。

## 配置

优先级：环境变量 `CT_*` > `config.json` > 默认值。配置、模板、输出、数据库和 Excel 单据默认值统一保存在运行时目录；测试或便携部署可通过 `CONTRACT_TOOL_RUNTIME_DIR` 指定该目录。

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `CT_HOST` | 127.0.0.1 | 监听地址 |
| `CT_PORT` | 5000 | 监听端口 |
| `CT_DEBUG` | 0 | 调试模式（1/true 开启） |
| `CT_MAX_CONTENT_LENGTH_MB` | 50 | 上传文件大小限制 |
| `CT_CLEANUP_DAYS` | 7 | 文件自动清理天数 |
| `CT_LOG_LEVEL` | INFO | 日志级别 |

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
├── pdf_exporter.py         # PDF 导出
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
70% 生产代码覆盖率、JavaScript 语法检查和 CSS 可重复构建。测试使用隔离的
数据目录，不读写正式合同、台账和配置。

## 安装升级与发布

离线安装器会先保存现有程序文件，暂存并校验新 EXE，然后运行隔离的 HTTP、
SQLite 和 schema 自检。只有自检通过才提交安装；复制、自检或替换失败时会自动
恢复上一版本。`data`、合同文件、模板和备份不属于程序文件回滚范围，不会被覆盖。

发布版本以 `version.txt` 为唯一来源，并在 `CHANGELOG.md` 中保留对应版本记录。
推送匹配版本的标签（例如 `v1.0.0`）后，GitHub Release 工作流会执行完整门禁、
构建唯一离线安装包并发布产物。本地发布验收命令为：

```powershell
python scripts/quality_gate.py release --build-installer
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

## 许可证

本项目采用 [MIT 许可证](LICENSE) 开源。

Copyright (c) 2026 Shao。使用、复制、修改或分发本项目时，必须保留原始著作权声明和许可证文本。
