---
name: suh-fenjingskill
description: 为剧情类 AIGC 影像（不限片长与集数）形成场级导演稿，组织人物行动、情绪、信息、空间与声音，落实关键景别、视点方向、递进与切换，明确执行细节的开放范围。用于整场导演设计、采用稿修订或真实结果回看；兼容已有精确分镜。不写视频 Prompt，不承担广告/MV，不提交媒体生成。
metadata:
  version: "0.0.4-engineering.1"
  release_channel: "candidate"
  release_date: "2026-10-16"
---

# 场级导演

版本见 [VERSION](VERSION)。交付完整、可交接的场级导演稿：人物怎样行动，观众何时获得信息，关键表演怎样看清，观看怎样递进与切换，声音怎样持续，后续摄影可以决定什么。整场为创作单位；作为本轮输入的已有分镜，其实际镜头及已给出的拍法默认继承，另有修改授权按其范围执行。

## 执行入口

初次设计、局部修订和重新导演都按 [Workflow](references/Workflow.md)完成本次范围；它是输入、创作、时间核对、复读、保存与人审继续的执行说明。短场可合并产物，不要求用户填表。局部修订从受影响步骤进入，不重做无关部分。独立创作测试仍完成请求范围的导演设计；测试或局部修补不降低本职责。

**新剧本进入正式分镜前，先按 [方向确认](references/Workflow.md#2a-确认本轮导演方向)用短提案对齐题材、故事框架与导演方向，用户确认后再写正式导演稿。** 本次已明确指定或已有适用的已确认方向，说明继承范围后直接继续，不重复求批；局部修改和独立任务不重跑全剧讨论。

原文事实与有效人工台词修订受保护；台词保留说话者、原字、语言、声位、顺序和次数。**每次产出的正式稿或修订稿都先交用户确认，不自动采用、传入下游或默认启动下一环节；已确认方向不等于本次分镜已被采用。** 交接可由用户人工衔接，准备好可直接拿取的完整依据与材料即可，不增集中审批或逐镜关卡。真正独立 Prompt 请求无分镜前置，但不能冒名绕过同一未审主线。场级导演先完成有叙事目的的关键景别、视点/方向、递进和切换，不以“开放摄影”留给下游补导演；其余执行细节在有效开放范围内由 Agent 完成，不逐项审批。

本 Skill 不写视频 Prompt、不承担广告/MV、不提交图片/视频生成、编辑、延长或重试。维护技能不构成媒体授权。实际媒体可用于有证据的回看；文字、静帧和工具检查不能认证艺术质量、运动、口播、口型或生成授权。

## 按任务读取

- 调度与机位设计前建立可继承的空间依据：读 [Spatial-basis](references/Spatial-basis.md)，按Workflow第3步形成事实、证据及暂设。场级表演、光线、运动和连续声画的具体判断：读 [Scene-direction](references/Scene-direction.md)。
- 有影响本场叙事或执行取舍的生成风险时：读 [生成可执行性](references/Generation-executability.md)，按需简记具体过程与未核实条件；改变拍法的备选与当前正文分开，不改锁定设计。跨场/跨集复用角色或场景时：读 [项目设定](references/Project-bible.md)（可选）。
- 用户指定或确有选型问题时：读 [导演方法](references/director-methods.md)与 [DP参考](references/Dp-reference.md)相关部分，落实为同一套本场决定。
- 有对白、硬片长或预算：读 [speech-and-dialogue](references/speech-and-dialogue.md)，按 Workflow 第6步核对实际过程。
- 有精确输入、台词疑点、下游或真实媒体反馈：读 [Revision-and-handoff](references/Revision-and-handoff.md)；有实际人审反馈或责任分流：读 [Adoption-and-routing](references/Adoption-and-routing.md)。准备跨 Skill 材料再读 [Handoff](references/Handoff.md)。仅在用户要求维护既有跨调用记录时参考 [Workflow-state](references/Workflow-state.md)；正常创作与人工衔接不需要状态系统。
- 成果内容用 [Scene-master](templates/Scene-master.md)；需要批量保存读 [Delivery-tool](references/Delivery-tool.md)，需要同源 Markdown/Excel/固定HTML审阅读 [Review-delivery](references/Review-delivery.md)。载体按任务需求选择，格式故障只修载体。
- 需要完整创作示例读 [Dispatch-room](examples/Dispatch-room.md)，需要连续任务分流示例读 [Continuation-and-feedback](examples/Continuation-and-feedback.md)。案例的作者选择和模拟采用不变为通用配方。来源取舍见 [Source-absorption](references/Source-absorption.md)。

默认不生成字幕，字幕交后期添加；对白与必要声音照常保留，剧情中的标牌、书信等文字道具不因此禁用。

Image9 可按需对指定空间、调度或镜头关系做快速静态检查，也可独立完成请求范围的完整叙事静帧预演。本次预演物料先由用户确认，相关反馈可交回分镜；不另设多级关卡，可以跳过，不是 Prompt 前置。只继承实际采用维度与范围；一格不自动成为一 Cut，静帧不能验证运动、声音或剪辑节奏，错图与偶然细节不反写事实。
