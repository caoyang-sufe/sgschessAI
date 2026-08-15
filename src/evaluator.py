# evaluator.py
import torch
import numpy as np
from typing import Dict, List, Tuple
from collections import defaultdict

class ModelEvaluator:
    """模型评估器"""
    def __init__(self, config):
        self.config = config
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def evaluate_policy(self, model, env, num_episodes=100, render=False):
        """评估策略性能"""
        rewards = []
        wins = 0
        action_counts = defaultdict(int)

        for ep in range(num_episodes):
            state = env.reset()
            episode_reward = 0
            done = False

            while not done:
                # 选择动作
                action, _, _ = model.get_action(state, deterministic=True)
                next_state, reward, done, info = env.step(action)

                action_counts[action] += 1
                episode_reward += reward
                state = next_state

            rewards.append(episode_reward)
            if info.get('win', False):
                wins += 1

        return {
            'avg_reward': np.mean(rewards),
            'std_reward': np.std(rewards),
            'win_rate': wins / num_episodes,
            'action_distribution': dict(action_counts)
        }

    def compare_models(self, model1, model2, env, num_episodes=50):
        """比较两个模型"""
        results1 = self.evaluate_policy(model1, env, num_episodes)
        results2 = self.evaluate_policy(model2, env, num_episodes)

        return {
            'model1': results1,
            'model2': results2,
            'improvement': results1['avg_reward'] - results2['avg_reward']
        }

    def analyze_behavior(self, model, env, num_episodes=20):
        """分析模型行为模式"""
        behaviors = {
            'action_sequence': [],
            'state_visits': defaultdict(int),
            'action_transitions': defaultdict(lambda: defaultdict(int))
        }

        for ep in range(num_episodes):
            state = env.reset()
            actions = []

            for step in range(100):  # 最大步数
                action, _, _ = model.get_action(state, deterministic=True)
                next_state, _, done, _ = env.step(action)

                actions.append(action)
                behaviors['state_visits'][self._state_hash(state)] += 1
                if len(actions) > 1:
                    behaviors['action_transitions'][actions[-2]][actions[-1]] += 1

                state = next_state
                if done:
                    break

            behaviors['action_sequence'].append(actions)

        return behaviors

    def _state_hash(self, state):
        """状态哈希 (用于统计访问频率)"""
        if isinstance(state, dict):
            # 简化哈希
            return str(state.get('money', 0)) + '_' + str(state.get('shopLevel', 0))
        return str(state)
