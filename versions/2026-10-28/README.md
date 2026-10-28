# SUH 2026-10-28 版本快照

本目录保存 2026-10-28 从当前已安装 SUH 四个 Skill 直接复制的完整运行包。根目录 `skills/` 继续保留 2026-10-16 发布内容，不被本快照覆盖。

| Skill | 明确调用名称 | 版本 |
| --- | --- | --- |
| 美术 | `$suh-art` | `0.0.3-execution.1` |
| 场级导演 | `$suh-fenjingskill` | `0.0.5-execution.1` |
| 叙事动态预演 | `$suh-image9` | `0.0.4-engineering.3.handoff.1` |
| 视频 Prompt | `$suh-promptskill` | `0.0.4-prompt.3.engineering.1.handoff.1` |

调用策略沿用各包 `agents/openai.yaml`：场级导演、Image9 和 Prompt 为仅显式调用；美术沿用原安装策略。四个入口分别独立，不使用自动总控。

本快照包含四个 Skill 目录下的全部 166 个文件，并与当前已安装目录逐字节一致。清单见 [MANIFEST.json](MANIFEST.json)。快照不包含安装备份、测试输出、用户创作物料、媒体文件或凭据。

文件一致性不等于创意质量、媒体生成、原生选择器或长期稳定性验收。
