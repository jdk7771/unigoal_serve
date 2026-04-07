# 场景图边生成逻辑修改方案

## 1. 问题背景
当前 `src/graph/graph.py` 中的 `update_edge` 方法在生成边时，会无条件地在所有新节点与旧节点之间、以及新节点相互之间尝试建立边。这可能导致图中存在大量空间距离过远、逻辑关系较弱的边。

## 2. 修改目标
在 `update_edge` 中引入基于欧几里得距离的过滤机制。只有当两个节点之间的物理距离在指定的范围内（`min_edge_distance` 到 `max_edge_distance`）时，才考虑生成它们之间的边。

## 3. 拟修改代码点分析 (`src/graph/graph.py`)

### `Graph.__init__`
- 从 `self.args` 中获取 `min_edge_distance` 和 `max_edge_distance` 配置。
- 如果配置不存在，设置默认值（例如 `min_edge_distance = 0.0`, `max_edge_distance = 1.0` 米）。

### `Graph.update_edge`
- 在遍历节点对准备创建 `Edge` 对象之前，计算两个节点的中心点之间的距离。
- `node.center` 存储的是地图网格坐标 `[x, y]`。
- 距离计算公式（米）：
  ```python
  dist_grid = np.linalg.norm(np.array(node1.center) - np.array(node2.center))
  dist_m = dist_grid * self.map_resolution / 100.0
  ```
- 增加条件判断：`if min_dist <= dist_m <= max_dist:`

## 4. 接口与配置变更

### `configs/config_habitat.yaml`
新增配置项：
- `min_edge_distance`: 0.0  # 最小距离限制（米）
- `max_edge_distance`: 1.5  # 最大距离限制（米）

## 5. 详细实现思路

1.  **配置读取**：在 `Graph` 类初始化时，读取相关参数。
2.  **距离过滤**：
    - 在 `update_edge` 方法中，分别针对 "new\_node vs old\_node" 和 "new\_node vs new\_node" 的循环中添加距离校验。
    - 只有满足距离条件的节点对才会被添加到 `new_edges` 列表中。
    - 随后 LLM 只会为这些满足物理距离条件的边预测语义关系。

## 6. 预期效果
- 减少冗余边的生成。
- 提高场景图的局部相关性，使图结构更符合真实的物理空间分布。
- 减少 LLM 的调用次数（因为待预测关系的边减少了）。
