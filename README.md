# 三国杀自走棋AI训练

本项目基于[三国杀自走棋小抄](https://github.com/caoyang-sufe/sgscodex)收集细粒度的自走棋实战操作数据，进行强化学习训练

目前项目处于demo阶段，提供三个文件：

- `CollectOperationTick.js`: 用于游戏中收集tick级别状态动作数据的篡改猴脚本，目前实现为分段下载，减小缓存压力和空间占用
- `tavern_data_sample.json`: 实际测试的tick级别状态动作数据样例
- `train_demo.py`: torch + TRL 框架的训练示例脚本

具体状态/动作定义如下:

1. 状态（state）：
   - 全局信息（全局信息只需记录一次）：本局使用的主公ID，本场游戏的场次ID或房间号（如果有则记录，可以参考TavernChessStats-0.4.3.js中的内容）
   - 当前商店等级
   - 当前商店区详细数据(shopGoods)
   - 当前手牌区详细数据(handChess)
   - 当前上阵区详细数据(lineUp)
   - 当前金币数(money)
   - 当前装备区详细数据(equip?)

2. 动作（action）：可能的动作集合如下，都已经找到了入口函数以及触发hook
   - 刷新商店：可记录本次刷新消耗
   - 锁定/解锁商店：
   - 购买：具体购买了商店第几个位置的卡牌(goodsId/chessId)？
   - 遣散：具体遣散卡牌的goodsId/chessId？
   - 上阵卡牌：具体上阵卡牌的goodsId/chessId？
   - 使用锦囊：具体使用的锦囊goodsId/spellId
   - 随征卡牌：将随征卡(goodsId/chessId)附着到上阵区域的卡牌(goodsId/chessId)

---

## 260813更新

- TickRecord.html: 根据tick数据复原游戏录像，暂未没有上传所有卡牌的图片，可在 [https://github.com/caoyang-sufe/TavernChessCodex/tree/main/assets](https://github.com/caoyang-sufe/TavernChessCodex/tree/main/assets) 下找到相关图片的历史备份