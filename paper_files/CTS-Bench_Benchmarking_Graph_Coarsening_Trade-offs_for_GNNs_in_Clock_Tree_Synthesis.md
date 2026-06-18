标题：CTS-Bench: Benchmarking Graph Coarsening Trade-offs for GNNs in Clock Tree Synthesis

​	    CTS-Bench：面向时钟树综合中图神经网络的图粗化权衡基准测试

时间：2026.1

会议：ASPLOS MLBench（workshop）

主要内容：这篇论文构建了一个 CTS-Bench 数据集，用来评估在 CTS 预测任务中，把原始门级图压缩成聚类图以后，GNN 的训练效率会提升多少、预测精度会损失多少，尤其关注 clock skew 这种局部 CTS 指标是否还能被准确预测

背景： GNN 预测物理设计指标，因为电路网表天然可以表示成图：节点是 cell，边是连接关系但**真实门级网表太大了**。如果每个标准单元都作为一个节点，那么图可能有几十万甚至上百万节点，直接训练 GNN 会消耗大量显存和时间。因此必须需要**graph coarsening / graph clustering**，也就是把很多节点合并成一个大节点，降低图规模

现有不足：缺少公开、标准化、面向 CTS 的 GNN benchmark，现有图压缩方法虽然能降低计算成本，但不清楚它们是否保留了 CTS 需要的信息

论文解决的核心问题：在 GNN-based CTS 分析中，图压缩到底是“有效加速”还是“破坏任务信息”？压缩带来的效率收益和预测精度损失之间如何量化

<img src="C:\Users\不胜传说正义仔\AppData\Roaming\Typora\typora-user-images\image-20260612152008475.png" alt="image-20260612152008475" style="zoom: 67%;" />

<img src="C:\Users\不胜传说正义仔\Desktop\cctsbench1.png" style="zoom: 25%;" />

4860个设计：随机化7个布局参数生成486个placement，随机4个时钟树综合参数，生成10个结果，共4860个

CTS参数：sink max diametersink 最大直径 / 时钟终端簇最大直径,Max Wire Length最大线长,Cluster Sizesink 聚类大小,Buffer Distancebuffer 插入距离 / 缓冲器间距

![image-20260612165837248](C:\Users\不胜传说正义仔\AppData\Roaming\Typora\typora-user-images\image-20260612165837248.png)

作者首先从 **RTL-Design（rtl.v）** 和 **TB（testbench，tb.v）** 出发，在 **Stage 1** 中通过 **Placement Generation（OpenROAD）**，利用随机化参数 **Rand. Knobs** 生成不同的 placement；同时进行 **Activity Extraction**，用 **Icarus Verilog** 仿真得到 **VCD** 波形文件，再转换成 **SAIF** 开关活动文件。之后流程分成左右两支：左侧是 **Graph Construction**，先从 placement 后的设计构建 **Raw Graph**，再经过 **Processing**，包括 **I. Atomic BFS**、**II. Spread Filter**，其中空间分散度满足 **σ > 0.05** 的 cluster 会被 **Keep** 保留，以及 **III. Gravity Merge**，最终得到压缩后的 **Clustered Graph**；右侧是 **Multi-Variant CTS**，使用 **TritonCTS** 对每个设计运行 **10x per Design** 的 CTS 参数变体，最后把结果写入 **metadata.csv**，其中包含 **Skew、Power、Wire** 等 QoR 指标，以及 **Place & CTS Knobs** 和 **Gap Scores**

activity extraction可以提供cell的信号反转信息，用于提供预测power所需的结点特征

![image-20260612182338380](C:\Users\不胜传说正义仔\AppData\Roaming\Typora\typora-user-images\image-20260612182338380.png)

图压缩效果，平均压缩13.3倍

![image-20260612184410778](C:\Users\不胜传说正义仔\AppData\Roaming\Typora\typora-user-images\image-20260612184410778.png)

峰值显存和执行时间表现

![image-20260612185957462](C:\Users\不胜传说正义仔\AppData\Roaming\Typora\typora-user-images\image-20260612185957462.png)

图粗化前

MAE平均绝对误差，越小越好说明预测值和真实值越接近

R² 决定系数，用来观察模型对趋势的捕捉，越接近1越好

结论一：Raw Graph seen 上效果好
看蓝色柱子低 + 红色菱形高。

结论二：Raw Graph unseen 上泛化变差
看橙色柱子比蓝色柱子高 + 黑色方块比红色菱形低。

结论三：skew 最难，power 相对容易
看 Skew 子图的 MAE 整体最高，Power 子图的 MAE 最低且 seen/unseen 差距小。

![image-20260612191443413](C:\Users\不胜传说正义仔\AppData\Roaming\Typora\typora-user-images\image-20260612191443413.png)

图粗化后

结论一：Clustered Graph seen 上仍可拟合
看红色菱形高，说明 R² Seen 接近 1。

结论二：Clustered Graph unseen 上泛化失败
看黑色方块大量低于 0，说明 R² Unseen 为负，甚至不如均值预测。

结论三：MAE 低不等于预测可靠
看部分橙色柱子不高，但黑色方块很低，说明平均误差小但没学到变化趋势。

结论四：图粗化损失 spatial fidelity
看 seen R² 高而 unseen R² 崩溃，说明聚类图保留了训练分布统计信息，但丢失了可泛化的局部空间细节。



图压缩破坏 skew 这种局部指标的信息。应该改为

Raw Graph 已经难以 zero-shot 预测 skew；
Clustered Graph 进一步恶化了 zero-shot R²。



动机包装：用GNN做CTS的并不多，因此这篇论文的出发点可能有点站不住脚，只能说未来可期。另外以他自己的实验为例，它的原始图包含了所有组合逻辑才会导致显存不够/效率下降，但实际上CTS预测主要依赖sink，如果只构建以sink为结点的图就没有它所说的问题了

实验方法纯主观：模型选取，图压缩方式都有争议：没有“完全证明”图压缩导致 skew 预测失败，如果 Raw Graph 在unseen skew 上本来就预测不好，那 Clustered Graph 在 unseen skew 上更差，到底是图压缩破坏了 skew 信息，还是模型本来就不会预测 skew？

