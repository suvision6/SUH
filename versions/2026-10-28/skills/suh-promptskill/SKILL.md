---
name: suh-promptskill
description: 为剧情类 AIGC 影像（不限片长与集数）组织生成段和段内镜头，输出完整视频Prompt；继承已有分镜，支持明确开放的摄影规划及无分镜独立创作或测试，结合实际素材回看局部修订。Image9可选，不自动提交图片、视频、编辑或延长任务。
metadata:
  version: "0.0.4-prompt.3.engineering.1.handoff.1"
  release_channel: "candidate"
  release_date: "2026-10-28"
---

# 剧情视频 Prompt

版本见 [VERSION](VERSION)。把整场理解落实成可复制的生成正文、段间承接和可修订交付物。自然语言和已有文档就是输入，不要求先填表。本版本止于文本与输入准备，不自动提交图片、视频、编辑、延长或付费重试。

## 入口与职责

主线只为实际人审采用且有效的分镜范围写Prompt；真实独立创作、快速测试和局部修补可直接进入，不把未审主线改名绕过。详细采用与跨Skill消费规则见 [Handoff](references/Handoff.md)。

已有分镜的实际镜头、摄影、调度、动作时间及声画/Cut关系默认继承，无需另说锁定；准确展开、明确开放微调及生成组织不等于重剪。无分镜独立任务可在授权内导演，用户明确时长作为创作条件；新对白须有创作授权并与原文分清。段落、行、Beat或Image9格不自动增加Cut。

## 执行与按需参考

按[Workflow](references/Workflow.md)完成准入、读源、整场声画理解、生成组织、完整正文、实际演读、交付及修订。短单条任务可内部压缩判断并直接交成品，无强制Bundle或项目档案；已有状态记录才使用相应context/check。状态工具只辅助依据恢复，不能代替真实反馈。

先完整读取本入口及Workflow的当前入口与适用步骤；下列条件成立时对应参考为本轮必读，短单条可压缩呈现但不省略适用规则。只取开头、搜索片段或收到截断时补齐缺失部分，命令成功和自报已读不证明读全。连续上下文内完整内容仍可用且版本未变可复用；上下文压缩后恢复、换入本Skill、版本变化或内容可用性不明时，重读入口、适用参考和当前有效正文。不可读处指出影响，不凭记忆冒充读取；简记实际依据与缺口即可，不新增读取表。

- 输入开放程度、控制精度、生成边界与长镜接续：读[输入与生成组织](references/Input-and-segmentation.md)。
- 正式生成正文先读唯一[格式与Cut计划时间规范](references/Output-format.md)及当前[入口profile](references/Generation-profile.json)：提交单元总长须为profile范围内的整数秒，Cut内部可用小数。有分镜输入默认每个实际Cut写连续起止计划时间，单Cut同样执行；明确不用时间戳只省略范围，仍保留Cut编号与合规总长。无分镜独立入口保留自然段与导演能力。
- 写调度和机位前按[共享空间依据](references/Spatial-basis.md)继承主线有效空间，独立入口先建立最小依据；当前初态、摄影/调度、表演、空间光声及正文表达：读[正文与跨段状态](references/Writing-and-continuity.md)。含对白或估时时读[对白与声画计时](references/speech-and-dialogue.md)。指定原话及最新明确局部修订优先；不静默纠错，不以超时删词、换词或提速。
- 跨Skill接手、部分采用或变更：读[交接约定](references/Handoff.md)和[有效依据与变更回流](references/Active-context.md)；需状态恢复时读[调度状态](references/Workflow-state.md)。按真实影响范围修订，保护其他正确原话、摄影和单元。
- 写正文时读[生成可执行性](references/Generation-executability.md)，明确必要初态、动作主体与观看关系。稳妥实现只落实当前有效设计中已采用或本次已授权的部分；风险标记不使未采用备选成为执行依据，也不授权改变既有镜头、切点或信息呈现。跨场/跨集一致性按需读[项目设定](references/Project-bible.md)；延续同一角色或修表演时读[表演延续与局修](references/Performance-continuity.md)。
- 摄影或导演方向确有需要时读[摄影参考](references/Dp-reference.md)、[导演方法](references/director-methods.md)；需要远距观察、近身广角、焦点揭示或主观穿行时按需读[观看与光学组合](references/Optics-and-viewing.md)。把采用方向落实到本段声画，不强制名家或固定前缀。
- 有素材、预演或编辑/延长文本需求时读[素材与任务](references/Assets-and-tasks.md)；收到实际媒体时读[回看与交付](references/Media-review-and-export.md)。媒体只按实读范围报告，不把错图变为项目事实。

## 成果

默认两层交付：正文外简记范围/采用依据、必要素材占位映射及参数/接续；内层按[Output-format](references/Output-format.md)交独立可复制正文。素材由用户最后手动映射/@，上传或绑定不是文本交付门禁；真实提交前再核对。多段按需用[工作稿示意](templates/Prompt-master.md)。来源和旧版本只读，新成果并列。每次新物料（含修订稿）交用户看过确认后，才在确认范围内采用或交接；已授权修改仍可先完成，不因此免去新物料的人审。各Skill可人工衔接，不自动采用、推进或联动。

需要来源/对白结构核对时用[交付工具](references/Delivery-tool.md)；现成正文仅需保存时可选[同文导出](references/Media-review-and-export.md#同文导出工具)。[Markdown、Excel、固定HTML](references/Review-delivery.md)从同一内容派生比较，不预锁载体默认，不改变已定正文格式。工具不能认证剧情、艺术质量、实际接声、人类身份或生成授权。

完成形态可按入口看[无分镜整场创作](examples/Independent-scene.md)、[采用稿转写](examples/Prompt-worked-example.md)、[继续与修订](examples/Workflow-continuation.md)；实拍合成文本可看[保留母版的局修例](examples/Composite-repair.md)。案例设定与反馈均为教学，不作运行事实或授权。开发溯源见[官方规则取舍](references/Official-rule-adaptation.md)，运行不要求安装官方Skill或使用Higgsfield。
