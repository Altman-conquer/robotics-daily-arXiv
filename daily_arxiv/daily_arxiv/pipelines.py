# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
import arxiv
import json
import os
import sys
from datetime import datetime, timedelta


class DailyArxivPipeline:
    def __init__(self):
        self.page_size = 100
        self.client = arxiv.Client(self.page_size)

    def process_item(self, item: dict, spider):
        item["pdf"] = f"https://arxiv.org/pdf/{item['id']}"
        item["abs"] = f"https://arxiv.org/abs/{item['id']}"

        required_fields = ("authors", "title", "categories", "summary")
        if all(item.get(field) for field in required_fields):
            item.setdefault("comment", "")
            return item

        search = arxiv.Search(
            id_list=[item["id"]],
        )
        try:
            paper = next(self.client.results(search))
        except Exception as exc:
            spider.logger.warning(
                "Failed to fetch arXiv API metadata for %s: %s",
                item["id"],
                exc,
            )
            return item

        item["authors"] = [a.name for a in paper.authors]
        item["title"] = paper.title
        item["categories"] = paper.categories
        item["comment"] = paper.comment
        item["summary"] = paper.summary
        return item
