# Agent怎样接续当前任务

入口、采用与职责回流遵循 [Handoff.md](Handoff.md)。人工采用检查始终必要：先读取实际请求、有效稿和用户反馈；已有状态记录时，再执行对应 context/check。短独立文字任务可直接完成，不以缺少Bundle或状态文件阻塞创作；多场、跨调用任务按下面的轻量记录恢复。

## 可恢复的本地记录

多场、跨Agent或跨调用任务需要恢复文件、采用范围和依赖时，使用 `scripts/workflow_state.py` 保存少量索引：请求、来源文件、逐单元摘要、上游依赖、实际用户反馈及影响范围。短小独立文字任务可直接完成，不强制建项目档案。用户不填写JSON，也不承担把文件从一个Skill复制给另一个Skill的工作。

内部沿用 `suh-delivery/1` 快照。item的id是内容定位，不是表格行号、镜头数或页位置。可选 `depends_on: ["D-r01#S01"]` 指向具体上游单元；可选对象形式为 `{"artifact":"P-r01","unit":"PV01","dimensions":["layout"]}`。部分采用需要item.facets里有对应维度的明确文字；工具回交layout时不附带未采用的photography。facet摘要须由Agent对照实际用户反馈写清，脚本不认识画面，也不鉴别用户身份。

同一项目中，不同集/不同方案的相同单元号用顶层 `lineage` 区分，例如 `EP59-director`；同一稿的修订延续相同lineage与单元ID。未指定时以kind为lineage，该范围内ID须唯一。可选 `source_files:[{"path":"原始来源路径","sha256":"已有预期散列"}]` 绑定真实来源文件；sha256不填则注册时计算。绑定源文件的任意字节变化会保守提示需定位影响，可能暂阻同一产物的多个单元；这不证明每个单元内容已改变或全场需重做。Agent先对照原文定位实际影响，保留未受影响正文，注册当前来源的新快照并依据真实反馈恢复有效范围；不得忽略警报或直接改状态为READY。未绑定的源消息/文件变化只能由Agent读取最新输入发现，不能宣称工具已检测全部来源。

在本Skill目录运行示意（路径和范围须换成实际任务内容）：

```sh
python3 scripts/workflow_state.py init --state /project/Work-context.json --project Project --intent pipeline --evidence-ref user-message-1 --evidence-text '用户实际任务原话'
python3 scripts/workflow_state.py register --state /project/Work-context.json --artifact D-r01 --bundle /project/Director-r01/Bundle.json
python3 scripts/workflow_state.py check --state /project/Work-context.json --target prompt --route mainline --artifact D-r01 --units S01
```

此时未审范围返回WAIT_REVIEW。Agent停在相应人审节点，不先写Prompt再事后登记。

```sh
python3 scripts/workflow_state.py review --state /project/Work-context.json --artifact D-r01 --units S01 --decision approved --evidence-ref actual-user-message --evidence-text '真实采用反馈原话'
python3 scripts/workflow_state.py check --state /project/Work-context.json --target prompt --route mainline --artifact D-r01 --units S01
python3 scripts/workflow_state.py context --state /project/Work-context.json --artifact D-r01 --units S01
```

review是对真实反馈的记录，不是Agent审批按钮，不得虚构原话。没有实际用户反馈就不能执行approved。测试必须标清模拟反馈，不能进入真实项目采用记录。

Prompt成稿的items保留对应director依赖；mainline注册会再次拦住未审依赖。选用预演维度时，先记录它的真实采用范围，再请求该维度context；记录和注册不会改变图片或源剧本。

context同时给出可回查的Bundle/源文件位置；已绑定实际图时返回路径、散列及采用维度，读出时复查实际字节。图只服务这些采用用途，不能由有图推定首尾帧、摄影或动作也已采用；未采用的facet不会进入context正文。像素是否真的满足已采用布局仍须实际观察。

```sh
python3 scripts/workflow_state.py review --state /project/Work-context.json --artifact P-r01 --units PV01 --decision approved --dimensions layout --evidence-ref actual-user-message --evidence-text '仅采用这段布局，摄影不采用'
python3 scripts/workflow_state.py context --state /project/Work-context.json --artifact P-r01 --units PV01 --dimensions layout
python3 scripts/workflow_state.py status --state /project/Work-context.json
```

只改某单元的有效来源时，用invalidate记录该单元及原因；status会追踪真正声明的依赖。新候选注册不自动生效；新版本实际采用后，改变的单元/维度使相应下游过期，未变摘要仍可继续使用。声明依赖可能遗漏，所以Agent仍须复读实际受影响接点，不能以程序未列出便认定无影响。

content包含本单元声明的facets：新局部采用改变某facet时，包含旧值的整内容需协调；采用新整内容时，旧的变化/移除facet不再是当前依据，未变facet及无关单元保持。有效依据选择不等于给新facet新增人审记录，仅采layout仍不能读取未采photography。旧/1台账按真实review事件顺序恢复这一关系，不改历史记录。实际撤回沿有效维度影响依赖；重新采用用新修订及真实反馈，不清除原失效记录。

```sh
python3 scripts/workflow_state.py invalidate --state /project/Work-context.json --artifact D-r01 --units S01 --evidence-ref actual-user-message --evidence-text '本场原文已经变更，原准备稿需更新'
```

文件被就地改写、丢失、未审或失效时不返回可继续结论。注册ID不能覆盖；使用新修订ID及真实文件。已经登记的文件移动需重新明确位置，不猜同名文件。任务意图固定；确有新独立请求可另建带真实请求依据的任务，不能伪造它。

## 记录与真实能力的边界

READY仅表示已声明的文件、依赖与审阅条件满足；不认证语义、艺术质量、用户身份或生成授权。脚本不调度模型、不提交媒体、不改写正文。实际反馈与影响范围仍由Agent读取判断。

状态文件由一个调度Agent负责写，带事件记录和并发写保护；发现锁文件不盲目删除，应判断是否仍有进程/任务在写。已有事实记录不会因新任务或较新文件被自动清空。
