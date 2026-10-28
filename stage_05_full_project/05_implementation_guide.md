# 实现指南

> 周次：Week 5-8 ｜ 投入：60小时 ｜ 前置：04_data_preparation.md

---

## 目标

四周冲刺：按"骨架→血肉→皮肤"顺序实现，每周有可演示的增量。**不追求完美，追求每周能跑**。

---

## Week 5: 工作流骨架跑通（15小时）

```
Day 1-2  复用模块搬运: rag/ + resilience/ import跑通单测
Day 3-4  新节点实现: classify(新枚举) + polite_refuse + route_tool
Day 5    端到端最小链: classify→rag→compose→END (chitchat和tool先stub)
Day 6-7  chaos测试移植: 换标签跑通 + preflight绿
```

**周验收**：命令行里问3个P0问题（1条policy、1条multi、1条chitchat），全链路走通，trace完整。

## Week 6: 核心能力补齐（15小时）

```
Day 1-3  decompose多条件节点 + evidences合并进compose
Day 4-5  工具实现: schedule_tool(空教室)/calendar_tool(校历)
         —— 课表数据拿不到就mock，接口设计成真的
Day 6    validate升级: 引用核验prompt + feedback字段
Day 7    意图分类100条专测: 准确率<95%就修prompt/加few-shot
```

**周验收**：02需求的US-01~US-04演示脚本全部可跑；意图准确率≥95%。

## Week 7: 接口与反馈闭环（15小时）

```
Day 1-2  API: /ask(带session多轮) + /feedback + /admin/badcases
Day 3-4  Streamlit: 聊天界面+引用展示+👍👎按钮+纠错弹窗
Day 5    反馈后台: feedback表→bad_case自动候选(👎全部进)
Day 6-7  部署: docker-compose全栈上服务器(学生机/便宜VPS/内网穿透)
         监控栈起来, 告警指向自己微信/邮件
```

**周验收**：公网(或校园网)可访问的URL；一条反馈从点击到出现在后台全流程走通。

## Week 8: 内测准备与安全加固（15小时）

```
Day 1-2  安全: 邀请码鉴权(控用户量) + 输入限长 + 简单频控(每用户20次/天)
Day 3    隐私: 日志脱敏(不记姓名学号) + 隐私声明文案
Day 4-5  150条测试集全量回归 + BadCase修一轮(top5类问题)
Day 6    演示视频脚本 + 内测群运营文案
Day 7    缓冲(一定会用上)
```

**周验收**：preflight+回归全绿；找5个同学预内测，每人提3个问题不崩溃。

---

## 实现纪律（贴显示器上）

1. **每个新功能先写测试**（测试集里找不到对应case的功能不写）
2. **每周五打tag**（v0.1骨架 / v0.2核心 / v0.3闭环 / v0.4内测）
3. **配置零硬编码**（换环境只改.env）
4. **遇到"要不要做X"的犹豫**：看02需求文档，不在P0/P1里就不做
5. **卡超过2小时**：降级方案先上（mock/简化版），记入TODO继续走

---

## ✅ 验收清单（四周末总检）

- [ ] 全部P0用户故事验收条件打勾
- [ ] P1故事≥70%完成
- [ ] 150条回归：四指标+意图+引用全部达标或有明确差距分析
- [ ] 公网可用、鉴权限流生效、日志脱敏
- [ ] git tag四个版本，每个可独立运行

---

**下一篇** → [06_testing_and_deployment.md](./06_testing_and_deployment.md)
