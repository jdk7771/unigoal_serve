# 引入信息熵（信息增益）与动态权重

## 核心思路
1.  **信息增益 (Information Gain, IG)**：在探索过程中，不仅考虑离当前位置或目标的距离，还要考虑该边界（Frontier）周围未知区域的大小。未知区域越多，该方向的信息增益越高。
2.  **动态权重**：根据导航的步数 (`navigate_steps`) 动态调整距离分数、信息增益分数和目标引导分数的权重。在初期侧重于开图（探索），在后期侧重于寻找目标。
3.  **可配置化**：在 `config_habitat.yaml` 中增加两个开关，用于控制是否启用信息增益和动态权重。

## 代码修改计划
### 1. 配置文件修改 (`configs/config_habitat.yaml`)
添加以下参数：
- `use_ig_weight`: true/false (是否在探索分数中加入信息增益)
- `use_dynamic_weight`: true/false (是否根据步数动态调整权重)

### 2. 代码实现 (`src/graph/graph.py`)
- 在 `Graph` 类的 `get_goal` 方法中：
    - 计算 `ig_scores`：统计边界点周围 $R$ 像素范围内的未知区域数量。
    - 定义权重 $w_{agent}, w_{ig}, w_{goal}$。
    - 如果 `use_dynamic_weight` 为 true，则根据 `self.navigate_steps` 设置权重。
    - 如果 `use_ig_weight` 为 true，则在最终得分 `scores` 中加入 `ig_scores`。

## 潜在问题与接口风险
1.  **性能开销**：`ig_scores` 的计算涉及对每个边界点周围区域的求和。如果边界点非常多，可能会导致每步决策变慢。
2.  **权重一致性**：当 `use_ig_weight` 为 false 时，需要合理分配剩余权重，或者确保公式在权重为 0 时依然有效。
3.  **未知区域定义**：目前定义 `fbe_map == 0` 为未知区域，需确保 `fbe_map` 的生成逻辑在不同场景下是一致的。
4.  **接口兼容性**：需要确保 `self.args` 中包含新增的配置项，否则 `getattr` 需提供默认值。
5.  **归一化风险**：如果 `ig_scores` 全部为 0，归一化过程（除以 max）需要处理除零错误。
