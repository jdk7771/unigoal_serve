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
- 在初始环视中增加对 `done` 的处理，如果环视中途结束，立即触发 Reset。
- 确保 `wait` 状态下不会发生非预期的环境步进冲突。
