# 本地媒体工具

`scripts/media_flow.py`只写本地文件，不生成图片、不调用provider、不安装。Python 3.9+；无图片参考的准备、台账读写和HTML嵌入已登记PNG使用标准库；含图片参考的准备、图片登记与归档解码需Pillow；PDF需Pillow、ReportLab及本地可嵌入TrueType字体。没有库时使用已有正确运行环境，不默认安装。

## 从自然主稿整理内部快照

沿用Delivery-tool的`suh-delivery/1`，kind=previs，主稿声画写items.body，对白展开仍用既有规则。追加media，不让用户手填：

```json
{
  "media": {
    "panels": [{
      "id": "F001", "shot_id": "PV01", "source_shot_id": "C01",
      "source_ids": ["S01"], "moment": "递信前，尚未接触",
      "relation": "first",
      "current_input": "白纸黑白导演简笔，粗略大形、低细节脸和简化衣服，仅必要浅灰；背景留桌面结构与接触关系。本轮无图片参考。平视中景；甲站桌左，右手捏住信角，乙双手停在身前未碰纸；桌在两人之间。净图无生产文字。",
      "facets": {"layout": "甲桌左乙桌右，桌面在中间", "photography": "平视中景"},
      "depends_on": ["Scene-r01#S01"]
    }],
    "pages": [{"id": "P01", "item_id": "Page1", "slots": ["F001", null, null, null, null, null, null, null, null]}]
  }
}
```

上例只展示扩展，不能独立当完整bundle。每格current_input自足，不把全场变化档案混进去；每页item.copy_text也是完整页输入。source_shot_id只有真实精确源镜才填；关系为first/same_shot/cut/ellipsis/alternative，同刻备选不推进时间。每个稳定格ID只占一槽，所有有效格恰好出现一次，未用槽为null。

完整预演页版式默认3×3；可在该页添加 `layout: {"rows": 2, "cols": 2}`，行列各为1—4，slots长度等于行×列。调整行列、格序或空槽位置时，Agent同步该页copy_text中的排布和逐槽内容；工具原样取正文，不替作者改写。prepare为整页保存page_assembly（规范化行列及含null的完整slots），纳入请求摘要；省略layout与显式3×3视为相同版式。单格请求不带此装配字段。

局部快检无需改脚本：按[Delivery-tool.md](Delivery-tool.md)准备独立范围bundle；媒体台账仍需一个页记录来定位，但单格用layout为1×1、slots为该格ID，双格可用1×2，不补九槽。准备单格用panel_id，准备小组用page_id；页正文与实际layout一致。status或export覆盖了这份局部bundle的所有格，只代表本次范围，不代表原整场全部镜头。

## 命令与操作

命令中的`<root>`是本候选包完整路径；`<python>`是已具备必要库的实际环境。操作文件由Agent填写，是调用记录，不是用户表单。所有路径用真实完整路径。

```text
<python> <root>/scripts/media_flow.py init --bundle <Bundle.json> --workspace <新的媒体目录>
<python> <root>/scripts/media_flow.py apply --workspace <媒体目录> --operation <操作.json>
<python> <root>/scripts/media_flow.py status --workspace <媒体目录>
<python> <root>/scripts/media_flow.py export --workspace <媒体目录> --out <新的比较目录> --stage review --formats html pdf
```

init只建记录不出图，目录必须新建。`--test-mode`仅用于明确技术夹具，所有导出显示SYNTHETIC TEST；不可用于真实用户作品伪造采用。每次操作独占精确Ledger.lock文件，避免并发覆盖；异常中断遗留锁／Ledger-next.json时先核对任务和文件，不盲删重跑。Snapshots保存导入稿；Assets保留原字节及逐格r修订；Requests/Responses保留实际输入和可取得回包。状态写入原子替换，未改图不覆盖。

操作最小字段：

| action | 必要字段与作用 |
|---|---|
| prepare | id；page_id或panel_id二选一；references可选[{path,purpose}]；parameters按实际工具填写。保存完整请求，整页另存page_assembly，返回input_sha256；purpose单独保存，不自动加入prompt，先按Input-and-delivery写入正文。 |
| authorize | request_id、panel_ids必须精确匹配准备范围；evidence_ref、evidence_text为实际用户消息及原话。 |
| start | request_id、tool、capabilities（本次实际工具暴露能力）、attached_references（实际传入文件的sha256列表）。在宿主调用前记submitting。 |
| result | request_id、status=submitted/unknown/succeeded/failed/cancelled；record_ref是实际回包引用；可有task_id、model_reported、response_file。字段未暴露不猜。 |
| register | request_id＋image实际路径；整页须boxes={稳定格ID:[left,top,right,bottom]}。成功仅登记一次；自动生成新r版本。 |
| archive | request_id＋image实际返回路径，仅限已知成功且输入已过期。panel_ids可选，默认原请求全部目标；原字节与原basis保存在Archived，不创建/选中当前格版本。分批归档只释放已收回范围。 |
| register（已有图） | 无request_id；origin=user_supplied、panel_ids、image、evidence_ref、evidence_text。不能把用户图伪造为本次生成；synthetic_fixture只限test-mode。多格仍需boxes。 |
| observe | panel_ids、status=checked/needs_changes/not_visible、observed具体观察、view_ref实际查看证据。写入当前图版本，不产生用户采用。 |
| adopt | panel_ids、dimensions、decision=approved/changes_requested、evidence_ref/text。每个维度须在对应格facets中有文字；content用于完整已采用描述，不能只写“通过”；记录器不认证用户身份。 |
| select | panel_id、revision。可选回历史图，但过期或缺采用仍阻止adopted导出。 |
| sync | bundle为新有效稿路径；更新当前依据，新旧稿快照并存；变更的格／整页执行输入使旧图待核。新增／删除格需新媒体目录，避免隐式身份迁移。 |
| resolve-derivation | items=[{item_id,outcome,note}]；只处理待核页。outcome=updated须已同步该页copy及受影响格输入；no_visual_change须两者均未改。note写专业检查依据；不是人类采用，也不自动重生。 |

示例操作（示例证据不能用于生产）：

```json
{"action":"prepare","id":"Q01","page_id":"P01","parameters":{"aspect":"16:9"}}
```

参数示例不是任何provider保证；必须按实际宿主schema转入。

修改正文后先sync，再按Media-execution的派生协调完成专业检查。例如`{"action":"resolve-derivation","items":[{"item_id":"Page1","outcome":"no_visual_change","note":"仅修画外对白标点，时点、可见行为及绘图文本保持"}]}`。例中结论必须来自实际检查，不能为绕过待核照抄。字面应用器的derivation_pending随候选保存；媒体台账按当前body摘要记录已处理结果，后续同步同一候选不重复待核。单独文字任务依专业修订直接交完整新稿，不强制启用台账。

archive在原图保存后、台账提交前中断，可对相同请求和实际返回文件重做；同路径按字节核对，不重新调用provider。原请求及回包仍保留；归档不能把旧输入结果冒充当前成功。

旧整页请求没有page_assembly时，装配依据不可核实：status显示input_current=false及legacy_page_assembly_missing=true，关联图版本标page_assembly_unverified。review仍保留并展示可读历史图与此说明；adopted导出和把旧请求结果登记为当前会受阻。这不是判定图片错误，也不删除或撤销历史采用，不自动重生。未提交请求按当前完整依据另建prepare；已提交或状态未知仍先查询/回收，已知成功的旧结果可archive。不得把当前行列与slots补进旧请求冒充历史依据。原本独立准备的单格请求不受缺少整页字段影响；单纯改分页不改变稳定格basis。正文变更仍按既有派生协调处理。

## 导出与范围

`--stage review`可以导出当前范围，缺图标MISSING，未用槽标UNUSED；不画合成占位冒充真实图。`--pages P02`明确部分范围。`--stage adopted --dimensions layout`要求范围内每个有效格均有当前真实图、未损坏字节及本维度有效采用；缺图／过期／仅Agent checked均阻止采用版导出。所需维度不填时默认content，只有明确整内容采用并有facet时才用。

PDF使用`--font <本地字体.ttf>`，默认尝试macOS Arial Unicode；不分发字体。中文字覆盖不足或长标签超出保留区时报具体错误，不悄悄截断。主稿保完整内容，PDF只放定位和短时点；HTML显示同范围同图，并无网页反馈保存功能。

登记写图后、台账提交前中断时，重新执行相同register会按每个r版本的receipt核对来源原图、当前依据、请求、裁框和PNG字节；完全相同则复用已写文件完成台账，不创建第二个r版本，也不重新提交provider。任一字节或依据不同则拒绝覆盖并保留旧文件。成功登记后再次register仍拒绝，防止重复记账。

Export.json记录真实图hash、修订、范围、问题和运行时间；adopted额外生成Adopted-bundle.json以同一证据回交全流程。content采用输出到完整body，输出facets只包含非content维度，兼容workflow_state的content保留语义；layout-only包与context不含未采用摄影。文件hash通过只证明文件一致；真实看图、人类采用、艺术效果分别处理。


## 工程候选：提交前准备恢复

正常 prepare/authorize/start/result 用法保持。新增 prepare 请求将创建时的原始 Ledger 摘要写入 prepared_from_ledger_sha256；此元数据不改变 input_sha256 或已有请求的正常执行。

仅在执行者有真实记录确认“请求旁文件已经写入、台账未提交、宿主尚未调用”的本地中断时，可通过原 apply 入口执行 recover-prepare。使用原 id、相同 page_id 或 panel_id、相同 parameters 和 references，另传 interruption=before_host_submission 以及真实 evidence_ref/evidence_text。脚本重算当前输入与参考摘要，对照原 Requests 文件和准确的原台账摘要后，仅恢复 prepared 台账记录；保留原创建时间和请求原字节，记录恢复证据。不授予授权、不调用宿主、不生成或重试媒体。重复恢复不新增请求或事件。

原台账已经变化、旧请求缺少该准备摘要、请求损坏或内容不同、出现回包/归档证据、已有请求进入 submitting/submitted/unknown 等情况均拒绝恢复。无法确认提交历史时先查询和回收原调用；不能把 Requests 中初次保存的 prepared 当成从未提交的证明。脚本核验声明和本地字节，不能认证操作者陈述或外部宿主历史。

台账提交使用本次独占 Ledger-*.tmp 再原子替换。遗留 Ledger-next.json 和旧临时文件保留供核对，不自动合并、覆盖或清理。遗留 Ledger.lock 会明确阻止写操作；先核对原执行者已经停止，再只处理明确的那一个锁文件，不按年龄自动清锁。本路径处理进程中断，未认证断电级持久性。

## 工程候选：导出快照

每次 export 从同一份 Ledger 原始字节解析状态并计算 ledger_sha256；HTML/PDF、Export.json 和 Adopted-bundle.json 共同引用读取时的状态。导出期间若台账推进，本次仍属于该历史快照，需要新版时另行导出。严格 JSON 校验保持；快照摘要不证明艺术、实际看听或用户身份。
