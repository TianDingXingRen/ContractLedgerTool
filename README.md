# 合同生成工具

基于模板的合同文档批量生成工具，支持 DOCX 模板制作、字段填充、批量生成、台账管理和付款计划跟踪。

## 功能

- **模板制作** — 上传 DOCX 模板文件，自动检测占位符 `{字段名}`，可视化配置字段类型（文本/下拉/表格/计算）
- **合同生成** — 逐个或批量生成合同，自动写入台账
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

1. **编制模板** — 点击「新建模板」→ 上传 DOCX 参考文件 → 配置字段 → 保存
2. **生成合同** — 选择模板 → 填写字段值 → 点击「生成合同」
3. **管理台账** — 在「合同台账」查看/搜索/更新合同
4. **付款跟踪** — 进入合同详情 → 查看/编辑付款计划

### 批量生成

在生成页面，勾选「批量生成」，填写对方单位列表（每行一个），系统将为每个单位生成独立的合同。

## 配置

优先级：`config.json` > 环境变量 `CT_*` > 默认值

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
├── docx_builder.py         # DOCX 文档写入
├── template_def.py         # 模板定义管理
├── field_eval.py           # 公式安全求值
├── ledger_store.py         # SQLite 台账存取
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

## 安全

- CSRF 保护（所有 POST 请求）
- 路径遍历防护
- 公式安全求值（AST 白名单）
- 输入长度和类型校验
- 内存速率限制
- Session SameSite=Strict

## 许可证

内部使用
