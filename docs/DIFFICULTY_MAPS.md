# Easy 与 Normal 地图

2026-11-05：六张地图保留独立地形，更新为四次曝光版。每张图有独立的道路与站址定义，统一的任务机制不再对应统一的局部支路模板。Hard 三图更新为48项的 v3.0 配置，见 [Hard 地图与规则](HARD_MAPS.md)。

## 当前六图

| 网站名称 | Agent 匿名名 | 版本 | 地点／道路 | 委托 | 保留与调整 |
| --- | --- | --- | --- | --- | --- |
| 卡普林火山 | 玄锥熔原 | easy-01-v4.0 | 39／45 | 16 | 火山环缘与西侧熔岩坡路，不穿越火山口 |
| 缪尔森林 | 雾杉溪谷 | easy-02-v3.0 | 43／51 | 16 | 保留溪谷与三桥，西侧山坡长环与东岸缓径不对称 |
| 普利维特采湖区 | 石阶湖群 | easy-03-v3.0 | 38／41 | 16 | 保留四湖串联与共享湖口，站点分布在两岸选择和崖边路径上 |
| 尼斯湖水怪 | 暮湾长湖 | normal-01-v3.0 | 68／79 | 24 | 保留长湖，西侧支谷与东侧高岭形成不同绕行路线 |
| 澳洲野犬 | 沙汀林湖 | normal-02-v3.0 | 71／86 | 24 | 重做为雨林营地、三处内陆湖区与东岸长路的放射连接 |
| 野猪林 | 栎影林地 | normal-03-v3.0 | 78／93 | 24 | 重做为两溪汇流、中央林脊与外围林班环路，取消规则网格 |

网站显示真实地图名；Agent 仍只收到匿名地点、公开道路与当前任务。地理来源、作者说明和隐藏能力表不进入 Agent 观察。

2026-11-07 前端地理地图：地图集和游玩页使用 OpenStreetMap 的真实地物轮廓与 WGS84 坐标。六图分别按火山环缘、溪谷、湖群、长湖、岛上海岸和迪恩森林的地理锚点落位；处理站、测点和连接仍是实验设置。地理显示层位于 `memorybenchmark/cartographic_maps/`，保持地点编号、连接关系、路程权重、任务和能力表不变。原生 Agent 的科学地图与已有实验观测底图保留原版本，显示层不进入 MCP 观察。

地理底图统一采用与全区域 Lunatic 相同的浅色地图集风格，湖岸、林地与聚落色块表示实际参考地物。Easy／Normal 没有新增处理区域限制。原始地理数据、检索记录及版本前像保存在 `.runs/atlas-cartographic-style-20261107/reference-data/`。使用 `python -m scripts.build_geographic_atlas --source-dir <参考数据目录> --map <地图主题>` 可复现单图；SVG 中保留 OpenStreetMap 署名。

完整公开图：[卡普林火山](assets/difficulty-maps/capulin_easy20-complete.svg)、[森林](assets/difficulty-maps/forest_geo_easy20-complete.svg)、[湖区](assets/difficulty-maps/cascade_easy20-complete.svg)、[长湖](assets/difficulty-maps/nessie_normal30-complete.svg)、[野犬](assets/difficulty-maps/dingo_normal30-complete.svg)、[野猪林](assets/difficulty-maps/boar_normal30-complete.svg)。图中不显示站型能力。

## 地形与路线

地图是在地理原型上创作的示意关卡，不能作为实测道路、交通条件或现实导航图。道路权重是抽象成本，画布坐标不是米；画布、节点数与真实面积分别记录。

- 卡普林火山参考整个 Capulin Volcano National Monument，官方约800英亩（约3.2平方公里）。火山锥与熔岩坡地给出环缘和缺口道路的地形背景，无需另取一个小范围彩丘裁片。[NPS 地形介绍](https://www.nps.gov/cavo/learn/nature/naturalfeaturesandecosystems.htm)、[官方步道说明](https://www.nps.gov/cavo/planyourvisit/choosing-your-hike.htm)。丹霞旧图与成绩保留历史归档，不混为本图结果。
- 缪尔森林参考溪谷平径、桥接步道和坡地绕行，以不等长的两岸路线及西侧山坡环路组织关卡。[NPS 步道说明](https://www.nps.gov/muwo/planyourvisit/hike.htm)。
- 普利维特采湖区参考下湖峡谷和湖阶过渡，保留串联瓶颈。两岸站点按路线作用配对，避免上下游同型站位于同一条必经返程线上而完全冗余。[公园游线说明](https://np-plitvicka-jezera.hr/en/plan-your-visit/istrazite-jezera/activities/lake-tour-programmes/)。
- 尼斯湖保留细长湖体，跨岸路线只能绕过两端；西部支谷与东部高岭有独立形态，没有横跨湖面的虚构捷径。[VisitScotland 原型介绍](https://www.visitscotland.com/things-to-do/nature-outdoors/lochs/ness)。
- 澳洲野犬参考 K’gari 中央湖区、林地与东岸的连接关系。海岸长路和三处内陆湖群围绕雨林营地展开，所有站点位于陆地。[昆士兰公园原型说明](https://parks.qld.gov.au/parks/kgari-fraser/journeys/central-lakes-scenic-drive)。
- 野猪林参考迪恩森林东部的混合林地与溪谷。两条溪流汇合，将中央林脊与外侧林区分隔；中央夹地在合流口终止，通过上游桥梁或下游外侧桥绕行。[Forestry England 原型说明](https://www.forestryengland.uk/forest-planning/parkend-walk-and-blakeney-hill-walk-forest-plan)。

处理站可以是道路中的沿途地点、林内短径或远端调查路径的入口。站型字母与站址先独立于能力设计，不能由地名、动物主题或站点外观推断支持资料。

## 共同规则和预算

Easy 仍为八种地理资料、八种站型、每型两座站，能力一一对应；Normal 仍为八种地理加四种动物资料、十六种站型、每型两站，每种资料有两个支持站型，站型支持一至两类资料。

每项两段：主动 survey 采集、主动 process 处理，两段成功后回营主动 submit。处理失败保留资料并反馈站型能力；经过不揭示能力，不提供独立查询。地图与能力配对在制作阶段固定，跨 Agent、条件与重复运行不变。

每项均重建 session；持久记忆由原生 Agent 自主保存和读取。保留与清除组独立推进，不输入参考记忆，不以任何旧 Agent 成绩选择地图配置。

| 级别 | 游戏操作上限 | 主模型调用／整理 | 有效任务时间 |
| --- | --- | --- | --- |
| Easy | 88 | 100／6 | 3600 秒 |
| Normal | 168 | 180／6 | 3600 秒 |

每种资料四次曝光、每个测点四次曝光，每图16／24项。四个区块各包含一次所有资料，任务顺序重新生成。制作阶段仅交换目标位置，使站址有实际路线用途，并避免“最近站”成为能力答案。能力关系、目标流与地理图随后一起冻结。

请求层的一周同请求恢复机制保持原状，失败请求与退避不计入有效任务时间；不启用整 session 自动重跑。详见[独立实验](INDEPENDENT_EXPERIMENTS.md)。

## 制作与验收

道路和站点分别定义于 scripts/field_geography/ 的六个模块。共享工具只处理绘图、线段交点和匿名站型标记，不生成网格、环形地区或重复服务支路。

每张图独立检查道路连通、真实交点、陆地站址、受控跨水通道、点击点间距、全部同型站副本的严格路线用途及操作预算。Normal 的非法能力空间不被当成 Agent 已知世界，未观察的站型保持未知。

确定性脚本使用实际反馈逐项运行并严格重放全部动作与返回观察；保留策略使用自己的历史反馈，清除策略只使用当前任务反馈。这是 240 项零模型调用的规则与可行性验收，不是原生 Agent 成绩，也不预设统一实验后的难度差或记忆收益。

逐张复现：

```powershell
python -m scripts.build_field_maps --map forest
python -m scripts.render_field_maps --map forest
python -m scripts.check_difficulty_maps --map forest_geo_easy16 --output .runs/forest-fresh-check
```

六图联合验收：

```powershell
python -m scripts.check_difficulty_maps --output .runs/field-v2-fresh-check
python -m unittest discover -s tests
```

## 历史版本

此前 GA／Hermes 的完整试跑属于 v1 预实验。原始 run、源码、地图、记忆及归档继续保留，不能用 v2 图解释 v1 分数。v1 配置保存在 memorybenchmark/data/history/difficulty-v1/，历史回放测试使用这些冻结夹具。[v1 制作记录](history/DIFFICULTY_MAPS_V1.md)。

当前 v2 六图准备供后续统一实验使用；本次地图制作没有启动新的原生模型实验。
