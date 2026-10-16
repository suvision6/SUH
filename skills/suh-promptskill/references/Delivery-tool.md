# 可选的本地交付器

先按 Skill 做完整专业创作与回读，再由 Agent 整理交付数据。用户提供自然剧本、导演稿或素材即可，不要求用户填 JSON。普通单条任务可直接交 Markdown／纯文本；批量需要来源清单、对白原字派生和版本比对时使用本工具。它不理解剧本、不代替创作、不调用生成服务。

## 数据与执行

```json
{
  "format": "suh-delivery/1",
  "kind": "prompt",
  "title": "走廊补拍",
  "source_units": [{"id": "S01", "text": "她停在门外，说别开灯；门保持关闭。"}],
  "dialogue": [{"id": "D01", "speaker": "她", "text": "别开灯。", "placement": "画内"}],
  "items": [{"id": "G01", "source_ids": ["S01"], "body": "她停在关闭的门外，手没有碰门把。[dialogue:D01] 门仍关闭。"}]
}
```

`kind` 为 `scene`、`previs` 或 `prompt`。`source_units` 是执行者从有效来源整理的事实核对清单，不是脚本自动读出的剧情。逐项与原稿回查后才交给工具；范围编号须展开为实际 ID。`dialogue` 按有效成片发言顺序列出每次发言，相同台词发生两次也有两个 ID；应用已授权人工修订，保留疑似错字。无对白用空数组。

`body` 为已写好的主稿或提示词，可选交付器的内部数据以 `[dialogue:D01]` 引用整次发言；合法跨段发言可用下面的片段形式。上例只展示内部引用关系，不是正式Prompt样稿。工具展开角色、声位和原字台词；最终Prompt按[Output-format](Output-format.md)在发生处写 `角色（声位，已知语言）说：{原字台词}`，不能把D编号或未展开标记交给用户代读，其他类型使用中文引号。全体 body 中每次发言的原字内容须按表中顺序完整出现一次。不得为通过校验而删改原稿或虚构来源。

`previs` 通常每页一个 item，body 包含本页各格的声画、同镜/切镜关系；`copy_text` 放自足的整页绘图输入，避免台词被当作字幕。`scene` 可按场或场内连续段落成项。`prompt` 每个生成单位一项，其复制文本直接从 body 派生，禁止另给 copy_text 造成两份正文。其他项目条件与采用范围写在实际主稿及交接说明中，脚本不会自动决定它们。

从包目录运行：

```sh
python3 scripts/deliver.py /absolute/path/Input.json --out /absolute/path/Delivery-r01
python3 scripts/deliver.py /absolute/path/Revision.json --out /absolute/path/Delivery-r02 --previous /absolute/path/Delivery-r01/Bundle.json
```

生成 `Master.md`、`Bundle.json`、`Checks.json`、`items/ID.md` 与 `copy/ID.txt`。新目录必须不存在，旧目录不会覆盖；写后按字节读回，记录文件散列。版本比较列出增删改及未变项；它不推断创作依赖，执行者仍须复核前后接点。输入有误时先修数据或交付内容，不反改用户原件；写盘中断时保留已有部分，改用另一新目录重交并如实说明。

## 能检查与不能检查

可检查：清单 ID 有效和覆盖、占位对白实例次数与顺序、同实例的原字片段完整复组、原字派生、复制文本一致、文件写后完整、修订文本范围。

`dialogue_counts` 列出每次发言的字面汉字数，排除标点和角色标签，供核对人工估时计算。数字读法、英文/缩写、方言、特殊停顿仍须另算；字数不是实际口播时长，也不会自动替用户选择语速。

不能检查：清单是否漏抄原稿、未使用占位而手写的对白、语义／空间／艺术合理性、说话实际持续时间、真实口型或运动、跨段媒体连续性、用户是否采用。不得把 `pass` 写成导演、媒体或人工验收通过。

## 同一次发言的跨段原字复组

`[dialogue:D01@0:5]` 表示D01原字文本从字符0到字符5之前的半开区间。计数是Python Unicode字符，不是汉字数、字节数、秒数或用户眼中的合字；标点、空格和换行均原样计入。不自行Unicode正规化，不给片段补标点。Agent从已写的有效稿整理区间，用户无需计算或填写。

例如D01=`先别开门，等我回来。`（10个字符），G01写 `[dialogue:D01@0:5]`，G02写 `[dialogue:D01@5:10]`，分别展开为 `甲（画内）说：{先别开门，}` 和 `甲（画内）继续说：{等我回来。}`。后一项的“继续”指同一次发言，不授权停顿或重新起句。真实跨生成接声能力仍待媒体验证。

每次发言必须独立ID；相同“嗯。”出现两次应为D01和D02，不能用一个ID引用两次。工具按items排列及body中标记顺序逐次展开，同一实例须从0开始、无间隙无重叠到末尾，完成后才能进入下一实例。缺片、重片、反序、越界、空区间、跨句区间与同ID整句/片段混用均拒绝。连续同一句跨镜可在同一item内用多个标记，也可跨item，格式不决定镜头或生成段数。

若采用的跨镜安排使D01在G02转为画外持续，可在G02声明 `"dialogue_placements":{"D01":"画外持续"}`；只覆盖本项的声位文字，不换说者、不换原词。使用前Agent须逐项核对采用安排；工具只验证对应已出现ID及非空文字，不能判定画面中人物是否实际可见。一个item内声位又变化时，用正文明确变化发生处，或用自然稿交付；不能为了该字典的粒度而拆出新的生成单位。

授权改词先更新对应有效发言实例，然后重新定位它的所有片段偏移；不得沿用旧偏移造成漏字。用 `--previous` 比较实际改变的单元，再专业复读相邻接点。工具不认证改词是否真正获得人类授权。

真正的重叠对话、抢话或跨句交错声轨超出此线性复组模式时，用自然声画稿/分轨说明保留设计，并明确该项未获本工具顺序认证；不能为了通过而改写成轮流说话。`save_prompts.py`仍可原样保存已经核对的正文。

## 与调度记录及可读载体连接

主线先按[Workflow-state.md](Workflow-state.md)检查采用，再创作正文；导出以后才登记实际Bundle及依赖。可选 `items[].depends_on` 指向真实上游 `artifact#unit`；`conditions`保存当前确有依据的条件，`facets`用于确有部分维度采用的明确摘要。`deliver.py`原样保存这些声明但不判断其语义，状态工具负责对应注册检查。

`review_delivery.py`可从同一Bundle派生Excel/固定HTML样稿并读取返还差异；运行接口以包内`--help`为准。载体生成及片段复组不会授予采用权限、不会提交生成，也不锁定默认载体；Prompt正文规范已经确定。TXT是按需复制附件；用户面对的是完整可审内容，而非内部JSON台账。

## 正式正文的最小结构检查

`check_prompt_contract.py`只读取Agent从实际上下文及最终正文整理的最小声明，不写文件，不要求用户填表。它独立于上述Bundle；先完成正文演读，再从包目录运行：

```sh
python3 scripts/check_prompt_contract.py --input /absolute/path/Context.json
```

下面仅示意机器输入，路径和总长应取真实交付值：

```json
{"format":"suh-prompt-contract/1","has_storyboard":true,"timestamp_policy":"required","units":[{"id":"G01","total_duration_seconds":"8","prompt_path":"copy/G01.txt"}]}
```

每项可将 `prompt_path` 换成互斥的 `prompt_text` 完整正文；相对路径以Context文件所在目录为准。有分镜默认 `required`。用户明确不用时间戳时用 `explicit_user_omission`，并提供 `timestamp_omission` 的 `role: "user"`、实际消息定位 `source`、原话节选 `excerpt`；保留Cut编号及符合profile的整数秒总长。程序只检查这些证据字段存在且非空，不认证原话、语义或授权真实性。无分镜用 `has_storyboard: false` 和 `timestamp_policy: "not_applicable"`，自然段无Cut合法；未要求估时、未给提交总长的非提交草稿可省略总长，若已写时间范围则需总长核对连续性。一旦给出提交总长，仍须为profile范围内整数秒；各Cut自身时长（含末Cut）及切换点可小数。

默认读取本包[Generation-profile.json](Generation-profile.json)，Context/Bundle不需要增加入口表单。未来已核对实际入口时，可用 `--profile /absolute/Profile.json` 显式选择对应profile；其schema为 `suh-generation-profile/1`，记录 `id`、`scope`、`duration_seconds` 的 `min/max` 及 `source` 的 `kind/reference/summary`。替换profile不会取消整段duration整数约束；没有依据不能自行改profile绕过限制。

结果只向stdout输出JSON：退出0是窄范围通过，1包括正文结构、小数总长或超出所选范围，2是输入/profile错误。报告包含适用profile及来源声明、整段总长规则和逐单元检查。它可查区块、Cut计划接续、整数总长及声明范围，但不能认证实际入口能力、profile对真实平台的适用性、语义、艺术、合理估时、用户实际采用或媒体表现；不能用PASS替代专业演读。
