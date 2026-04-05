# Bug 诊断与修复报告 - FMM 规划器崩溃 (Zero Contour Error)

## 1. 报错现象与堆栈信息
- **错误类型**：`ValueError: the array phi contains no zero contour (no zero level set)`
- **触发位置**：`src/utils/fmm/fmm_planner_policy.py`, 调用 `skfmm.distance` 时。
- **业务上下文**：在 `main.py` 的 Episode 开始阶段，执行完初始环视（step == 0）后调用第一个 `agent.step(agent_input)` 时崩溃。

## 2. 根因分析
- **FMM 算法原理**：Fast Marching Method 需要一个“种子点”（目标点）作为 0 等值线向外扩散计算距离场。
- **空目标传递**：在 `main.py` 中，环视结束后的代码逻辑如下：
  ```python
  agent_input['goal'] = np.zeros((args.local_width, args.local_height))
  ```
- **逻辑缺陷**：这段代码直接创建了一个全为 0 的矩阵作为目标图。在 FMM 逻辑中，目标通常被设为 1，非目标为 0。如果整个图都是 0，意味着**没有任何点被标记为目标**。当规划器尝试寻找“到目标的距离”时，由于找不到起点（zero level set），底层 `skfmm` 库会抛出 ValueError。

## 3. 解决方案
### A. 初始目标注入（推荐）
在 `main.py` 的环视结束后，不应传递全零目标。应该：
1. 调用 `BEV_map.move_local_map()` 更新当前地图位姿。
2. 调用 `graph.explore()` 获取第一个真实探索目标（边界点或推理点）。
3. 将该目标转换到局部地图坐标，并填充到 `agent_input['goal']` 中。

### B. 规划器鲁棒性加固
在 `src/agent/unigoal/agent.py` 或规划器模块中增加空目标检查：
- 如果 `goal_map.sum() == 0`，则跳过路径规划，直接返回原地动作或停止信号，而不是任由其调用 FMM 导致崩溃。

## 4. 复核记录
- [x] 确认 `global_goals` 在 `step == 0` 时未被赋予有效初值。
- [x] 确认 `agent.step` 内部确实在 `get_action` -> `get_local_goal` 中使用了 FMM。
- [x] 确认转换逻辑（全局坐标 -> 局部地图坐标）符合当前 `BEV_map` 偏移量。

## 5. 实施计划
1. 修改 `main.py`：环视结束后立即触发第一次 `graph.explore()`。
2. 修改 `src/agent/unigoal/agent.py`：在 `get_local_goal` 中增加目标有效性检查。
