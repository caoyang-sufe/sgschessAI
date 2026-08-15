# train_pipeline.py
import json
import torch
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TrainingPipeline:
    """完整训练管道"""
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.output_dir = Path(self.config['output_dir'])
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 初始化组件
        self.data_loader = self._create_data_loader()
        self.model = self._create_model()
        self.trainer = self._create_trainer()
        self.evaluator = ModelEvaluator(self.config)

    def _create_data_loader(self):
        """创建数据加载器"""
        # 加载JSON数据
        with open(self.config['data_path'], 'r') as f:
            raw_data = json.load(f)

        # 创建轨迹数据集
        dataset = TavernChessDataset(raw_data, self.config)
        return DataLoader(
            dataset,
            batch_size=self.config['batch_size'],
            shuffle=True,
            num_workers=4,
            pin_memory=True
        )

    def _create_model(self):
        """创建模型"""
        if self.config['model_type'] == 'ppo':
            return ActorCritic(self.config)
        elif self.config['model_type'] == 'decision_transformer':
            return DecisionTransformer(self.config)
        else:
            raise ValueError(f"Unknown model type: {self.config['model_type']}")

    def _create_trainer(self):
        """创建训练器"""
        if self.config['algorithm'] == 'ppo':
            return PPOTrainer(self.config)
        elif self.config['algorithm'] == 'ilql':
            return OfflineRLTrainer(self.config)
        else:
            raise ValueError(f"Unknown algorithm: {self.config['algorithm']}")

    def train(self):
        """执行训练"""
        logger.info("开始训练...")

        best_reward = -float('inf')
        training_log = []

        for epoch in range(self.config['num_epochs']):
            epoch_losses = []

            # 训练循环
            for batch_idx, batch in enumerate(self.data_loader):
                loss_dict = self.trainer.train_step(batch)
                epoch_losses.append(loss_dict)

                if batch_idx % self.config['log_interval'] == 0:
                    logger.info(f"Epoch {epoch}, Batch {batch_idx}, Loss: {loss_dict}")

            # 评估
            if epoch % self.config['eval_interval'] == 0:
                eval_results = self.evaluator.evaluate_policy(
                    self.trainer.model,
                    None,  # 需要提供环境
                    num_episodes=self.config['eval_episodes']
                )

                logger.info(f"Epoch {epoch} Evaluation: {eval_results}")

                # 保存最佳模型
                if eval_results['avg_reward'] > best_reward:
                    best_reward = eval_results['avg_reward']
                    self.save_model('best_model.pt')

                training_log.append({
                    'epoch': epoch,
                    'eval_results': eval_results,
                    'losses': epoch_losses
                })

        # 保存最终模型
        self.save_model('final_model.pt')
        self.save_training_log(training_log)

        logger.info("训练完成!")
        return training_log

    def save_model(self, filename: str):
        """保存模型"""
        path = self.output_dir / filename
        torch.save({
            'model_state_dict': self.trainer.model.state_dict(),
            'config': self.config,
            'timestamp': datetime.now().isoformat()
        }, path)
        logger.info(f"模型已保存: {path}")

    def save_training_log(self, log):
        """保存训练日志"""
        path = self.output_dir / 'training_log.json'
        with open(path, 'w') as f:
            json.dump(log, f, indent=2)

    def load_model(self, path: str):
        """加载模型"""
        checkpoint = torch.load(path, map_location=self.device)
        self.trainer.model.load_state_dict(checkpoint['model_state_dict'])
        logger.info(f"模型已加载: {path}")
        return checkpoint


# ===================== 配置文件 =====================
# config.json
CONFIG_TEMPLATE = {
    "data_path": "tavern_segment_1_1786774585880.json",
    "output_dir": "checkpoints",

    # 模型配置
    "model_type": "ppo",  # ppo | decision_transformer
    "algorithm": "ppo",   # ppo | ilql | bc
    "state_dim": 128,
    "action_dim": 14,
    "embed_dim": 256,
    "max_seq_len": 128,
    "num_heads": 4,
    "num_layers": 4,
    "ffn_dim": 512,
    "dropout": 0.1,

    # 训练配置
    "batch_size": 64,
    "learning_rate": 3e-4,
    "num_epochs": 100,
    "log_interval": 50,
    "eval_interval": 5,
    "eval_episodes": 50,
    "max_grad_norm": 1.0,

    # PPO超参数
    "clip_epsilon": 0.2,
    "value_coef": 0.5,
    "entropy_coef": 0.01,
    "gamma": 0.99,
    "gae_lambda": 0.95,
    "ppo_epochs": 10,

    # ILQL超参数
    "tau": 0.005,
    "expectile": 0.7,
    "discount": 0.99,
}


# ===================== 主程序 =====================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='自走棋强化学习训练')
    parser.add_argument('--config', type=str, default='config.json', help='配置文件路径')
    parser.add_argument('--mode', type=str, choices=['train', 'eval', 'play'], default='train')
    parser.add_argument('--model', type=str, help='模型路径')
    args = parser.parse_args()

    if args.mode == 'train':
        # 创建并保存配置
        with open(args.config, 'w') as f:
            json.dump(CONFIG_TEMPLATE, f, indent=2)

        # 运行训练
        pipeline = TrainingPipeline(args.config)
        pipeline.train()

    elif args.mode == 'eval':
        # 评估模型
        pipeline = TrainingPipeline(args.config)
        pipeline.load_model(args.model)
        results = pipeline.evaluator.evaluate_policy(
            pipeline.trainer.model,
            None,  # 需要环境
            num_episodes=100
        )
        print(f"评估结果: {results}")

    elif args.mode == 'play':
        # 交互式对战
        print("交互模式 (需要实现环境)")
