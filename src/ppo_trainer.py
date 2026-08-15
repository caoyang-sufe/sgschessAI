# ppo_trainer.py
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from collections import deque
import numpy as np
from typing import Dict, List, Tuple

class PPOTrainer:
    """PPO训练器"""
    def __init__(self, config):
        self.config = config
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # 初始化模型
        self.model = ActorCritic(config).to(self.device)
        self.optimizer = optim.Adam(self.model.parameters(), lr=config.learning_rate)

        # PPO超参数
        self.clip_epsilon = config.clip_epsilon  # 0.2
        self.value_coef = config.value_coef      # 0.5
        self.entropy_coef = config.entropy_coef  # 0.01
        self.gamma = config.gamma                # 0.99
        self.gae_lambda = config.gae_lambda      # 0.95

        # 经验缓存
        self.buffer = {
            'states': [],
            'actions': [],
            'rewards': [],
            'dones': [],
            'log_probs': [],
            'values': [],
            'advantages': [],
            'returns': []
        }

    def collect_trajectory(self, env, max_steps=1000):
        """收集一条轨迹"""
        state = env.reset()
        trajectory = []

        for _ in range(max_steps):
            # 选择动作
            action, log_prob, value = self.model.get_action(state)

            # 执行动作
            next_state, reward, done, info = env.step(action)

            trajectory.append({
                'state': state,
                'action': action,
                'reward': reward,
                'done': done,
                'log_prob': log_prob,
                'value': value,
                'info': info
            })

            state = next_state
            if done:
                break

        return trajectory

    def compute_gae(self, trajectory):
        """计算GAE优势函数"""
        values = [t['value'] for t in trajectory]
        rewards = [t['reward'] for t in trajectory]
        dones = [t['done'] for t in trajectory]

        advantages = []
        returns = []
        gae = 0

        for t in reversed(range(len(trajectory))):
            if t == len(trajectory) - 1:
                next_value = 0 if dones[t] else values[t + 1]
            else:
                next_value = values[t + 1]

            delta = rewards[t] + self.gamma * next_value * (1 - dones[t]) - values[t]
            gae = delta + self.gamma * self.gae_lambda * (1 - dones[t]) * gae

            advantages.insert(0, gae)
            returns.insert(0, gae + values[t])

        return advantages, returns

    def update(self, trajectory):
        """PPO更新"""
        # 计算优势
        advantages, returns = self.compute_gae(trajectory)

        # 转换为张量
        states = self._prepare_states([t['state'] for t in trajectory])
        actions = torch.tensor([t['action'] for t in trajectory], device=self.device)
        old_log_probs = torch.tensor([t['log_prob'] for t in trajectory], device=self.device)
        advantages = torch.tensor(advantages, device=self.device)
        returns = torch.tensor(returns, device=self.device)

        # 标准化优势
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        # 多轮更新
        for _ in range(self.config.ppo_epochs):
            # 评估当前策略
            log_probs, values, entropy = self.model.evaluate_actions(states, actions)

            # 计算比率
            ratio = torch.exp(log_probs - old_log_probs.detach())

            # PPO损失
            surr1 = ratio * advantages
            surr2 = torch.clamp(ratio, 1 - self.clip_epsilon, 1 + self.clip_epsilon) * advantages
            actor_loss = -torch.min(surr1, surr2).mean()

            # Critic损失
            value_loss = F.mse_loss(values.squeeze(), returns)

            # 熵损失 (鼓励探索)
            entropy_loss = -self.entropy_coef * entropy

            # 总损失
            loss = actor_loss + self.value_coef * value_loss + entropy_loss

            # 反向传播
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.max_grad_norm)
            self.optimizer.step()

        return {
            'actor_loss': actor_loss.item(),
            'value_loss': value_loss.item(),
            'entropy': entropy.item()
        }
