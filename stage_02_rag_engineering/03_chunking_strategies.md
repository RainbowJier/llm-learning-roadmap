# 文本切分策略

> 对应周次：Week 4-5 ｜ 投入：15小时 ｜ 前置：02_document_parsing.md（需要中间格式语料）

---

## 本文档目标

实现三种切分策略并**用实验证明父子文档切分最优**：小chunk负责搜得准，大chunk负责答得全。

---

## Step 1: 切分的核心矛盾（1小时）

```
chunk越小 → 向量语义越集中 → 检索越准 → 但LLM读到的上下文越碎
chunk越大 → 上下文越完整   → 回答越稳 → 但向量语义稀释 → 检索越糊

父子文档切分 = 两头都要：
  用小chunk（子）做向量匹配
  命中后取出它所属的大chunk（父）喂给LLM
```

其他硬规则：
- **表格、代码块 = 原子单元，永不切开**
- chunk之间保留 **overlap（重叠）**，避免关键句正好在边界

---

## Step 2: 策略一：递归字符切分（基线，2小时）

```python
# pip install langchain-text-splitters
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=400,       # 字符数
    chunk_overlap=60,     # 相邻块重叠60字
    separators=["\n\n", "\n", "。", "；", "，", " ", ""],  # 中文优先按句号断
)

chunks = splitter.split_text(raw_text)
```

递归逻辑：优先用第一个分隔符切；单段超长才降级用下一个分隔符。**这是最常用的基线**，先用它拿到第一批chunk和后续评估基线分。

**练习**：用相同语料跑 `chunk_size=200/400/800` 三组，肉眼对比表格被切断的比例（记录数字）。

---

## Step 3: 策略二：结构感知切分（3小时）

利用02文档中间格式里的 `heading` 信息，**按章节切**：

```python
def structure_aware_chunk(elements: list[dict], max_size: int = 800):
    """按标题层级组装：H1开新父块，H2开新父块（若父块超长）"""
    chunks, current, current_heading = [], [], ""

    for el in elements:
        if el["type"] == "heading":
            if current:
                chunks.append({"heading": current_heading,
                               "text": "\n".join(current)})
                current = []
            current_heading = el["text"]
        else:
            candidate = "\n".join(current + [el["text"]])
            if len(candidate) > max_size and current:
                chunks.append({"heading": current_heading,
                               "text": "\n".join(current)})
                current = [el["text"]]
            else:
                current.append(el["text"])
    if current:
        chunks.append({"heading": current_heading, "text": "\n".join(current)})
    return chunks
```

优势：每个chunk自带章节标题 → **把标题拼进chunk文本再embedding**（上下文增强，检索提升明显）：

```python
def enrich(chunk: dict) -> str:
    return f"{chunk['heading']}\n{chunk['text']}"    # 标题前置后再向量化
```

---

## Step 4: 策略三：父子文档切分（重点，5小时）

```python
from dataclasses import dataclass, field

@dataclass
class ChunkPair:
    child: str                 # 小块：用于向量检索（150-300字）
    parent_id: str             # 命中后取父块
    heading: str

class ParentChildChunker:
    def __init__(self, child_size=250, child_overlap=50,
                 parent_size=1200, parent_overlap=100):
        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=child_size, chunk_overlap=child_overlap,
            separators=["\n\n", "\n", "。", "；", "，"])
        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=parent_size, chunk_overlap=parent_overlap,
            separators=["\n\n", "\n"])

    def split(self, elements: list[dict], doc_id: str):
        parents = []            # [(parent_id, parent_text)]
        children = []           # [ChunkPair]

        structured = structure_aware_chunk(elements, max_size=1200)
        for i, sec in enumerate(structured):
            parent_text = enrich(sec)                    # 带标题的父块
            pid = f"{doc_id}_p{i}"
            parents.append((pid, parent_text))

            for piece in self.child_splitter.split_text(sec["text"]):
                children.append(ChunkPair(
                    child=f"{sec['heading']}\n{piece}",   # 子块也带标题
                    parent_id=pid,
                    heading=sec["heading"]))
        return parents, children

    def get_context(self, hit_children: list[ChunkPair],
                    parent_store: dict[str, str], max_parents: int = 3) -> str:
        """检索命中子块后，取去重后的父块拼上下文"""
        pids = list(dict.fromkeys(c.parent_id for c in hit_children))[:max_parents]
        return "\n\n".join(parent_store[pid] for pid in pids)
```

存储方案：**子块进向量库（带parent_id元数据），父块进普通KV**（dict / Redis / 数据库都行）。

```
向量库: child_chunk ──metadata: {parent_id, doc_id, heading}──┐
父块库: parent_id → parent_text  ◄──────────────────────────┘
```

---

## Step 5: 表格与特殊元素保护（2小时）

```python
def protect_tables(text: str) -> tuple[str, dict[str, str]]:
    """切分前把表格挖出来占位，切完再放回去"""
    placeholders = {}
    def _stash(m):
        key = f"__TABLE_{len(placeholders)}__"
        placeholders[key] = m.group(0)
        return key
    # 匹配markdown表格（| 开头的连续行）
    protected = re.sub(r"(\|.+\|\n\|[-:| ]+\|\n(?:\|.*\|\n?)+)", _stash, text)
    return protected, placeholders

def restore(text: str, placeholders: dict[str, str]) -> str:
    for k, v in placeholders.items():
        text = text.replace(k, v)
    return text

# 流程: protect → split → 每个chunk restore
# 效果: 表格要么完整地在一个chunk里，要么作为占位符被单独处理
```

**验收断言**：切分后遍历所有chunk，`|` 行数总和 == 原文 `|` 行数（没有表格行丢失或重复）。

---

## Step 6: 对比实验（2小时）

用同一批语料 + 同一批测试问题，对比三种策略的**检索命中情况**（此时还没有评估框架，先手工看top1是否包含答案段落）：

| 策略 | 表格完整率 | top1命中（10个问题手工判） | 平均chunk长度 |
|------|----------|--------------------------|--------------|
| 递归400字 | __% | __/10 | |
| 结构感知 | __% | __/10 | |
| 父子切分 | __% | __/10 | |

把表格填进学习日志。**这份对比就是06评估文档的前身，也是面试时"我做过策略对比"的证据**。

---

## ✅ 验收清单

- [ ] 三种切分器全部实现并有单测
- [ ] 表格保护机制生效（行数守恒断言）
- [ ] 父子切分的child带parent_id元数据入向量库
- [ ] 对比实验数据已记录（哪怕手工判分）

---

## 参数速查（起步默认值，都需按语料调）

| 参数 | 默认 | 调整信号 |
|------|------|---------|
| child_size | 250字 | 检索不准→调小；召回内容太零碎→调大 |
| parent_size | 1200字 | LLM答缺上下文→调大；超token预算→调小 |
| overlap | chunk的15-20% | 关键句总在边界丢失→加大 |
| 取父块数 | 3 | 上下文不够→加；噪声变多→减 |

---

**下一篇** → [04_hybrid_retrieval.md](./04_hybrid_retrieval.md)
