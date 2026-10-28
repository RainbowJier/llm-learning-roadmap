# 文档解析工程

> 对应周次：Week 2-3 ｜ 投入：20小时 ｜ 前置：01_rag_overview.md

---

## 本文档目标

把PDF/Word/HTML里的内容（尤其是**表格和双栏排版**）正确提取成结构化Markdown。这是RAG最容易翻车的环节，也是拉开差距的地方。

---

## Step 1: 准备测试语料（1小时）

**不要用干净的测试PDF**。去收集5-10份真实"脏"文档：

- 公司/学校的制度类PDF（含跨页表格）
- 一份扫描件（图片型PDF）
- 一份双栏排版的论文/报告
- 一个 `.docx`（带表格和图片）
- 一个通知类网页（HTML）

存到 `datasets/documents/`。**后面所有解析、切分、检索实验都用这批语料**，保证结果可比。

---

## Step 2: PDF文本提取三级跳（6小时）

### 2.1 Level 1: pypdf / PyMuPDF 直接提取（先看有多糟）

```python
import fitz  # PyMuPDF，比pypdf快且信息全

def extract_raw(pdf_path: str) -> list[str]:
    doc = fitz.open(pdf_path)
    return [page.get_text() for page in doc]

# 实验：跑你的双栏论文，观察输出顺序
# 典型结果：左右栏文字交错、表格散架、页眉页脚混入
```

**实验记录**（写进学习日志）：每份文档用Level 1提取后，人工检查表格是否完整、双栏是否串行。

### 2.2 Level 2: 带坐标的块级提取

```python
def extract_blocks_sorted(pdf_path: str):
    doc = fitz.open(pdf_path)
    all_blocks = []
    for pno, page in enumerate(doc):
        for b in page.get_text("blocks"):    # (x0,y0,x1,y1,text,block_no,type)
            x0, y0, x1, y1, text, _, btype = b
            if btype == 0:                   # 0=文本块
                all_blocks.append({
                    "page": pno, "bbox": (x0, y0, x1, y1),
                    "text": text.strip(),
                })
    # 阅读顺序排序：先按页，页内先上后下、先左后右
    all_blocks.sort(key=lambda b: (b["page"], round(b["bbox"][1]),
                                   round(b["bbox"][0])))
    return all_blocks

# 双栏检测技巧：统计每行block的x中心点，若明显聚集在左右两簇 → 双栏
# 此时排序改为：先左栏全部（按y），再右栏全部（按y）
```

### 2.3 Level 3: 版面分析工具（表格识别主力）

```python
# pip install unstructured[all-docs]
from unstructured.partition.pdf import partition_pdf

elements = partition_pdf(
    pdf_path,
    strategy="hi_res",                 # 深度版面分析
    infer_table_structure=True,        # 表格→HTML
    languages=["zh"],                  # OCR语言
)

for el in elements:
    print(el.category)        # Title / NarrativeText / Table / ListItem
    print(el.text)
    print("---")

# Table类别的el.metadata.text_as_html 直接是<table>...</table>
```

表格转Markdown：

```python
import htmltabletomd          # pip install htmltabletomd

def table_to_markdown(html_table: str) -> str:
    return htmltabletomd.convert(html_table)

# 验证表格完整性：原PDF表格8行，转换后必须也是8行
def check_table_rows(md_table: str, expected_rows: int) -> bool:
    return len([l for l in md_table.splitlines() if l.startswith("|")]) >= expected_rows
```

**验收实验**：对你的"跨页表格"语料，Level 3必须能把表格行数提对。提不对的记录原因（扫描件？合并单元格？），这些就是你的BadCase库。

---

## Step 3: 扫描件OCR（3小时）

```python
# 判断是否扫描件：文本层字符数 < 100 即视为扫描件
def is_scanned(pdf_path: str) -> bool:
    doc = fitz.open(pdf_path)
    total_chars = sum(len(p.get_text()) for p in doc[:3])   # 抽查前3页
    return total_chars < 100

# OCR方案A（中文强）: PaddleOCR
# from paddleocr import PaddleOCR
# ocr = PaddleOCR(use_angle_cls=True, lang="ch")
# result = ocr.ocr(pdf_path, cls=True)

# OCR方案B（轻量）: RapidOCR（onnxruntime，无paddle依赖）
# from rapidocr_onnxruntime import RapidOCR
# engine = RapidOCR()
```

OCR后处理必做：按y坐标聚类还原行、按x坐标排序还原列。**只做一次实验感知难度即可**——生产中扫描件建议直接上 RagFlow 的 deepdoc 或 MinerU，自己拼OCR细节性价比低，但要知道它们内部在做什么。

---

## Step 4: Word与HTML解析（3小时）

```python
# 4.1 docx：表格必须单独走
from docx import Document

def parse_docx(path: str):
    doc = Document(path)
    output = []
    for para in doc.paragraphs:            # 段落
        if para.text.strip():
            style = para.style.name        # Heading 1/2 可用于层级切分！
            output.append({"type": "heading" if "Heading" in style else "para",
                           "level": style, "text": para.text})
    for table in doc.tables:               # 表格（pypdf的paragraphs接口会漏掉）
        rows = [[cell.text for cell in row.cells] for row in table.rows]
        output.append({"type": "table", "markdown": rows_to_md(rows)})
    return output

# 4.2 HTML：先用readability抽正文再清洗
# pip install trafilatura
import trafilatura
text = trafilatura.extract(html_str, include_tables=True, output_format="markdown")
```

---

## Step 5: 清洗规范（2小时）

统一输出格式（后续切分只认这个格式）：

```python
"""清洗规则清单（每条都写成一个函数，可单测）"""
def clean(text: str) -> str:
    text = re.sub(r"?\s*[-–—•]\s*", "- ", text)      # 项目符号归一
    text = re.sub(r"第\s*\d+\s*页\s*共\s*\d+\s*页", "", text) # 页眉页脚
    text = re.sub(r"[ \t]+", " ", text)                      # 连续空格
    text = re.sub(r"\n{3,}", "\n\n", text)                   # 连续空行
    # 全角/半角数字标点归一（检索一致性关键！）
    text = text.replace("：", ":").replace("，", ",")
    return text.strip()
```

**统一中间格式**（本阶段所有文档最终都转成它）：

```json
{
  "doc_id": "hr_policy_v3",
  "source": "人事制度.pdf",
  "elements": [
    {"type": "heading", "level": 1, "text": "第二章 年假管理"},
    {"type": "para", "text": "新员工试用期享受5天年假..."},
    {"type": "table", "markdown": "| 城市 | 上限 |\n|---|---|\n| 北京 | 500 |"}
  ]
}
```

---

## Step 6: 构建自己的Parser类（5小时）

```python
class DocumentParser:
    """统一入口：按扩展名分派，输出标准中间格式"""

    async def parse(self, path: str) -> dict:
        ext = Path(path).suffix.lower()
        match ext:
            case ".pdf":  elements = await self._parse_pdf(path)
            case ".docx": elements = await self._parse_docx(path)
            case ".html": elements = await self._parse_html(path)
            case _:       elements = await self._parse_txt(path)
        return {"doc_id": Path(path).stem,
                "source": path,
                "elements": [self._normalize(e) for e in elements]}

    async def _parse_pdf(self, path):
        if is_scanned(path):
            return await self._ocr_pdf(path)      # 扫描件走OCR
        return await self._hi_res_pdf(path)       # 版面分析
```

**验收测试**（写进 `tests/test_parser.py`）：

| 用例 | 断言 |
|------|------|
| 双栏论文 | 输出阅读顺序正确（人工标注10个句对验证） |
| 跨页表格 | 表格行数 = 原文行数 ± 1 |
| docx表格 | markdown表格包含所有单元格 |
| 扫描件 | 识别出 ≥ 80% 的关键文字（抽查） |
| 页眉页脚 | 清洗后不存在"第X页共Y页" |

---

## ✅ 验收清单

- [ ] 5份脏语料全部解析成功并转成统一中间格式
- [ ] 表格完整性有自动化断言，不是肉眼看看
- [ ] 扫描件有检测逻辑（is_scanned）和降级路径
- [ ] 解析结果入库 `datasets/processed/`，供03文档使用

---

## 常见坑

| 症状 | 原因 | 解法 |
|------|------|------|
| 中文PDF提取出乱码 | 嵌入字体无ToUnicode映射 | 换PyMuPDF；不行就OCR |
| unstructured表格识别慢 | hi_res模型在CPU跑 | 先缓存结果；量大再上GPU或MinerU |
| 表格转markdown列错位 | 合并单元格 | 记录BadCase，复杂的表转成"行描述文本"兜底 |
| docx解析丢内容 | 忘了遍历doc.tables | 段落和表格分开处理再按位置合并 |

---

**下一篇** → [03_chunking_strategies.md](./03_chunking_strategies.md)
