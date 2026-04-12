# 自适应信息熵探索策略 (Uncertainty-Aware Exploration) 修改方案

## 1. 核心逻辑修改说明

### A. 信息增益 (Information Gain, IG) 计算
- **定义**：对于每一个候选边界点 (Frontier)，计算其邻域内“未知区域”的占比。
- **实现方法**：
    - 在 `get_goal` 中，识别 `fbe_map == 0` 的区域为未知区域。
    - 对于 `frontier_locations_16` 中的每个点，取一个以其为中心、半径为 `R`（拟定为 30 像素，约 1.5 米）的窗口。
    - 统计窗口内 `fbe_map == 0` 的像素总数，作为该点的 `ig_score`。
- **目的**：优先前往那些背靠大片“白区”的边界，避免在已经几乎探索完毕的小角落浪费时间。

### B. 动态权重调节 (Dynamic Weighting)
- **判定标准**：使用 `self.navigate_steps`。
- **两个阶段**：
    1. **探索初期 (Early Stage)**：`navigate_steps < 100`（可配置）。
       - 权重分配：`W_proximity_agent` (高), `W_ig` (高), `W_proximity_goal` (低)。
       - 理由：先快速把房子跑完，建立全局地图。
    2. **任务导向期 (Task Stage)**：`navigate_steps >= 100`。
       - 权重分配：`W_proximity_agent` (中), `W_ig` (中), `W_proximity_goal` (高)。
       - 理由：已经有了一定地图基础，开始根据场景图推理的建议位置进行精准定向探索。

### B. 初始环视开关 (Initial Look-around Toggle)
- **目的**：通过配置控制是否在任务开始时执行初始 360 度环视。
- **配置项**：在 `configs/config_habitat.yaml` 中新增 `use_look_around: true/false`。
- **实现逻辑**：
    - 在 `main.py` 中判断 `args.use_look_around`。
    - 如果为 `True`，执行环视循环；如果为 `False`，跳过环视直接进入探索阶段。
- **注意**：跳过环视可能会减少初始地图信息，影响后续的图构建。

## 2. 接口与变量依赖
- `self.navigate_steps`: 用于判断当前探索阶段。
- `fbe_map`: 形状为 `(H, W)`，其中 `0` 表示未知。
- `frontier_locations_16`: 过滤后的候选边界点坐标。
- `args.use_look_around`: 控制初始环视的布尔值。

## 3. 注意事项与风险防范
- **边界检查**：在提取局部窗口时，必须使用 `np.clip` 或边界判定，防止坐标越界导致程序崩溃。
- **计算效率**：边界点数量可能较多（通常 10-50 个），使用 numpy 的切片求和是高效的，不会引起卡顿。
- **量化对齐**：IG 分数、距离分数、目标引导分数需要进行归一化（0-1），否则权重调节将失去意义。
- **初始化一致性**：无论是否执行环视，`navigate_steps` 都应正确初始化以保证后续逻辑正常。

## 4. 错误修复 (Bug Fixes)

### A. AttributeError: 'Graph' object has no attribute 'navigate_steps'
- **问题原因**：在 `main.py` 的初始环视阶段调用了 `graph.update_scenegraph()`，但此时 `graph.navigate_steps` 尚未初始化。
- **修复方案**：
    - 在 `src/graph/graph.py` 的 `Graph.__init__` 方法中初始化 `self.navigate_steps = 0`。
    - 在 `main.py` 的初始环视循环中，可以显式设置 `graph.set_navigate_steps(0)`（可选，由于已经在 `__init__` 中初始化）。
- **具体修改代码**：
    ```python
    # src/graph/graph.py
    class Graph():
        def __init__(self, args, is_navigation=True) -> None:
            # ... 现有初始化代码 ...
            self.last_reasoning = "None"
            self.navigate_steps = 0  # 新增：初始化 navigate_steps
    ```

### B. ValueError: zero-size array to reduction operation maximum which has no identity
- **问题原因**：在 `get_goal` 方法中，当所有候选边界点到智能体的距离都小于 `distance_threshold` 时，`distances_16` 及其对应的索引 `idx_16` 为空。这导致 `ig_scores` 也是一个空数组，调用 `ig_scores.max()` 时触发了 NumPy 的报错。
- **修复方案**：
    - 在计算 `ig_scores` 之前，先检查 `distances_16` 是否为空。如果为空，直接返回 `None`。
    - 在调用 `ig_scores.max()` 之前增加 `ig_scores.size > 0` 的判断，增强鲁棒性。
- **具体修改代码**：
    ```python
    # src/graph/graph.py
    idx_16 = np.where(distances>=distance_threshold)
    distances_16 = distances[idx_16]
    if len(distances_16) == 0:  # 新增：空数组检查
        return None
    # ... 后续计算 ig_scores ...
    if ig_scores.size > 0 and ig_scores.max() > 0: # 新增：size > 0 检查
        ig_scores = ig_scores / ig_scores.max()
    ```
