# state_schema.py
from dataclasses import dataclass
from typing import List, Optional
import numpy as np

@dataclass
class GameState:
    """游戏状态完整定义"""
    # ===== 经济信息 (4维) =====
    money: float                    # 金币 (归一化到0-1)
    shop_level: float               # 营帐等级 (1-6)
    shop_refresh_cost: float        # 刷新消耗
    shop_level_up_cost: float       # 升级消耗

    # ===== 主公信息 (3维) =====
    hp: float                       # 当前血量
    hp_limit: float                 # 血量上限
    shop_lock: int                  # 是否锁定 (0/1)

    # ===== 商店卡牌 (4维 × 6槽位 = 24维) =====
    shop: List[dict]                # 每个卡牌: chess_id编码, rank, 是否空

    # ===== 手牌 (5维 × 8张 = 40维) =====
    hand: List[dict]                # 每个卡牌: chess_id, attack, hp, is_spell, is_followup

    # ===== 上阵棋子 (4维 × 7位置 = 28维) =====
    lineup: List[dict]              # 每个棋子: chess_id, attack, hp, exists

    # ===== 装备 (2维 × 3件 = 6维) =====
    equipments: List[dict]          # 每个装备: equipment_id, exists

    # ===== 等待选择 (2维) =====
    wait_select_cards: float        # 待选卡牌数
    wait_select_equips: float       # 待选装备数

    # ===== 敌方信息 (2维) =====
    enemy_count: float              # 敌方棋子数
    enemy_hp: float                 # 敌方血量

    # ===== 总计: 4+3+24+40+28+6+2+2 = 109维 =====

    def to_vector(self) -> np.ndarray:
        """转换为特征向量"""
        pass

# 动作空间 (离散动作)
ACTION_SPACE = {
    # 基础操作 (10种)
    'refresh': 0,           # 刷新商店
    'level_up': 1,          # 升级营帐
    'lock': 2,              # 锁定/解锁
    'buy_slot_0': 3,        # 购买槽位0
    'buy_slot_1': 4,        # 购买槽位1
    'buy_slot_2': 5,        # 购买槽位2
    'buy_slot_3': 6,        # 购买槽位3
    'buy_slot_4': 7,        # 购买槽位4
    'buy_slot_5': 8,        # 购买槽位5
    'sell_rightmost': 9,    # 遣散最右侧手牌
    'lineup_rightmost': 10, # 上阵最右侧手牌
    'use_spell': 11,        # 使用锦囊 (需要进一步选择目标)
    'follow_up': 12,        # 随征 (需要选择目标和随征卡)
    'skip': 13,             # 跳过 (等待)
}

# 分层动作空间 (先决策类型，再决策具体参数)
HIERARCHICAL_ACTION = {
    'type': ['refresh', 'level_up', 'lock', 'buy', 'sell', 'lineup', 'use_spell', 'follow_up', 'skip'],
    'params': {
        'buy': ['slot_0', 'slot_1', 'slot_2', 'slot_3', 'slot_4', 'slot_5'],
        'sell': ['rightmost', 'by_chess_id'],
        'lineup': ['rightmost', 'by_position'],
        'use_spell': ['target_shop', 'target_lineup', 'target_hand'],
        'follow_up': ['target_position', 'follow_up_card'],
    }
}
