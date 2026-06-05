import unittest

from scrapy.http import HtmlResponse, Request

from daily_arxiv.daily_arxiv.spiders.arxiv import ArxivSpider


ABS_HTML = """
<html>
  <body>
    <h1 class="title mathjax"><span class="descriptor">Title:</span>Robot Policy Learning</h1>
    <div class="authors">
      <span class="descriptor">Authors:</span>
      <a>Ada Lovelace</a>, <a>Alan Turing</a>
    </div>
    <blockquote class="abstract mathjax">
      <span class="descriptor">Abstract:</span>
      We train a useful robot policy.
    </blockquote>
    <table>
      <tr>
        <td class="tablecell label">Comments:</td>
        <td class="tablecell comments mathjax">8 pages</td>
      </tr>
      <tr>
        <td class="tablecell label">Subjects:</td>
        <td class="tablecell subjects">
          <span class="primary-subject">Robotics (cs.RO)</span>;
          Machine Learning (cs.LG)
        </td>
      </tr>
    </table>
  </body>
</html>
"""


class ArxivSpiderTest(unittest.TestCase):
    def test_parse_abs_returns_full_item_without_api(self):
        spider = ArxivSpider()
        request = Request(
            "https://arxiv.org/abs/2606.00001",
            meta={"arxiv_id": "2606.00001", "categories": ["cs.RO"]},
        )
        response = HtmlResponse(
            url=request.url,
            body=ABS_HTML.encode(),
            encoding="utf-8",
            request=request,
        )

        item = next(spider.parse_abs(response))

        self.assertEqual(item["id"], "2606.00001")
        self.assertEqual(item["title"], "Robot Policy Learning")
        self.assertEqual(item["authors"], ["Ada Lovelace", "Alan Turing"])
        self.assertEqual(item["summary"], "We train a useful robot policy.")
        self.assertEqual(item["categories"], ["cs.RO", "cs.LG"])
        self.assertEqual(item["comment"], "8 pages")


if __name__ == "__main__":
    unittest.main()
