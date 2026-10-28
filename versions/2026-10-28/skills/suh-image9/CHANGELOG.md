# 0.0.4-engineering.3 (candidate, 2026-10-16)

- P2: HTML and PDF consume the same verified image bytes captured during export.
- P3: run evidence requires historical target/interpreter fields, finite duration and plausible UTC timing.
- Recovery, adoption and creative rules are unchanged; visual approval is never automatic.
- Creative rules and all prior notes are preserved. No install or media submission.

# 0.0.4-engineering.2 (candidate, 2026-10-16)

- P3: recover-prepare events now bind request_id and page_id/panel_id.
- Engineering runner records UTC start/end, run identity and before/after source hashes.
- Metadata maintenance never writes visual-review outcomes.
- Creative rules and all prior notes are preserved. No install or media submission.

# 0.0.4-engineering.1 (candidate, 2026-10-16)

- 基于 0.0.4 的工程隔离候选，未安装、未发布。
- B3: Excel 片段完整性与自动导出顺序核对。
- B4: 单次检查缓存依赖节点与文件摘要，不跨操作保留。
- B5: 显式提交前准备恢复、唯一台账临时文件及遗留锁诊断。
- B6: 同一原始台账缓冲区解析并计算导出摘要。
- 创作正文、导演/摄影/对白/采用规则及模板保持原字节。
- 仅技术回归，不认证媒体表现；证据随候选交付。

# 0.0.4 候选 · 2026-10-07

渠道：candidate。基于2026-10-05完整三件套内Image9 0.0.3，独立保存；未安装、推送或生成媒体。

增加按需局部静态快检入口，读取指定镜头/接点的必要上下文，只交必要简格输入和范围明确的反馈。完整预演七步、黑白低细节表达及四类参考职责保留，Image9仍为Prompt可选旁路。补局部范围bundle与1×1/小组媒体准备的现有脚本用法；未修改脚本或放宽其声明覆盖检查。每次完整/局部物料交用户确认后人工衔接，不自动采用、改写上游或推进下游。

本轮检查及未验证范围见[VALIDATION.md](VALIDATION.md)。

# 0.0.3 候选 · 2026-10-05

渠道：candidate。来源为用户上传的0.0.2，独立保存；未安装、推送或生成媒体。

恢复Workflow阶段条件；补现有示例辨识轮廓及稳定格映射；整页请求记录版式与完整槽位，独立格保持；修窄屏列数覆盖。 共用生成风险与项目资料更新规则同步为本Skill内置副本，运行不依赖根shared或其他Skill。

实际检查及未验证范围见本目录VALIDATION.md和发行包Validation.md。

## 历史发布文字

以下保留原包记录；其中0.0.2对mapping、语义完整性和生成效果的主张未作为0.0.3验收证据。包外mapping未随材料提供，像素兼容等全称承诺已由本候选收窄。

# 正式发布 0.0.2 · 2026-10-05

渠道：release（正式）。在正式0.0.1基础上优化，三个Skill统一为0.0.2。

- Workflow 改为“目标/输入/必做/禁止/完成判据”短条形态，长例子移至 `examples/Workflow-examples.md`；只改形态，不改规则语义（逐条对照表见包外证据）。
- 四份 Handoff 与四份 speech-and-dialogue 完全统一；引用 promptskill 专属文件处注明“同时安装时以其为准，本Skill运行不依赖”。
- Handoff 采用段新增“采用回显”：Agent依语境判定采用时，先用一句话写明视为已采用的范围与版本；不是新增审批。
- 新增 `references/Generation-executability.md`（生成风险标注与模型友好写法）和可选 `references/Project-bible.md`（跨场/跨集一致性）。
- description 去掉片长/集数限定，改为“剧情类 AIGC 影像（不限片长与集数）”。
- Image9：页面版式可配置（1—4行×1—4列，默认3×3）；`media_flow.py` 支持 `layout`，未写 layout 时行为与0.0.1一致。

# 正式发布 0.0.1 · 2026-10-04

渠道：release（正式）。本次正式编号从0.0.1重新开始，来源为调试总包0.0.9中的组件0.0.7。此前名称含formal的包均作为调试历史保留，不等同本发行。

保留调试组件的简笔预演、四类参考职责、多页身份与实际输入规则；本轮未扩展功能。

历史版本号仍表示对应调试轮次；完整历史记录保留在原0.0.9基线和包外证据目录，不作为本版验证结果。此次未安装、未推送、未生成媒体。
