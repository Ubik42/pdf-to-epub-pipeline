import unittest

from scripts.build_epub import Section, add_navigation_targets, printed_toc, style_semantic_blocks


class EpubStructureTests(unittest.TestCase):
    def test_printed_contents_define_navigation(self):
        source = (
            "- 第2章 线性规划 …… 17\n"
            "- 2.1 数学模型 …… 17\n"
            "- 2.2 标准型 …… 23\n"
            "- 习题 …… 68\n"
            "# 第1章 绪论\n"
        )
        self.assertEqual(printed_toc(source), {2: ["2.1", "2.2"]})

    def test_only_printed_sections_get_bookmarks(self):
        section = Section(
            "第2章 线性规划",
            "## 2.1 数学模型\n## 2.2 标准型\n## 2.13 习题题号\n## 习题",
        )
        content = "<h2>2.1 数学模型</h2><h2>2.2 标准型</h2><h2>2.13 习题题号</h2><h2>习题</h2>"
        result, targets = add_navigation_targets(content, section, ["2.1", "2.2"])
        self.assertEqual([anchor for anchor, _ in targets], ["sec-2-1", "sec-2-2", "exercises"])
        self.assertNotIn('id="sec-2-13"', result)

    def test_captions_and_example_labels(self):
        content = (
            '<p><img src="../images/a.jpg" alt=""/></p>\n<p>图2-6 计算步骤</p>\n'
            '<p>表2-1 资源消耗</p>\n<table><tr><td>值</td></tr></table>\n'
            '<p>例 2-1（生产安排） 设有两种产品。</p>\n'
            '<p>例2-1 和例2-2均为线性规划。</p>\n'
            '<p>(d)</p><p>图2-8</p><p>图9-7是一个无向图。</p>'
        )
        result = style_semantic_blocks(content)
        self.assertIn('<figcaption>图2-6 计算步骤</figcaption>', result)
        self.assertIn('alt="图2-6 计算步骤"', result)
        self.assertIn('<caption>表2-1 资源消耗</caption>', result)
        self.assertIn('<strong class="example-label">例 2-1</strong>', result)
        self.assertEqual(result.count('class="example-label"'), 1)
        self.assertIn('<p class="figure-caption">图2-8</p>', result)
        self.assertIn('<p>图9-7是一个无向图。</p>', result)


if __name__ == "__main__":
    unittest.main()
