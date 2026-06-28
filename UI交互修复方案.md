# 合同生成工具 — UI 交互修复方案

> 基于 2026-06-24 UI交互分析报告，按优先级逐项修复。所有修改已通过现有测试套件验证（27/27 passed）。

---

## P0 — 严重问题（已修复 ✓）

### 1. 修复 base.html 双重 `<body>` 及内联样式

**问题描述**：
- `<body class="min-h-screen bg-base-200">` 出现在 `</head>` 之前，随后又有第二个 `<body>` 标签
- 45 行内联 CSS 与 `style.css` 职责不清，维护困难

**修复内容**：
| 文件 | 变更 |
|------|------|
| `templates/base.html` | 移除内联 `<style>` 块和重复 `<body>`，HTML 结构标准化为 `<!DOCTYPE> → <html> → <head> → </head> → <body> → </body>` |
| `static/style.css` | 将原内联布局样式迁移至文件头部（`:root` 变量、`.sp/.ma/.tf` 等固定布局规则），统一管理 |

---

## P1 — 高优先级（已修复 ✓）

### 2. 添加键盘快捷键

**问题描述**：无 `Ctrl+S` 保存、无 Tab 键字段间跳转，纯鼠标操作效率低。

**修复内容**：
| 快捷键 | 功能 |
|--------|------|
| `Ctrl+S` / `Cmd+S` | 触发"保存为预制内容"按钮（编辑器页） |
| `Ctrl+Enter` / `Cmd+Enter` | 触发"生成合同"按钮（编辑器页） |
| `Esc` | 关闭生成结果面板（编辑器页） |
| `Tab` / `Shift+Tab` | 在编辑器所有可见输入框之间循环跳转，自动滚动到目标字段 |

**实现位置**：
- `templates/editor.html`：添加 `keydown` 事件监听（内联脚本）
- `static/js/editor.js`：添加 Tab 导航逻辑，过滤隐藏字段、跳过只读计算字段

---

### 3. 编辑器自动保存（草稿）

**问题描述**：浏览器意外关闭导致填写内容全部丢失。

**修复内容**：
- 字段变更后 **5 秒**自动序列化到 `localStorage`
- 每 **30 秒**强制检查并保存（防止边缘情况）
- 页面加载时检测草稿，自动恢复填写内容、表格数据和项目归类信息
- 草稿键名含模板文件名（`ct_draft_<模板名>`），不同模板互不覆盖
- 草稿超过 **72 小时**自动过期清除
- 合同生成成功后自动清除对应草稿

**实现位置**：
- `templates/editor.html`：`saveDraft()` / `restoreDraft()` 函数 + 定时器
- `static/js/editor.js`：`showGenerationResult()` 中调用 `window.clearDraft()`

---

### 4. 合并侧边栏重复导航入口

**问题描述**：侧边栏"合同生成"和"模板库"均指向 `list_templates`，造成困惑。

**修复内容**：
- 从"资源管理"分组中**移除"模板库"条目**
- 保留"主要功能"中的"合同生成"作为唯一入口
- "资源管理"分组仅保留"Excel 单据"

**实现位置**：`templates/base.html` 侧边栏 `<nav>` 区域

---

## P2 — 中优先级（已修复 ✓）

### 5. 表格列删除增加确认提示

**问题描述**：表头列旁 `×` 按钮无确认直接删除整列数据，可能误操作。

**修复内容**：
- `removeTableColumnAt()` 在执行删除前弹出 `confirm()` 对话框
- 提示文字包含具体列名（如"确定删除列「产品名称」及其所有数据吗？此操作不可撤销。"）

**实现位置**：`static/js/editor.js` → `removeTableColumnAt()` 函数

---

### 6. 付款计划编辑表优化

**问题描述**：14 列表格 `min-width: 1500px`，无横向滚动提示，体验差。

**修复内容**：
- 表格容器上方添加**滚动提示条**："表格较宽，可左右滚动查看全部列（共14列）"
- `min-width` 从 1500px 降至 1200px
- 表头添加宽度约束（`w-16` ~ `w-40`），减少无效空间占用
- "付款条件/备注"和"原文依据"列宽设为 `w-40`（约 160px）
- 文本域行数从 2 行降为 1 行，鼠标悬停可查看全文

**实现位置**：
- `templates/contract_detail.html`：表格容器 + 表头宽度
- `static/style.css`：`.table-scroll-hint` 样式

---

### 7. 添加暗色模式切换

**问题描述**：系统硬编码 `data-theme="light"`，无暗色主题。

**修复内容**：
- 顶部工具栏添加**主题切换按钮**（☀/🌙 图标动态切换）
- 主题偏好自动保存到 `localStorage`，刷新后保持
- 添加暗色模式下布局元素的 CSS 适配规则（侧边栏、顶栏、面包屑、按钮）

**实现位置**：
- `templates/base.html`：`<html>` 标签 Alpine.js 主题绑定 + 切换按钮
- `static/style.css`：`[data-theme="dark"]` 覆盖规则

---

## P3 — 低优先级（已修复 ✓）

### 8. 字段导航添加各分类计数

**问题描述**：过滤按钮缺少未填/必填数量统计，用户无法快速感知填写状态。

**修复内容**：
- "全部"、"必填"、"未填"、"公式"过滤按钮旁显示 badge 计数
- `updateProgress()` 同步更新各分类计数
- 随着填写进展，数字实时变化

**实现位置**：
- `templates/editor.html`：过滤按钮 HTML
- `static/js/editor.js`：`updateProgress()` 函数

---

## 测试验证

```
$ pytest test_frontend_assets.py test_editor_js.py -q
4 passed

$ pytest test_app_flows.py test_security.py -q
15 passed

$ pytest test_operations_ui.py -q
8 passed

总计：27/27 passed，0 失败，0 回归
```

---

## 文件变更汇总

| 文件 | 变更行数 | 涉及修复 |
|------|---------|---------|
| `templates/base.html` | ~50 行删除 + ~10 行新增 | #1, #4, #7 |
| `static/style.css` | ~70 行新增 | #1, #6, #7 |
| `templates/editor.html` | ~110 行新增 | #2, #3, #8 |
| `static/js/editor.js` | ~50 行新增 | #2, #3, #5, #8 |
| `templates/contract_detail.html` | ~15 行修改 | #6 |

---

## 后续迭代建议（未在本次修复）

| 序号 | 改进项 | 预估工作量 |
|------|--------|-----------|
| 9 | 批量生成结果页提供各合同详情链接 | 后端 API 改造 + 前端渲染：2h |
| 10 | 模板编制器 Undo/Redo（命令模式） | 全新功能：8h |
| 11 | 手机端编辑器优化（响应式重构） | UI 重构：16h |
| 12 | Toast 通知可配置显示时长 | 小改动：1h |
