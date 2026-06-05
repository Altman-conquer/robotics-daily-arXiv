import scrapy
import os
import re


class ArxivSpider(scrapy.Spider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categories = os.environ.get("CATEGORIES", "cs.CV")
        categories = categories.split(",")
        # 保存目标分类列表，用于后续验证
        self.target_categories = set(map(str.strip, categories))
        self.start_urls = [
            f"https://arxiv.org/list/{cat}/new" for cat in self.target_categories
        ]  # 起始URL（计算机科学领域的最新论文）

    name = "arxiv"  # 爬虫名称
    allowed_domains = ["arxiv.org"]  # 允许爬取的域名

    @staticmethod
    def clean_text(texts):
        return " ".join(text.strip() for text in texts if text and text.strip())

    @staticmethod
    def strip_descriptor(text, descriptor):
        text = text.strip()
        if text.startswith(descriptor):
            return text[len(descriptor):].strip()
        return text

    def parse(self, response):
        # 提取每篇论文的信息
        anchors = []
        for li in response.css("div[id=dlpage] ul li"):
            href = li.css("a::attr(href)").get()
            if href and "item" in href:
                anchors.append(int(href.split("item")[-1]))

        # 遍历每篇论文的详细信息
        for paper in response.css("dl dt"):
            paper_anchor = paper.css("a[name^='item']::attr(name)").get()
            if not paper_anchor:
                continue
                
            paper_id = int(paper_anchor.split("item")[-1])
            if anchors and paper_id >= anchors[-1]:
                continue

            # 获取论文ID
            abstract_link = paper.css("a[title='Abstract']::attr(href)").get()
            if not abstract_link:
                continue
                
            arxiv_id = abstract_link.split("/")[-1]
            
            # 获取对应的论文描述部分 (dd元素)
            paper_dd = paper.xpath("following-sibling::dd[1]")
            if not paper_dd:
                continue
            
            # 提取论文分类信息 - 在subjects部分
            subjects_text = paper_dd.css(".list-subjects .primary-subject::text").get()
            if not subjects_text:
                # 如果找不到主分类，尝试其他方式获取分类
                subjects_text = paper_dd.css(".list-subjects::text").get()
            
            if subjects_text:
                # 解析分类信息，通常格式如 "Computer Vision and Pattern Recognition (cs.CV)"
                # 提取括号中的分类代码
                categories_in_paper = re.findall(r'\(([^)]+)\)', subjects_text)
                
                # 检查论文分类是否与目标分类有交集
                paper_categories = set(categories_in_paper)
                if paper_categories.intersection(self.target_categories):
                    yield response.follow(
                        abstract_link,
                        callback=self.parse_abs,
                        meta={
                            "arxiv_id": arxiv_id,
                            "categories": list(paper_categories),
                        },
                    )
                    self.logger.info(f"Found paper {arxiv_id} with categories {paper_categories}")
                else:
                    self.logger.debug(f"Skipped paper {arxiv_id} with categories {paper_categories} (not in target {self.target_categories})")
            else:
                # 如果无法获取分类信息，记录警告但仍然返回论文（保持向后兼容）
                self.logger.warning(f"Could not extract categories for paper {arxiv_id}, including anyway")
                yield response.follow(
                    abstract_link,
                    callback=self.parse_abs,
                    meta={
                        "arxiv_id": arxiv_id,
                        "categories": [],
                    },
                )

    def parse_abs(self, response):
        arxiv_id = response.meta["arxiv_id"]

        title = self.strip_descriptor(
            self.clean_text(response.css("h1.title ::text").getall()),
            "Title:",
        )
        summary = self.strip_descriptor(
            self.clean_text(response.css("blockquote.abstract ::text").getall()),
            "Abstract:",
        )
        authors = [
            author.strip()
            for author in response.css("div.authors a::text").getall()
            if author.strip()
        ]
        comment = self.clean_text(response.xpath(
            "//td[contains(concat(' ', normalize-space(@class), ' '), ' label ') "
            "and normalize-space()='Comments:']/following-sibling::td[1]//text()"
        ).getall())

        subjects_text = self.clean_text(response.css("td.subjects ::text").getall())
        categories = re.findall(r"\(([^)]+)\)", subjects_text)
        if not categories:
            categories = response.meta.get("categories", [])

        yield {
            "id": arxiv_id,
            "pdf": f"https://arxiv.org/pdf/{arxiv_id}",
            "abs": f"https://arxiv.org/abs/{arxiv_id}",
            "authors": authors,
            "title": title,
            "categories": categories,
            "comment": comment,
            "summary": summary,
        }
