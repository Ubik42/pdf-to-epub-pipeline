# PDF to EPUB Pipeline

批量把没有可用 EPUB 的 PDF 书籍转换为可检索、可重排、可在 Koodo Reader 中阅读的 EPUB 3。源 PDF 不修改；中间结果可追溯到原始页码；失败书籍进入隔离队列，不生成表面可读但内容不可靠的成品。

## 已转换书目

此表只列由本工程实际处理、完成结构校验的 EPUB；“结构校验通过”不等于全书文字、公式和阅读器显示均已逐页复核。下载入口只对已核实公开再分发授权的文件开放。

| 书名 | 作者／出版社 | ISBN | 转换与校验状态 | 下载 |
| --- | --- | --- | --- | --- |
| [运筹学（第5版）](jobs/operations-research-5.status.md) | 《运筹学》教材编写组／清华大学出版社 | 9787302590811 | 526 页扫描版转 EPUB 3；EPUBCheck 5.4.0：0 错误、0 警告；阅读器与内容仍待进一步复核 | 授权材料核验中，暂不公开文件 |

本仓库公开转换程序、排版规则和可复核的处理记录。源 PDF、解析出的整书正文、书中图片和 EPUB 成品默认不纳入 Git；公开书籍文件须逐本确认授权范围，随后在 GitHub Release 提供，并从上表直链下载。项目代码的公开不代表原书获得开放许可。

## 工作区边界

| 路径 | 内容 |
| --- | --- |
| `D:\text\PDFBookInbox` | 待处理 PDF；允许按批次建立子目录 |
| `D:\text\BookInbox` | 验收通过的 EPUB，继续进入现有 Koodo 导入链路 |
| `work/` | 页图、解析结果、质量报告和可重试状态；不提交 Git |
| `docs/WORKFLOW.md` | 识别路由、标准中间层、EPUB 生成与验收规则 |
| `docs/EPUB_STYLE_STANDARD.md` | 教材目录、图表、例题、公式的 EPUB 排版标准 |

本机 Text 链路：用户手动提供 PDF；本工程生成的 EPUB 放入 `BookInbox`；再由 `obsidian_koodo_library` 入库到 Koodo 与 Obsidian。此链路仅供本机使用，不是公开仓库的运行前提。

## 核心决策

工程以直接读取页面图像的文档解析模型为主。所用 MinerU standard 档是混合流水线，内部仍使用 OCR 组件；它不会先给通用语言模型一份扁平 OCR 文本并让模型自由改写：

1. 扫描书籍、公式、表格、脚注和图文混排页面直接使用文档视觉模型解析。
2. 如果页面本来具有可靠文本层，可把文本层作为字符证据，但不能让它取代页面视觉结构。
3. 对疑难字符、数字和模型分歧，可以再用独立 OCR 结果交叉复核；任何识别文本都不能交给通用语言模型无证据地改写。
4. 一本书对应一个可断点续跑的长期任务。当前每 32 页保存一个解析段；后续再细化到逐页资源、警告和修改记录。
5. 无法可靠判断的内容保留原页并进入人工复核，不为了“完成率”生成未经证实的文本。

本机 RTX 4080 具有 16 GB 显存，可以进行本地文档视觉模型的试运行。正式后端不在工程初建时写死；先以中文教材、英文正文、公式、表格、双栏和低清扫描页组成小型基准集，再决定默认后端和降级顺序。

## 当前阶段

MinerU 4 本地环境已经建立。首个完整任务为《运筹学（第5版）》：526 页纯扫描 PDF，使用 standard 质量档进行页面理解、结构恢复和 EPUB 生成。解析与 EPUBCheck 已通过，Koodo 已本地入库；阅读器显示和全书内容仍需继续复核，见 `jobs/operations-research-5.status.md`。

书籍任务参数保存在 `jobs/`；识别生成的 Markdown 和验证报告保存在 `work/`。`scripts/build_epub.py` 将 Markdown 按章拆成 EPUB 3 XHTML、把 LaTeX 公式转为 MathML、嵌入封面和本地图片并生成导航目录。发布前使用官方 EPUBCheck 验证。

## 本地环境

使用 Python 3.12 与 `requirements.txt`。MinerU 模型权重存于用户的 `.mineru/models`，不进入仓库：

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
.venv\Scripts\mineru-kit.exe models download --tier standard --small-backend onnx --vlm-engine llama-cpp --source modelscope
```

每本书的元数据、页数、源文件指纹和输出路径写入 `jobs/*.toml`。解析脚本按 32 页保存，重新运行会跳过已完成页段；人工修订另记在同名 `corrections.md`。
