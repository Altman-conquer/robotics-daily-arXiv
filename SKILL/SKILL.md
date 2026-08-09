---
name: embodied-ai-daily
version: 0.2
description: 通过 URL 请求，从 Embodied AI Daily 获取具身智能论文 JSON 数据
---

# arXiv论文数据API

## 触发条件
用户想要获取 Embodied AI Daily 中的具身智能论文数据

## 功能说明
通过URL参数获取JSON格式的arXiv论文数据

## 基础仓库 URL
https://altman-conquer.github.io/robotics-daily-arXiv/

## URL参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `category` | arXiv类别 | `cs.CV`, `cs.AI`, etc. |
| `author` | 作者姓名 | `Smith` |
| `keywords` | 关键词，逗号分隔 | `vision,learning` |

## 样例
```
bash scripts/fetch.sh "https://altman-conquer.github.io/robotics-daily-arXiv/?category=cs.RO&author=Smith&keywords=manipulation"
```
这里使用到了`fetch.sh`脚本来发送请求并处理响应数据，该脚本基于NodeJS和puppeteer环境，如果没有安装则会自动安装。你不能直接wget或curl这个url，因为它需要执行JavaScript来生成最终的JSON响应。

## 筛选逻辑

```
category AND (keywords OR author)
```

- category: 硬筛选，只返回指定类别
- keywords: 在标题和摘要中搜索
- author: 在作者字段中搜索
- keywords与author是"或"关系

## JSON响应结构

```json
{
  "category": "cs.CV",
  "author": "Smith",
  "keywords": ["deep"],
  "count": 10,
  "papers": [
    {
      "id": "2401.00001",
      "title": "标题",
      "authors": "作者1, 作者2",
      "categories": ["cs.CV"],
      "summary": "tldr",
      "date": "2024-01-01",
      "url": "https://arxiv.org/abs/2401.00001"
    }
  ]
}
```
