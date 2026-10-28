# 数据准备

> 周次：Week 3-4 ｜ 投入：20小时 ｜ 前置：03_architecture_design.md

---

## 目标

数据是本项目的**地基中的地基**：采集→清洗→入库→测试集扩充→基线指标。前两个阶段练的所有数据处理功夫在这里兑现。

---

## Step 1: 数据采集工程化（6小时）

把选型周手工下载的文件变成**可持续更新的爬取管线**：

```python
# scripts/crawl_docs.py
"""每周跑一次：增量抓取教务处/学工处/财务处通知与附件"""
import aiohttp, asyncio
from pathlib import Path
from datetime import datetime

SOURCES = [
    {"name": "jwc", "url": "http://jwc.xxx.edu.cn/tzgg.htm",
     "attach": True},                          # 抓附件PDF/Word
    {"name": "xsc", "url": "http://xsc.xxx.edu.cn/xyzq/list.htm",
     "attach": True},
    {"name": "cwc", "url": "http://cwc.xxx.edu.cn/tz.htm",
     "attach": True},
]

async def crawl_incremental():
    """增量逻辑：记录每个源的最后抓取URL/日期，只抓新的"""
    state = load_crawl_state()
    for src in SOURCES:
        new_docs = await crawl_source(src, since=state[src["name"]])
        for doc in new_docs:
            save(f"datasets/documents/{src['name']}/{doc.filename}", doc.body)
        state[src["name"]] = new_docs[-1].marker if new_docs else state[src["name"]]
    save_crawl_state(state)
```

采集纪律：
- **只抓公开信息**（无需登录的通知页），遵守robots、控制频率（并发≤3、间隔≥1s）
- 原始文件**永不修改**，处理产物另存（Stage 0原则）
- 每次采集输出统计：新增N份、失败M个、文件类型分布

---

## Step 2: 解析与清洗流水线（6小时）

跑Stage 2-02的DocumentParser全量处理，重点盯**教务文件的特殊性**：

| 教务文件特征 | 处理策略 |
|-------------|---------|
| 通知正文在HTML、附件才是正文 | 正文+附件都入库，关联doc_id |
| 附件是扫描版红头文件 | is_scanned→OCR路径，OCR结果标记低置信度 |
| 表格：奖学金评定表/学分认定表 | 表格→Markdown，行数守恒断言 |
| 政策有时效性（"2024版规定"） | 文件名/正文中提取生效年份入元数据，检索可过滤旧版 |
| 多校区差异 | 提取校区字段入元数据 |

**元数据schema（比Stage 2多三个业务字段）**：

```json
{
  "doc_id": "jwc_2024_087",
  "source": "jwc",
  "effective_year": 2024,
  "category": "学籍管理",       // 分类由LLM打标+人工抽检
  "confidence": 1.0,            // OCR文件<1.0
  "url": "原始链接"
}
```

---

## Step 3: 索引与测试集扩充（4小时）

- [ ] 跑build_index全量入库（记录chunk/父块统计）
- [ ] 测试集从v1的80条扩到**150条**（新增条目覆盖：多校区差异、时效性问题"最新的转专业政策"、表格数字题各≥10条）
- [ ] 时效性测试题标注期望引用的effective_year（防答出旧政策）

---

## Step 4: 拿到全链路基线（4小时）

**先跑通再优化**——用最直接的组合出一版能用的系统：

```bash
python scripts/evaluate.py --test-set datasets/test_set_150.json --tag baseline
```

基线报告必须包含：

| 指标 | 基线值 | 目标 |
|------|--------|------|
| Ragas四指标 | __ | CR85/CP80/F90/AR85 |
| 意图分类准确率 | __ | >95% |
| 多条件题正确率 | __ | ≥70% |
| 拒答正确率 | __ | ≥50% |
| 引用准确率（人工抽检20条） | __ | ≥90% |
| P95延迟 | __ | <3s |

**把这份报告钉在墙上**——12周后你要指着它讲"从这里到这里"的故事。

---

## ✅ 验收清单

- [ ] 爬取脚本增量可重复运行（跑两次第二次新增=0）
- [ ] 语料≥150份，表格类≥30份，OCR低置信标记完整
- [ ] 元数据含生效年份/分类/校区
- [ ] 测试集150条（含时效性/多校区专项题）
- [ ] 基线报告落盘 `reports/baseline.md`

---

**下一篇** → [05_implementation_guide.md](./05_implementation_guide.md)
