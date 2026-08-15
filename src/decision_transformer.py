# decision_transformer.py
import torch
import torch.nn as nn
import math

class DecisionTransformer(nn.Module):
    """
    决策Transformer - 适用于离线强化学习
    使用轨迹历史预测下一步动作
    """
    def __init__(self, config):
        super().__init__()
        self.config = config

        # 状态编码器
        self.state_encoder = StateEncoder(config)

        # 动作嵌入
        self.action_embedding = nn.Embedding(config.action_dim, config.embed_dim)

        # 返回嵌入 (奖励的累计值)
        self.return_embedding = nn.Linear(1, config.embed_dim)

        # 位置编码
        self.pos_encoder = PositionalEncoding(config.embed_dim, config.max_seq_len)

        # Transformer解码器
        decoder_layer = nn.TransformerDecoderLayer(
            d_model=config.embed_dim,
            nhead=config.num_heads,
            dim_feedforward=config.ffn_dim,
            dropout=config.dropout,
            activation='gelu'
        )
        self.transformer = nn.TransformerDecoder(decoder_layer, num_layers=config.num_layers)

        # 输出头
        self.action_head = nn.Linear(config.embed_dim, config.action_dim)
        self.value_head = nn.Linear(config.embed_dim, 1)

    def forward(self, states, actions, returns, timesteps):
        """
        states: [batch, seq_len, state_dim]
        actions: [batch, seq_len]
        returns: [batch, seq_len, 1]
        timesteps: [batch, seq_len]
        """
        batch_size, seq_len = states.shape[:2]

        # 编码状态
        state_embeds = self.state_encoder(states)  # [batch, seq_len, embed_dim]

        # 编码动作和返回
        action_embeds = self.action_embedding(actions)  # [batch, seq_len, embed_dim]
        return_embeds = self.return_embedding(returns)   # [batch, seq_len, embed_dim]

        # 位置编码
        pos_embeds = self.pos_encoder(timesteps)        # [batch, seq_len, embed_dim]

        # 拼接输入 (每个时间步包含状态+动作+返回+位置)
        inputs = state_embeds + action_embeds + return_embeds + pos_embeds

        # 因果掩码 (保证只关注过去)
        causal_mask = torch.triu(torch.ones(seq_len, seq_len), diagonal=1).bool()

        # Transformer解码
        outputs = self.transformer(
            inputs.permute(1, 0, 2),  # [seq_len, batch, embed_dim]
            inputs.permute(1, 0, 2),
            tgt_mask=causal_mask
        ).permute(1, 0, 2)  # [batch, seq_len, embed_dim]

        # 预测动作
        action_preds = self.action_head(outputs)  # [batch, seq_len, action_dim]
        value_preds = self.value_head(outputs)    # [batch, seq_len, 1]

        return action_preds, value_preds


class PositionalEncoding(nn.Module):
    """位置编码"""
    def __init__(self, d_model, max_len=1000):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)  # [1, max_len, d_model]
        self.register_buffer('pe', pe)

    def forward(self, timesteps):
        return self.pe[:, timesteps, :]
