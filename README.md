<div align="center">
  <img src="assets/embodied-ai-daily-mark.svg" width="88" alt="Embodied AI Daily logo">
  <h1>Embodied AI Daily | 具身智能论文日报</h1>
  <p>面向具身智能、机器人学习、VLA 与世界模型的每日 arXiv 论文检索和 AI 辅助阅读站。</p>
  <p>
    <a href="https://altman-conquer.github.io/robotics-daily-arXiv/">在线阅读</a> ·
    <a href="https://github.com/Altman-conquer/robotics-daily-arXiv/actions/workflows/run.yml">运行状态</a> ·
    <a href="https://github.com/Altman-conquer/robotics-daily-arXiv/issues">问题反馈</a>
  </p>
</div>

## 项目定位

这是由 [Altman-conquer](https://github.com/Altman-conquer) 独立维护的具身智能论文日报。项目每天从 `cs.RO`、`cs.AI`、`cs.LG`、`cs.CV` 抓取候选论文，先进行语义主题过滤，再为保留论文生成中文摘要、动机、方法、结果和结论。

重点覆盖：

- Vision-Language-Action（VLA）、机器人基础模型和世界模型
- 操作、灵巧操作、抓取、运动、导航和具身规划
- 机器人策略学习、视觉运动控制、模仿学习和强化学习
- Sim-to-Real、遥操作、Physical AI、具身数据集与评测
- 与物理智能直接相关的自动驾驶感知、规划和控制

通用计算机视觉、纯 NLP、通用 LLM 推理、图像生成或没有明确物理交互对象的工作会被过滤，减少信息噪声。

## 自动更新

GitHub Actions 工作流每天北京时间 `09:30` 自动执行：

1. 从 arXiv 抓取候选论文；
2. 与最近 7 天数据去重；
3. 用 LLM 筛选具身智能相关论文；
4. 并发生成结构化中文解读；
5. 生成 Markdown，并将结果发布到独立的 `data` 分支；
6. GitHub Pages 从 `main` 分支提供阅读界面。

当前 AI 配置为 `gpt-5.6-luna`，推理强度为 `medium`。工作流设置了并发保护和 `330` 分钟硬超时；相比旧版对所有论文串行处理，主题过滤和并发处理可显著降低运行时间。

## 部署

仓库需要以下 Actions Secrets：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`

主要 Actions Variables：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `CATEGORIES` | `cs.RO,cs.AI,cs.LG,cs.CV` | arXiv 候选类别 |
| `LANGUAGE` | `Chinese` | 生成语言 |
| `MODEL_NAME` | `gpt-5.6-luna` | 筛选和摘要模型 |
| `REASONING_EFFORT` | `medium` | 推理强度 |
| `AI_MAX_WORKERS` | `6` | 摘要并发数 |
| `TOPIC_FILTER_ENABLED` | `true` | 启用主题过滤 |
| `TOPIC_FILTER_MAX_WORKERS` | `3` | 主题筛选并发数 |
| `TOPIC_FILTER_KEEP_UNCERTAIN` | `false` | 是否保留低置信度负例 |

在 Actions 页面选择 `Embodied AI Daily` 可手动运行。当天数据已经存在时默认跳过；需要完整重跑时启用 `force_reprocess`。

本地 Docker 仅作为 GitHub Actions 不可用时的后备方案，配置与运行方式见 [docs/docker-local.md](docs/docker-local.md)。密钥文件 `.env.docker.local` 已被 Git 忽略，不应提交到仓库。

## 数据与免责声明

网站展示内容由模型根据论文元数据和摘要自动生成，可能存在遗漏或错误；研究结论应以 arXiv 原文为准。论文版权归原作者所有，本项目只保存公开元数据和辅助解读。

## 独立维护与致谢

本项目从 [dw-dengwei/daily-arXiv-ai-enhanced](https://github.com/dw-dengwei/daily-arXiv-ai-enhanced) 演进而来，保留原始 Git 历史和贡献记录，并在其 Apache-2.0 许可下继续开发。当前的具身智能主题策略、并发流水线、数据分支和品牌由本仓库独立维护；上游项目不对本部署、内容或运营负责。

## License

[Apache License 2.0](LICENSE)
