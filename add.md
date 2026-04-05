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

## 2. 接口与变量依赖
- `self.navigate_steps`: 用于判断当前探索阶段。
- `fbe_map`: 形状为 `(H, W)`，其中 `0` 表示未知。
- `frontier_locations_16`: 过滤后的候选边界点坐标。

## 3. 注意事项与风险防范
- **边界检查**：在提取局部窗口时，必须使用 `np.clip` 或边界判定，防止坐标越界导致程序崩溃。
- **计算效率**：边界点数量可能较多（通常 10-50 个），使用 numpy 的切片求和是高效的，不会引起卡顿。
- **量化对齐**：IG 分数、距离分数、目标引导分数需要进行归一化（0-1），否则权重调节将失去意义。

## 4. 修改步骤规划
1. 修改 `src/graph/graph.py` 中的 `get_goal` 函数。
2. 在计算 `distances_16_inverse` 之后，插入 IG 计算逻辑。
3. 增加权重计算逻辑。
4. 合并所有分数得出最终目标。
