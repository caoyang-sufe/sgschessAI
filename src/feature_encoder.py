# feature_encoder.py
import torch
import torch.nn as nn
import numpy as np
from typing import Dict, List, Optional

class ChessEmbedding(nn.Module):
    """棋子ID的嵌入表示"""
    def __init__(self, num_chess: int = 10000, embed_dim: int = 64):
        super().__init__()
        self.embedding = nn.Embedding(num_chess, embed_dim)

    def forward(self, chess_ids: torch.Tensor) -> torch.Tensor:
        return self.embedding(chess_ids)

class StateEncoder(nn.Module):
    """状态编码器 - 将原始状态转换为特征向量"""
    def __init__(self, config):
        super().__init__()
        self.config = config

        # 1. 经济特征编码 (简单MLP)
        self.econ_encoder = nn.Sequential(
            nn.Linear(7, 32),
            nn.ReLU(),
            nn.Linear(32, 32)
        )

        # 2. 卡牌特征编码 (使用Transformer处理变长序列)
        self.card_encoder = nn.TransformerEncoder(
            nn.TransformerEncoderLayer(
                d_model=64,
                nhead=4,
                dim_feedforward=128,
                dropout=0.1
            ),
            num_layers=2
        )
        self.card_proj = nn.Linear(5, 64)  # 5维卡牌特征 -> 64维嵌入

        # 3. 全局注意力 (处理多区域信息)
        self.global_attention = nn.MultiheadAttention(
            embed_dim=128,
            num_heads=4,
            dropout=0.1
        )

        # 4. 最终输出
        self.output_proj = nn.Sequential(
            nn.Linear(128, 256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, config.state_dim)
        )

    def forward(self, state: Dict) -> torch.Tensor:
        """
        state 格式:
        {
            'econ': tensor,           # [batch, 7]
            'shop': tensor,           # [batch, 6, 5]
            'hand': tensor,           # [batch, 8, 5]
            'lineup': tensor,         # [batch, 7, 4]
            'equip': tensor,          # [batch, 3, 2]
            'wait': tensor,           # [batch, 2]
            'enemy': tensor,          # [batch, 2]
            'mask': {                 # 各区域的mask
                'shop': tensor,
                'hand': tensor,
                'lineup': tensor,
            }
        }
        """
        batch_size = state['econ'].shape[0]

        # 编码经济特征
        econ_feat = self.econ_encoder(state['econ'])  # [batch, 32]

        # 编码卡牌特征 (商店 + 手牌 + 上阵)
        shop_feat = self.card_proj(state['shop'])     # [batch, 6, 64]
        hand_feat = self.card_proj(state['hand'])     # [batch, 8, 64]
        lineup_feat = self.card_proj(state['lineup']) # [batch, 7, 64]

        # 合并所有卡牌特征
        all_cards = torch.cat([shop_feat, hand_feat, lineup_feat], dim=1)  # [batch, 21, 64]

        # 使用Transformer编码卡牌间关系
        all_cards = all_cards.permute(1, 0, 2)  # [21, batch, 64]
        card_feat = self.card_encoder(all_cards)  # [21, batch, 64]
        card_feat = card_feat.permute(1, 0, 2)    # [batch, 21, 64]
        card_feat = card_feat.mean(dim=1)         # [batch, 64]

        # 融合所有特征
        combined = torch.cat([econ_feat, card_feat], dim=-1)  # [batch, 96]

        # 最终投影
        output = self.output_proj(combined)  # [batch, state_dim]

        return output
