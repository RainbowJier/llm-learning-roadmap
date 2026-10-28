# 结构化输出

> 对应周次：Week 5-6 ｜ 投入：15小时 ｜ 前置：03_state_machine_design.md

---

## 本文档目标

让LLM的输出从"一段话"变成"可编程消费的强类型数据"：Schema定义 → API层强制 → 解析失败自动回炉。这是Agent稳定性的第一块基石。

---

## Step 1: 为什么"解析一段话"是灾难（1小时）

```
LLM输出: "好的，已为您查到订单12345，状态是已发货，预计明天到。"

❌ 正则提取数字 → "12345"和"明天"里的数字混在一起
❌ 关键词匹配 → 措辞稍微变就miss
❌ 信任LLM的JSON格式口头承诺 → "以下是JSON：```json {...} ```"（带markdown围栏）

必须做到：格式正确性由API/校验层保证，不靠prompt祈祷。
```

---

## Step 2: Pydantic定义输出Schema（3小时）

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional

# 案例：意图分类节点（03文档classify_node的返回）
class IntentResult(BaseModel):
    intent: Literal["order_query", "policy_query",
                    "repair_request", "chitchat"]
    confidence: float = Field(ge=0, le=1)
    extracted_entities: dict[str, str] = Field(
        default_factory=dict,
        description="提取的实体，如order_id、product_name")

# 案例：工单生成节点
class TicketDraft(BaseModel):
    summary: str = Field(max_length=100)
    priority: Literal["low", "medium", "high"]
    suggested_action: str
    needs_human: bool
```

**Schema设计四原则**：
1. **枚举优先**：能Enum/Literal就不要自由字符串
2. **字段描述写清楚**：`description`会进入LLM看到的schema，直接影响输出质量
3. **嵌套别超两层**：太深LLM容易漏字段
4. **默认值兜底**：可选信息给default，必填信息绝不给default

---

## Step 3: API层强制——三种实现（4小时）

### 3.1 方式A：Claude Structured Outputs（推荐，原生保证）

```python
import anthropic
from anthropic import Anthropic

client = Anthropic()

def classify_with_schema(text: str) -> IntentResult:
    resp = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=512,
        messages=[{"role": "user",
                   "content": f"对以下用户输入做意图分类：\n{text}"}],
        tools=[{
            "name": "report_intent",
            "description": "报告分类结果",
            "input_schema": IntentResult.model_json_schema(),
        }],
        tool_choice={"type": "tool", "name": "report_intent"},  # 强制调用
    )
    args = json.loads(resp.content[0].input)     # API保证符合schema
    return IntentResult(**args)                  # 双保险再校验一次
```

### 3.2 方式B：OpenAI Structured Outputs

```python
from openai import OpenAI
client = OpenAI()

resp = client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "intent_result",
            "schema": IntentResult.model_json_schema(),
            "strict": True,
        }
    },
)
result = IntentResult(**json.loads(resp.choices[0].message.content))
```

### 3.3 方式C：通用降级方案（任何模型都能用：prompt+校验+回炉）

```python
JSON_PROMPT = """...任务描述...

你必须只输出一个JSON对象，符合以下结构：
{schema}

注意：不要输出任何其他文字、不要markdown代码块。"""

async def structured_call(prompt: str, schema_model, llm,
                          max_attempts: int = 3) -> BaseModel:
    last_error = None
    for attempt in range(max_attempts):
        resp = await llm.chat(prompt if attempt == 0
                              else f"{prompt}\n\n你上次的输出无法解析，"
                                   f"错误：{last_error}。请严格只输出JSON。")
        try:
            data = json.loads(strip_fences(resp))    # 剥```json围栏
            return schema_model.model_validate(data) # Pydantic校验
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = str(e)[:200]
    raise StructuredOutputError(f"3次仍失败: {last_error}")

def strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()
```

**方式C是面试重点**：即使API有结构化输出，也要会讲"校验失败→错误信息回喂→重试"这个通用模式（它就是"Reflection/自我修复"的雏形）。

---

## Step 4: 校验失败回炉进LangGraph（3小时）

把结构化输出失败纳入03文档的状态机，而不是节点内偷偷重试：

```python
async def classify_node(state: TicketState) -> dict:
    try:
        result = await structured_call(
            build_classify_prompt(state["user_input"]),
            IntentResult, llm, max_attempts=2)        # 节点内软重试2次
        return {"intent": result.intent,
                "extracted_entities": result.extracted_entities,
                "trace": [f"classify:{result.intent}({result.confidence:.2f})"]}
    except StructuredOutputError as e:
        return {"intent": None,
                "validation_feedback": f"分类输出解析失败:{e}",
                "trace": ["classify:PARSE_FAIL"]}

def route_after_classify(state) -> str:
    if state["intent"] is None:
        return "fallback" if state["retry_count"] >= MAX_RETRY else "classify"
    ...  # 正常路由查表
```

**双层重试结构**（记住这个分层）：
- **节点内**：同构重试（格式错了马上再来，成本低，2次）
- **图层面**：异构重试（换策略/带反馈，贵，走条件边）

---

## Step 5: 对抗测试（4小时）

**主动构造刁钻输入，验证Schema防线**（这些case写进单测）：

| 测试输入 | 期望行为 |
|---------|---------|
| "订单号是 123456789012345678901234567890" | 超长数字，看是否被截断/科学计数法 |
| 空字符串/纯表情 | 意图应落chitchat或触发解析失败路径 |
| 中英混合 + 拼写错误 | 枚举仍应正确 |
| LLM输出带```围栏 | strip_fences处理掉 |
| LLM漏了confidence字段 | Pydantic校验失败 → 回炉 |
| LLM把confidence输出成"高" | 类型错误 → 回炉 |

**指标化**：跑100条真实用户问题，统计：
- 首次解析成功率（目标>95%）
- 结构化输出总成功率含重试（目标>99.5%）
- 平均重试次数（目标<0.1）

这份小报表是07项目报告的一部分。

---

## ✅ 验收清单

- [ ] 至少两种API级结构化输出跑通（Claude tool_use + OpenAI json_schema）
- [ ] 通用降级方案（prompt+校验+回炉）实现并有单测
- [ ] strip_fences处理markdown围栏
- [ ] 双层重试结构接入LangGraph节点
- [ ] 100条对抗测试通过率达标并留档

---

## 常见坑

| 坑 | 现象 | 解法 |
|----|------|------|
| schema里写了Optional一切都可空 | LLM疯狂省略字段 | 必填字段不给default |
| description太简略 | LLM乱填枚举 | 枚举值含义写进description |
| temperature没调0 | 同输入不同结构 | 结构化任务温度0 |
| 一次让LLM输出巨型schema | 漏字段率高 | 拆成多节点各管一小块 |

---

**下一篇** → [05_tool_calling.md](./05_tool_calling.md)
