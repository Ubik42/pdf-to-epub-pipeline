# 《运筹学（第5版）》识别修订

## PDF 第 197 页（印刷页 192）

例 7-6 的拉格朗日条件在扫描页中为三行，共用一个左花括号，式号依次为（7-17）至（7-19）。原解析把花括号误分到三个公式中，并把上、下部分分别识别为 `\left\lceil`、`\left\lfloor`，导致首式不能转换为 MathML。

修订为三条独立的可重排公式，保留等式和式号：

```latex
\frac{\partial L(X,\lambda)}{\partial x_1}=w_1-\lambda\frac{\partial f}{\partial x_1}=0\tag{7-17}
\frac{\partial L(X,\lambda)}{\partial x_2}=w_2-\lambda\frac{\partial f}{\partial x_2}=0\tag{7-18}
f(x_1,x_2)=q\tag{7-19}
```

共用花括号的视觉样式未保留；三个等式和原书式号已逐项核对。原始 PDF 未修改。

## PDF 第 172 页（印刷页 167）

表 6-7（b）、（c）的首个“条件”列分别使用带撇号的圆点符号 `⊙′` 和 `⊙″`。解析结果将它们误写成没有基底的上标角度符号 `^{\circ}'`、`^{\circ}''`。已对照扫描页修订两个表头单元格。
