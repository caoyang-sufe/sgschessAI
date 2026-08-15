# ilql_trainer.py
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
from typing import Dict, List, Tuple

class OfflineRLTrainer:
    """
    离线强化学习训练器
    使用ILQL (Implicit Q-Learning) 算法
    """
    def __init__(self, config):
        self.config = config
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # 初始化模型
        self.q_network = ActorCritic(config).to(self.device)
        self.target_q_network = ActorCritic(config).to(self.device)
        self.target_q_network.load_state_dict(self.q_network.state_dict())
        
        self.optimizer = optim.Adam(self.q_network.parameters(), lr=config.learning_rate)
        
        # ILQL超参数
        self.tau = config.tau  # 目标网络更新率
        self.expectile = config.expectile  # 0.7 或 0.9
        self.discount = config.discount  # 0.99
        
    def train_step(self, batch: Dict) -> Dict:
        """
        单步训练
        batch: {
            'states': [batch, state_dim],
            'actions': [batch],
            'rewards': [batch],
            'next_states': [batch, state_dim],
            'dones': [batch]
        }
        """
        states = batch['states'].to(self.device)
        actions = batch['actions'].to(self.device)
        rewards = batch['rewards'].to(self.device)
        next_states = batch['next_states'].to(self.device)
        dones = batch['dones'].to(self.device)
        
        # 计算当前Q值
        current_q = self.q_network.q_head(states, actions)
        
        # 计算目标Q值 (使用目标网络)
        with torch.no_grad():
            # 选择最优动作 (使用当前Q网络)
            next_actions = self.q_network.get_action(next_states, deterministic=True)
            next_q = self.target_q_network.q_head(next_states, next_actions)
            target_q = rewards + (1 - dones) * self.discount * next_q
        
        # ILQL损失 (expectile回归)
        error = target_q - current_q
        loss = torch.where(
            error > 0,
            self.expectile * error**2,
            (1 - self.expectile) * error**2
        ).mean()
        
        # 反向传播
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.q_network.parameters(), self.config.max_grad_norm)
        self.optimizer.step()
        
        # 更新目标网络
        self._update_target_network()
        
        return {'loss': loss.item()}
    
    def _update_target_network(self):
        """软更新目标网络"""
        for target_param, param in zip(
            self.target_q_network.parameters(),
            self.q_network.parameters()
        ):
            target_param.data.copy_(
                self.tau * param.data + (1 - self.tau) * target_param.data
            )