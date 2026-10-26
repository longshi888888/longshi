# 第二期 GitHub 周榜视频学习：编程 Agent 生态与小隆启发

2026-10-26；revision 1；components-research-1026；lsr-8hd / learn-02。状态：视频分析、官方README及限定许可核查完成；候选建议 proposed，未安装新项目或改现有小隆。

## 实际学习范围

[视频：10.17–10.24 GitHub最火开源项目](https://www.bilibili.com/video/BV1FsHM6yEj3)，约7分59秒，介绍10项并另荐VoiceStudio。已取得公开视频、对完整音轨本地Whisper转写331段、按20秒及11个章节锚点抽35帧，三张采样总览均实际看。非逐帧检查；主体画面是标题/示意机械动画，所述能力未因此成为本机运行验证。名称用作者链接/画面/原项目校正，保留ASR原错误。时间表按作者章节点写“约”，画面切换/旁白可能更早，精准回看以本地索引为准。

简介将榜单截止日写为2026-10-24；未复算其涨星统计。REA与首期重复，仓库分析复用。GitHub未登录API触发403 rate limit，本轮没有补得第二批pushed_at/archived字段；正常公开仓库与raw README/许可证仍可读，已转用并保存URL/分支/内容SHA256。不能把这一批也说成“全部API维护元数据核查通过”。

## 项目与本系统关系

| 章节点 | 项目与本次许可证据 | 实际职责 | 对本项目的取舍 |
| --- | --- | --- | --- |
| 约00:29 | [morluto/rea](https://github.com/morluto/rea)；MIT，复用首期实际文本 | 取证/逆向；首期已分析，本期只复核新视频内容 | 保持授权资料/公开实现优先，不重复安装或扩大ERP接入 |
| 约01:00 | [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official)；根仓库Apache-2.0；每个插件另核 | 官方/第三方插件目录及统一清单结构 | 可借鉴插件元数据和能力入口；官方收录不等于每个MCP/代码均由官方控制，也不等于插件天然适配当前宿主 |
| 约01:48 | [ruvnet/ruflo](https://github.com/ruvnet/ruflo)；README/GitHub标MIT；本次root许可证原文未取得 | Agent harness：任务/记忆/工具/控制台和宿主集成 | 可学任务可视化与成本/动作分级；Codex侧MCP不自动等于Claude侧全部钩子/控制台能力，不启用新swarm |
| 约02:31 | [android/skills](https://github.com/android/skills)；Apache-2.0，实际文本 | 针对Android模型薄弱项的技能 | 最值得学的是用失败评测选技能；当前Windows主线不因此改成原生Android开发 |
| 约03:16 | [anomalyco/opencode](https://github.com/anomalyco/opencode)；MIT，实际文本；默认master | 可换模型的编程Agent/客户端 | 可比较plan/build与供应商接口分离；开源客户端不代表模型调用免费，也未测试替换当前Codex |
| 约03:56 | [stablyai/orca](https://github.com/stablyai/orca)；MIT，实际文本；默认master | 独立worktree中的多Agent任务、设计批注及手机接续 | 隔离工作区、比对成果、明确合并责任有启发；本轮不新增对话/代理，不把并行个数当正确性 |
| 约04:41 | [cursor/plugins](https://github.com/cursor/plugins)；README写MIT；插件分别有LICENSE，root原文未取得 | 插件清单/规则/技能/MCP与集成目录 | 适合借鉴工具注册、输入输出及小型能力包；宿主专有规则和外部服务授权需独立适配 |
| 约05:23 | [akitaonrails/ai-memory](https://github.com/akitaonrails/ai-memory)；MIT，实际文本 | 跨编程工具/项目/机器的记忆与显式交接 | 本项先概览，用户截图指定的深入研究紧接下一项；当前支持矩阵Native Windows为Experimental，WSL2为Supported |
| 约06:11 | [HKUDS/CLI-Anything](https://github.com/HKUDS/CLI-Anything)；Apache-2.0，实际文本 | 分析软件源代码/API并生成结构化CLI外壳 | 值得借鉴“可枚举工具＋JSON结果＋错误码＋回执”；不是给任何闭源EXE一句话就获得可用/获准自动化接口 |
| 约06:54 | [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI)；GPLv3，实际文本；默认master | 节点工作流、生成引擎、本地API与工作流元数据 | 未来小隆角色素材/演示可比较；节点/模型权重另核，低显存宣传不能覆盖所有模型和速度 |
| 约07:38加荐 | [debpalash/VoiceStudio](https://github.com/debpalash/VoiceStudio)；AGPLv3，实际文本 | 本地语音生成/设计、配音、转写及API/MCP | 对小隆固定音色/本地语音有潜在价值；当前README已为Electron，v0.5.3是最后Tauri版本，模型体积/每语种质量另测 |

## 本期最值得保留的设计

1. **能力扩展采用小型清单和受控接口**：把工具名、适用场景、必要输入、权限/外送、输出结构、失败和回执写清，再由宿主决定是否能执行。Claude/Cursor/Android插件都采用文件式能力描述，但它们的插件格式、运行时及权限机制不因此完全通用。现有技能须遵守本项目目录和最多三问等约定。
2. **先设计交接内容，再谈跨工具自动记忆**：交接应能回答“当前目标/已确认依据/试过什么/已有成果/尚未解决/下一步”，还要区分拥有者、项目身份与来源版本。记忆、任务队列与跨窗口信箱的职责继续分开；不是把一段聊天摘要写入数据库就已经实现自动接续。ai-memory的细节见下一项，当前不替换既有Memory/Beads/Hardline。
3. **外部软件自动化优先找可验证接口**：先用已有库、CLI、公开/获准API，再评估薄适配层或UI操作。CLI-Anything七步流程包含读源码、设计、实现、测试和文档，原软件/后端仍需存在；它并不自动证明能无授权操控闭源ERP。给小隆增加工具时，优先返回结构化结果、来源和执行回执，支持预览/防重/失败可诊断。
4. **并行需要隔离和合并规则**：Orca独立worktree及Ruflo控制台可启发任务归属与成果对照；同一项目同时写一份文件仍会冲突，五个Agent不保证五倍速度。当前沿用户指定的窗口/任务，不因为视频出现“蜂群”就自行新建代理或全面换平台。
5. **工作流和输出一起保存**：ComfyUI把参数、模型、随机种子等随结果保留的思路，适合小隆的生成产物与技术演示追溯；模型版本、节点和硬件仍影响复现，不能只留一个漂亮截图就声称可重复。VoiceStudio可为后续语音能力比较提供候选，本机现有朗读/识别继续保留，各语种和实际麦克风效果另测。

## 核实到的重要边界

- ai-memory README明确 Native Windows 是 Experimental，WSL2受支持。此机此前无可用WSL，已有QEMU/Alpine软件实验环境；原生自动钩子/安装与当前桌面客户端能否完整配合，不能由“支持Codex”几个字代替。本轮只读，没有安装它。
- 官方插件目录 README 自己要求逐插件信任与核查；根LICENSE不能覆盖外链插件、MCP服务或账户费用。Ruflo与Cursor根许可文件读取未成功，分别仅能记录README/GitHub的MIT声明，不伪造下载成功。
- CLI-Anything依赖可用源代码、API或具体软件后端；各适配器质量与真实运行环境不相同。ComfyUI“4G显存＋8G内存”等是特定实现/模型条件的项目宣传，未在本机验证，不能推广到所有生成模型。
- VoiceStudio目前README写明Electron是唯一桌面/网页UI，v0.5.3为最后Tauri；视频截图/旧说明里的版本或技术架构不可直接用于当前选型。其模型权重、音色和输出条件与应用AGPL许可分开。

原文、许可和视频处理证据在工具箱项目外 `outputs/github-video-study-20261026/upstream-second/` 与 `BV1FsHM6yEj3-study/`。本轮未执行任何仓库安装说明、没有启用新多Agent、没有接公司资料/生产系统，也没有更改正式业务开发状态。下一项按队列深入用户截图的 ai-memory。
