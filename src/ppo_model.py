# ppo_model.py
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple, Dict

class ActorCritic(nn.Module):
    """PPO Actor-Critic 网络"""
    def __init__(self, config):
        super().__init__()
        self.config = config

        # 状态编码器
        self.state_encoder = StateEncoder(config)

        # Actor网络 (策略)
        self.actor = nn.Sequential(
            nn.Linear(config.state_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, config.action_dim)
        )

        # Critic网络 (价值)
        self.critic = nn.Sequential(
            nn.Linear(config.state_dim, 256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, 1)
        )

        # 动作价值头 (用于Q学习)
        self.q_head = nn.Sequential(
            nn.Linear(config.state_dim + config.action_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 1)
        )

    def forward(self, state: Dict) -> Tuple[torch.Tensor, torch.Tensor]:
        """返回动作logits和状态价值"""
        features = self.state_encoder(state)
        logits = self.actor(features)
        value = self.critic(features)
        return logits, value

    def get_action(self, state: Dict, deterministic: bool = False) -> Tuple[int, torch.Tensor, torch.Tensor]:
        """选择动作"""
        features = self.state_encoder(state)
        logits = self.actor(features)
        probs = F.softmax(logits, dim=-1)

        if deterministic:
            action = probs.argmax(dim=-1).item()
        else:
            action = torch.multinomial(probs, 1).item()

        log_prob = F.log_softmax(logits, dim=-1)[0, action]
        value = self.critic(features)

        return action, log_prob, value

    def evaluate_actions(self, state: Dict, actions: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """评估给定动作"""
        features = self.state_encoder(state)
        logits = self.actor(features)
        values = self.critic(features)

        log_probs = F.log_softmax(logits, dim=-1)
        action_log_probs = log_probs.gather(1, actions.unsqueeze(-1)).squeeze(-1)

        # 计算熵 (用于探索)
        probs = F.softmax(logits, dim=-1)
        entropy = -(probs * log_probs).sum(dim=-1).mean()

        return action_log_probs, values, entropy
