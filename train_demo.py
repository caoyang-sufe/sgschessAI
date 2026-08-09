import json
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    BitsAndBytesConfig
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer, DataCollatorForCompletionOnlyLM
import numpy as np
from collections import Counter
import pandas as pd

# ===================== 1. 数据加载与预处理 =====================

class TavernChessDataset(Dataset):
    """将轨迹数据转换为训练样本"""
    
    def __init__(self, json_path, tokenizer, max_length=512):
        with open(json_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        
        self.tokenizer = tokenizer
        self.max_length = max_length
        
        # 动作类型映射
        self.action_type_map = {
            'init': 0,
            'refresh': 1,
            'levelUp': 2,
            'lock': 3,
            'buy': 4,
            'sell': 5,
            'lineup': 6,
            'useSpell': 7,
            'followUp': 8,
            'gameOver': 9
        }
        
        # 构建样本列表
        self.samples = self._build_samples()
        
    def _build_samples(self):
        samples = []
        
        for trajectory in self.data['trajectory']:
            state_before = trajectory.get('stateBefore')
            action = trajectory.get('type')
            details = trajectory.get('details', {})
            
            if state_before is None:
                continue
                
            # 提取状态特征
            state_features = self._extract_features(state_before)
            
            # 构建动作描述
            action_desc = self._build_action_description(action, details)
            
            # 标签：动作类型
            action_label = self.action_type_map.get(action, 0)
            
            samples.append({
                'state': state_features,
                'action_label': action_label,
                'action_desc': action_desc,
                'raw_state': state_before,
                'raw_action': action,
                'details': details
            })
        
        return samples
    
    def _extract_features(self, state):
        """将状态转换为数值特征向量"""
        features = []
        
        # 1. 基础经济信息
        features.append(state.get('money', 0) / 100.0)  # 归一化
        features.append(state.get('shopLevel', 1) / 10.0)
        features.append(state.get('shopRefreshCost', 1) / 10.0)
        features.append(state.get('shopLevelUpCost', 10) / 100.0)
        features.append(1.0 if state.get('shopLock', False) else 0.0)
        features.append(state.get('hp', 40) / 100.0)
        features.append(state.get('hpLimit', 40) / 100.0)
        
        # 2. 商店信息 (3个槽位)
        shop_goods = state.get('shopGoods', [])
        for i in range(3):
            if i < len(shop_goods) and shop_goods[i]:
                goods = shop_goods[i]
                features.append(goods.get('chessID', 0) / 1000000.0)  # 归一化
                features.append(goods.get('rank', 0) / 10.0)
                features.append(1.0)  # 存在标志
            else:
                features.extend([0.0, 0.0, 0.0])
        
        # 3. 手牌信息 (最多8张)
        hand_chess = state.get('handChess', [])
        for i in range(8):
            if i < len(hand_chess) and hand_chess[i]:
                card = hand_chess[i]
                features.append(card.get('chessID', 0) / 1000000.0)
                features.append(card.get('attack', 0) / 10.0)
                features.append(card.get('hp', 0) / 10.0)
                features.append(1.0 if card.get('isSpell', False) else 0.0)
                features.append(1.0 if card.get('isFollowUp', False) else 0.0)
            else:
                features.extend([0.0, 0.0, 0.0, 0.0, 0.0])
        
        # 4. 上阵信息 (最多7个位置)
        lineup = state.get('lineup', [])
        for i in range(7):
            if i < len(lineup) and lineup[i]:
                chess = lineup[i]
                features.append(chess.get('chessID', 0) / 1000000.0)
                features.append(chess.get('attack', 0) / 10.0)
                features.append(chess.get('hp', 0) / 10.0)
                features.append(1.0)  # 存在标志
            else:
                features.extend([0.0, 0.0, 0.0, 0.0])
        
        # 5. 装备信息
        equipments = state.get('equipments', [])
        for i in range(3):
            if i < len(equipments) and equipments[i]:
                equip = equipments[i]
                features.append(equip.get('equipmentID', 0) / 1000000.0)
                features.append(1.0)
            else:
                features.extend([0.0, 0.0])
        
        # 6. 等待选择状态
        features.append(min(state.get('waitSelectCards', 0), 5) / 5.0)
        features.append(min(state.get('waitSelectEquips', 0), 5) / 5.0)
        
        return np.array(features, dtype=np.float32)
    
    def _build_action_description(self, action, details):
        """构建动作的自然语言描述"""
        desc = f"执行操作: {action}"
        if details:
            desc += f", 详情: {json.dumps(details)}"
        return desc
    
    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, idx):
        sample = self.samples[idx]
        state_tensor = torch.tensor(sample['state'], dtype=torch.float32)
        action_tensor = torch.tensor(sample['action_label'], dtype=torch.long)
        
        # 构建文本输入（用于语言模型微调）
        text = f"当前状态: {json.dumps(sample['raw_state'])}\n动作: {sample['action_desc']}\n"
        
        # Tokenize
        encoding = self.tokenizer(
            text,
            truncation=True,
            max_length=self.max_length,
            padding='max_length',
            return_tensors='pt'
        )
        
        return {
            'input_ids': encoding['input_ids'].squeeze(),
            'attention_mask': encoding['attention_mask'].squeeze(),
            'state': state_tensor,
            'action_label': action_tensor,
            'action_desc': sample['action_desc']
        }


# ===================== 2. 模型定义 =====================

class TavernChessModel:
    """自走棋决策模型"""
    
    def __init__(self, model_name="Qwen/Qwen2-1.5B"):
        self.model_name = model_name
        self.state_dim = None
        self.action_dim = 10  # 10种动作类型
        
    def create_model(self):
        # 使用 Qwen2 作为基础模型 (轻量级，适合强化学习)
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16
        )
        
        model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True
        )
        
        # 添加状态编码器 (MLP)
        # 由于我们使用语言模型，将状态特征作为文本输入的一部分
        return model
    
    def create_tokenizer(self):
        tokenizer = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        return tokenizer


# ===================== 3. 训练管道 =====================

def train():
    """使用 TRL 框架训练模型"""
    
    # 1. 初始化模型和分词器
    chess_model = TavernChessModel()
    tokenizer = chess_model.create_tokenizer()
    model = chess_model.create_model()
    
    # 2. 加载数据
    dataset = TavernChessDataset('tavern_data.json', tokenizer)
    
    # 3. 配置 LoRA
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )
    
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()
    
    # 4. 训练参数
    training_args = TrainingArguments(
        output_dir="./chess_model_output",
        num_train_epochs=3,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        save_steps=100,
        logging_steps=50,
        learning_rate=2e-4,
        fp16=True,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        report_to="none"
    )
    
    # 5. 数据整理器
    response_template = "动作:"
    collator = DataCollatorForCompletionOnlyLM(response_template, tokenizer=tokenizer)
    
    # 6. SFT 训练器
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        tokenizer=tokenizer,
        data_collator=collator,
        max_seq_length=512,
        dataset_text_field="text",
        packing=False
    )
    
    # 7. 开始训练
    trainer.train()
    
    # 8. 保存模型
    model.save_pretrained("./chess_model_final")
    tokenizer.save_pretrained("./chess_model_final")
    
    return model, tokenizer


# ===================== 4. 推理与评估 =====================

def predict_action(model, tokenizer, state, device="cuda"):
    """根据状态预测最优动作"""
    
    # 将状态转换为文本
    state_text = f"当前状态: {json.dumps(state)}\n动作:"
    
    inputs = tokenizer(state_text, return_tensors="pt").to(device)
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=50,
            temperature=0.7,
            do_sample=True
        )
    
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    # 解析动作
    # 简单实现：从输出中提取动作类型
    action_part = response.split("动作:")[-1].strip()
    
    # 这里需要根据实际情况解析动作
    return action_part


# ===================== 5. 主程序 =====================

if __name__ == "__main__":
    # 训练模型
    model, tokenizer = train()
    print("模型训练完成！")
    
    # 加载一个示例状态进行测试
    with open('tavern_data.json', 'r') as f:
        data = json.load(f)
    
    example_state = data['trajectory'][0]['stateBefore']
    predicted_action = predict_action(model, tokenizer, example_state)
    print(f"预测动作: {predicted_action}")
