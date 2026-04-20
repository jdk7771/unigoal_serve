# 修改思路 - 修复 Episode over AssertionError

## 问题分析
报错 `AssertionError: Episode over, call reset before calling step` 通常发生在 Habitat 环境已经结束（done=True），但代码在没有调用 `reset()` 的情况下再次调用了 `step()`。

经过对 `main.py` 和 `src/agent/unigoal/agent.py` 的代码审计，发现以下几个潜在问题导致了这一冲突：

1. **隐式 Reset 与 Wait 标志冲突**：
   - 在 `agent.py` 中，`agent.step()` 会在检测到 `done=True` 时自动调用 `self.reset()`。
   - 但是，如果 `agent.step()` 被调用时携带了 `wait=True` 标志（例如在 Episode 开始时的等待阶段），它会直接返回 `done=False` 而不执行任何环境交互。
   - 如果环境在之前的某个地方（如 `main.py` 中的初始环视循环）已经达到了结束状态，而 `agent.step()` 因为 `wait=True` 绕过了检测和 Reset 逻辑，那么当 `wait` 变为 `False` 并最终调用 `envs.step()` 时，就会触发报错。

2. **初始环视逻辑不健壮**：
   - `main.py` 中的 `step == 0` 分支直接调用了 `envs.step({'action': 3})`。如果这个循环中环境意外结束（例如触发了某种步数限制或动作限制），它虽然会 `break`，但后续的 `agent.step(agent_input)` 调用（此时 `wait` 通常为 `True`）会掩盖这一 `done` 状态，导致环境在之后真正需要行动时已经处于 Over 状态。

3. **Stop 动作判定失效**：
   - 在 `instanceimagegoal_env.py` 中，`step(action)` 方法通过 `if action == 0` 判断是否停止。
   - 然而，`agent.py` 传入的是 `{'action': 0}` 字典。这导致 `self.stopped` 永远不会被设为 `True`，环境虽然通过模拟器停止了，但 Agent 内部的状态记录可能不一致。

## 修改方案

### 1. 规范化 Reset 流程 (main.py)
- 将 Episode 结束后的 Reset 逻辑显式化。
- 在 `if done:` 分支中明确调用 `agent.reset()`，获取新 Episode 的初始观测。
- 确保在 `done` 触发后，本轮循环不再执行可能导致 `envs.step()` 的后续逻辑。

### 2. 移除 Agent 内部的自动 Reset (agent.py)
- `agent.step()` 应该只负责执行一步动作并返回结果。
- 移除 `if done: self.reset()` 逻辑，交给外部循环统一管理。这符合标准的强化学习/机器人环境交互规范，也避免了隐藏的状态切换。

### 3. 增强环境类的动作处理 (instanceimagegoal_env.py)
- 修改 `step` 方法，支持从字典中提取 action 索引，确保 `self.stopped` 能正确触发。

### 4. 优化初始环视与 Wait 逻辑 (main.py)
- 在初始环视中增加对 `done` 的处理，如果环视中途结束，立即触发 Reset制。
- 确保 `wait` 状态下不会发生非预期的环境步进冲突。

# 修改思路 - 图边生成距离限制

## 问题分析
当前 `src/graph/graph.py` 中的 `update_edge` 方法在生成边（Edge）时，会将所有新探测到的节点（new_nodes）与已有节点（old_nodes）以及新节点之间全部建立连接。这种全连接方式在节点较多时会导致：
1. **冗余边过多**：物理上相距甚远的物体之间也会生成空间关系查询，增加 LLM/VLM 的负担。
2. **逻辑不合理**：空间关系通常只存在于近距离物体之间（如 "next to", "on"），对远距离物体强制生成关系可能导致错误的推理结果。

## 修改方案

### 1. 配置参数引入 (configs/config_habitat.yaml)
- 增加 `use_distanage` 参数（默认为 `false` 或根据需求设为 `true`），用于控制是否开启距离过滤。
- 增加 `dist_threshold` 参数（单位：米），设定生成边的最大物理距离阈值。

### 2. 图类初始化调整 (src/graph/graph.py)
- 在 `Graph.__init__` 中从 `args` 读取上述两个参数。
- 确保 `self.map_resolution` 正确初始化，用于将物理距离（米）转换为地图像素距离。

### 3. 边生成逻辑过滤 (src/graph/graph.py)
- 在 `update_edge` 方法中，在创建 `Edge` 对象之前增加距离判定。
- 计算两个节点中心点（`node.center`）之间的欧几里得距离。
- 判定公式：`dist_px <= (dist_threshold * 100 / map_resolution)`。
- 只有满足条件的节点对才实例化 `Edge` 并加入后续的 LLM 关系推理流程。

## 潜在问题与风险

1. **坐标系转换精度**：
   - `node.center` 是在 `update_node` 中基于 PCD 点云平均值计算并转换到地图像素坐标的。转换公式为 `int(center * 100 / resolution)`。
   - 距离过滤时需统一单位。建议将 `dist_threshold` 转换为像素单位进行比较，以减少浮点运算开销。

2. **空中心点异常**：
   - 如果某个节点的点云为空（虽然罕见），`node.center` 可能为 `None`。
   - **对策**：在计算距离前增加 `if node1.center is not None and node2.center is not None` 的检查，若中心点缺失则跳过边生成。

3. **图连通性风险**：
   - 若 `dist_threshold` 设置过小，可能导致场景图变得支离破碎（Disconnected Graph），影响后续基于图匹配（Graph Matching）的导航决策。
   - **建议**：默认阈值设置不宜过小（如 3.0m - 5.0m），以涵盖常见的房间内物体分布。

4. **性能考虑**：
   - 距离计算虽然是 $O(N^2)$，但在单步更新中新节点数量通常较少，计算压力可控。但需注意在大规模场景中累积节点过多的情况。

5. **LLM 语义缺失**：
   - 过滤掉远距离边意味着 LLM 将不再处理这些物体间的关系。需确保这不会误删关键的全局空间约束。
