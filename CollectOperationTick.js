// ==UserScript==
// @name         自走棋训练数据收集器
// @namespace    http://tampermonkey.net/
// @version      1.0.0
// @description  收集自走棋游戏状态和动作数据，用于AI强化学习训练
// @author       caoyang-sufe
// @match        https://game.4399iw2.com/yxxsgs/*
// @match        *://*.sanguosha.com/10/*
// @match        *://*.sanguosha.com/x/*
// @match        *://*.sanguosha.com/10th/*
// @match        https://wan.baidu.com/*gameId=19793616*
// @match        *://h5.7k7k.com/web/H5GAMES.html?gid=960982bec2f555de44ea43ca8a7ef418/*
// @match        *://qqgame.qq.com/webappframe/?appid=10951
// @match        *://s118.app1107877410.qqopenapp.com/pc/qqLobby_index.php*
// @grant        GM_download
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-idle
// ==/UserScript==

(function() {
    'use strict';

    // ============================================================
    // 配置
    // ============================================================
    const CONFIG = {
        // 是否启用数据收集
        enabled: true,
        // 是否在控制台输出日志
        verbose: true,
        // 是否自动下载数据（每N步下载一次）
        autoDownload: true,
        // 自动下载间隔（步数）
        downloadInterval: 100,
        // 是否包含原始数据（用于调试）
        includeRaw: false
    };

    // ============================================================
    // 数据存储
    // ============================================================
    let gameData = {
        // 全局信息
        global: {
            gameId: '',
            tableId: '',
            userId: '',
            generalID: 0,
            generalName: '',
            seasonID: 0,
            startTime: '',
            playerCount: 0
        },
        // 回合数据 { round: { state, action, reward? } }
        rounds: {},
        // 当前回合
        currentRound: 0,
        // 步骤计数（用于自动下载）
        stepCount: 0,
        // 轨迹列表（按时间顺序）
        trajectory: [],
        // 是否已结束
        isGameOver: false
    };

    // ============================================================
    // 工具函数 - 获取管理器
    // ============================================================
    function getManager() {
        try {
            if (Laya && Laya.stage) {
                function find(o) {
                    if (!o) return null;
                    if (o.manager && o.manager.ReqShopRefreshChess) return o.manager;
                    if (o.ReqShopRefreshChess) return o;
                    var c = o._children || o.children || o.childList;
                    if (c) {
                        for (var i = 0; i < c.length; i++) {
                            var r = find(c[i]);
                            if (r) return r;
                        }
                    }
                    if (typeof o.numChildren === 'number' && typeof o.getChildAt === 'function') {
                        for (var i = 0; i < o.numChildren; i++) {
                            try {
                                var r = find(o.getChildAt(i));
                                if (r) return r;
                            } catch(e) {}
                        }
                    }
                    return null;
                }
                var m = find(Laya.stage);
                if (m) return m;
            }
        } catch(e) {}

        for (var k in window) {
            try {
                var o = window[k];
                if (o && o.ReqShopRefreshChess) return o;
                if (o && o.manager && o.manager.ReqShopRefreshChess) return o.manager;
            } catch(e) {}
        }
        return null;
    }

    // ============================================================
    // 状态收集函数
    // ============================================================

    // 1. 全局信息
    function collectGlobalInfo() {
        var m = getManager();
        if (!m) return null;

        var selfInfo = m.SelfInfo || m.selfInfo || {};
        var generalID = selfInfo.generalID || m.GeneralID || 0;
        var generalName = '';
        try {
            if (window.TavernChessConfiger) {
                var general = TavernChessConfiger.GetInstance().GetGeneralByGeneralID(generalID);
                if (general) generalName = general.GeneralName || '';
            }
        } catch(e) {}

        var seasonID = 0;
        try {
            if (window.TavernChessManager && TavernChessManager.GetInstance) {
                seasonID = TavernChessManager.GetInstance().CurSeasonID || 0;
            }
        } catch(e) {}

        return {
            gameId: m.TableID ? String(m.TableID) : '',
            tableId: m.TableID || 0,
            userId: selfInfo.userID || 0,
            generalID: generalID,
            generalName: generalName,
            seasonID: seasonID,
            startTime: new Date().toISOString(),
            playerCount: 0 // 稍后从headInfoList获取
        };
    }

    // 2. 商店区详细数据
    function collectShopGoods() {
        var m = getManager();
        if (!m) return [];

        var shop = m.ShopGoods || [];
        return shop.map(function(goods, index) {
            if (!goods) return null;
            return {
                slotIndex: index,
                goodsID: goods.goodsID || goods.GoodsID || 0,
                chessID: goods.chessID || goods.ChessID || 0,
                spellID: goods.spellID || goods.SpellID || 0,
                name: goods.name || goods.Name || '',
                rank: goods.rank || goods.Rank || 0,
                isLocked: false // 从商店锁状态推断
            };
        }).filter(Boolean);
    }

    // 3. 手牌区详细数据
    function collectHandChess() {
        var m = getManager();
        if (!m) return [];

        var hand = m.HandChess || m.handChess || [];
        return hand.map(function(card, index) {
            if (!card) return null;
            return {
                index: index,
                goodsID: card.goodsID || card.GoodsID || 0,
                chessID: card.chessID || card.ChessID || 0,
                spellID: card.spellID || card.SpellID || 0,
                name: card.name || card.Name || '',
                isSpell: !!(card.spellID || card.SpellID),
                isFollowUp: isFollowUpCard(card),
                attack: card.attack || card.Attack || 0,
                totalAttack: card.totalAttack || card.TotalAttack || 0,
                hp: card.hp || card.Hp || 0,
                totalHp: card.totalHp || card.TotalHp || 0,
                skills: card.skills ? card.skills.map(function(s) {
                    return s.skillID || 0;
                }) : [],
                buffs: card.mapBuffTyp ? Object.keys(card.mapBuffTyp).map(function(key) {
                    var b = card.mapBuffTyp[key];
                    return { buffID: b.buffID || 0, value: b.buffValue || 0, count: b.buffCount || 0 };
                }) : []
            };
        }).filter(Boolean);
    }

    // 4. 上阵区详细数据
    function collectLineup() {
        var m = getManager();
        if (!m) return [];

        var lineup = m.SelfInfo ? (m.SelfInfo.LineUpChess || []) : [];
        return lineup.map(function(chess, position) {
            if (!chess) return null;
            return {
                position: position,
                goodsID: chess.goodsID || chess.GoodsID || 0,
                chessID: chess.chessID || chess.ChessID || 0,
                name: chess.name || chess.Name || '',
                attack: chess.attack || chess.Attack || 0,
                totalAttack: chess.totalAttack || chess.TotalAttack || 0,
                hp: chess.hp || chess.Hp || 0,
                totalHp: chess.totalHp || chess.TotalHp || 0,
                skills: chess.skills ? chess.skills.map(function(s) {
                    return s.skillID || 0;
                }) : [],
                buffs: chess.mapBuffTyp ? Object.keys(chess.mapBuffTyp).map(function(key) {
                    var b = chess.mapBuffTyp[key];
                    return { buffID: b.buffID || 0, value: b.buffValue || 0, count: b.buffCount || 0 };
                }) : []
            };
        }).filter(Boolean);
    }

    // 5. 金币数
    function collectMoney() {
        var m = getManager();
        if (!m) return 0;
        return m.CoinNum || 0;
    }

    // 6. 装备区详细数据
    function collectEquipments() {
        var m = getManager();
        if (!m) return [];

        // 装备在 SelfInfo.equipments 中
        var selfInfo = m.SelfInfo || m.selfInfo || {};
        var equips = selfInfo.equipments || [];
        
        return equips.map(function(equip) {
            if (!equip || !equip.equipmentID) return null;
            var equipID = equip.equipmentID || 0;
            var equipName = '';
            var equipType = 0;
            try {
                if (window.TavernChessConfiger) {
                    var config = TavernChessConfiger.GetInstance().GetEquipByEquipID(equipID);
                    if (config) {
                        equipName = config.WeaponName || '';
                        equipType = config.WeaponType || 0;
                    }
                }
            } catch(e) {}
            return {
                equipmentID: equipID,
                name: equipName,
                type: equipType,
                progress: equip.skillProgress || 0,
                activeTime: equip.activeTime || 0
            };
        }).filter(Boolean);
    }

    // 7. 随征卡判断
    var FOLLOWUP_CHESS_IDS = [
        '21003071', '21003072', // 黄盖
        '21001061', '21001062', // 薛灵芸
        '21004141', '21004142', // 马元义
        '21007101', '21007102', // 张勋
        '20904231'              // 黄巾兵
    ];

    function isFollowUpCard(card) {
        if (!card) return false;
        var chessID = card.chessID || card.ChessID || 0;
        return FOLLOWUP_CHESS_IDS.indexOf(String(chessID)) !== -1;
    }

    // ============================================================
    // 完整状态收集
    // ============================================================
    function collectFullState() {
        var m = getManager();
        if (!m) return null;

        var phase = m.Phase || m.phase;
        var round = m.CurRound || m.curRound || m.Turn || m.turn || 0;

        var state = {
            // 基本信息
            round: round,
            phase: phase,
            timestamp: Date.now(),
            time: new Date().toISOString(),
            
            // 经济
            money: collectMoney(),
            shopRefreshCost: m.ShopRefreshCost || 0,
            shopLevelUpCost: m.ShopLevelUpCost || 0,
            shopLevel: m.ShopCurLevel || 0,
            shopLock: !!(m.SelfInfo && m.SelfInfo.shopLock),
            
            // 商店
            shopGoods: collectShopGoods(),
            
            // 手牌
            handChess: collectHandChess(),
            handCount: 0, // 下面计算
            
            // 上阵
            lineup: collectLineup(),
            lineupCount: 0, // 下面计算
            
            // 装备
            equipments: collectEquipments(),
            
            // 玩家信息
            hp: m.HP || 0,
            hpLimit: m.HPLimit || 0,
            
            // 敌人信息（简要）
            enemyCount: 0,
            enemyHP: 0,
            
            // 等待选择状态
            waitSelectCards: m.WaitSelectCards ? m.WaitSelectCards.length : 0,
            waitSelectEquips: m.WaitSelectEquiments ? m.WaitSelectEquiments.length : 0,
            
            // 原始数据（可选）
            raw: CONFIG.includeRaw ? {
                HandChess: m.HandChess,
                ShopGoods: m.ShopGoods,
                LineUpChess: m.SelfInfo ? m.SelfInfo.LineUpChess : null
            } : null
        };

        // 计算派生值
        state.handCount = state.handChess.length;
        state.lineupCount = state.lineup.length;

        // 获取敌人信息
        try {
            if (m.EnemyChess) {
                state.enemyCount = m.EnemyChess.length;
                state.enemyHP = m.EnemyHP || 0;
            } else if (m.battlePlayerInfo) {
                state.enemyCount = (m.battlePlayerInfo.Chess || []).length;
                state.enemyHP = m.battlePlayerInfo.hp || 0;
            }
        } catch(e) {}

        return state;
    }

    // ============================================================
    // 动作记录
    // ============================================================
    function recordAction(actionType, details, stateBefore, stateAfter) {
        if (!CONFIG.enabled) return;

        var m = getManager();
        var round = m ? (m.CurRound || m.curRound || m.Turn || m.turn || 0) : 0;

        var action = {
            round: round,
            timestamp: Date.now(),
            time: new Date().toISOString(),
            type: actionType,
            details: details || {},
            stateBefore: stateBefore || null,
            stateAfter: stateAfter || null,
            stepIndex: gameData.stepCount
        };

        // 添加到轨迹
        gameData.trajectory.push(action);
        gameData.stepCount++;

        // 更新回合数据
        if (!gameData.rounds[round]) {
            gameData.rounds[round] = { actions: [] };
        }
        gameData.rounds[round].actions.push(action);

        // 日志
        if (CONFIG.verbose) {
            console.log('[数据] 动作:', actionType, details);
        }

        // 自动下载
        if (CONFIG.autoDownload && gameData.stepCount % CONFIG.downloadInterval === 0) {
            downloadData('auto');
        }

        // 更新当前回合
        gameData.currentRound = round;
    }

    // ============================================================
    // Hook 函数 - 拦截游戏操作
    // ============================================================
    function hookGameOperations() {
        var m = getManager();
        if (!m) {
            setTimeout(hookGameOperations, 1000);
            return;
        }

        console.log('[数据] 开始Hook游戏操作...');

        // ----- 1. 刷新商店 -----
        var origRefresh = m.ReqShopRefreshChess;
        if (origRefresh && !origRefresh.__hooked) {
            m.ReqShopRefreshChess = function(isAuto) {
                var stateBefore = collectFullState();
                var cost = this.ShopRefreshCost || 0;
                origRefresh.call(this, isAuto);
                // 延迟记录状态（等待UI更新）
                setTimeout(function() {
                    var stateAfter = collectFullState();
                    recordAction('refresh', {
                        cost: cost,
                        isAuto: !!isAuto
                    }, stateBefore, stateAfter);
                }, 300);
            };
            m.ReqShopRefreshChess.__hooked = true;
            console.log('[数据] Hook: 刷新商店');
        }

        // ----- 2. 锁定/解锁商店 -----
        var origLock = m.ReqShopLock;
        if (origLock && !origLock.__hooked) {
            m.ReqShopLock = function() {
                var stateBefore = collectFullState();
                var currentLock = this.SelfInfo ? this.SelfInfo.shopLock : false;
                origLock.call(this);
                setTimeout(function() {
                    var stateAfter = collectFullState();
                    recordAction('lock', {
                        newState: !currentLock,
                        oldState: currentLock
                    }, stateBefore, stateAfter);
                }, 300);
            };
            m.ReqShopLock.__hooked = true;
            console.log('[数据] Hook: 锁定商店');
        }

        // ----- 3. 购买 -----
        var origBuy = m.ReqShopBuyChess;
        if (origBuy && !origBuy.__hooked) {
            m.ReqShopBuyChess = function(goodsID) {
                var stateBefore = collectFullState();
                // 找到购买的是第几个
                var shop = this.ShopGoods || [];
                var slotIndex = -1;
                var cardInfo = null;
                for (var i = 0; i < shop.length; i++) {
                    if (shop[i] && (shop[i].goodsID === goodsID || shop[i].GoodsID === goodsID)) {
                        slotIndex = i;
                        cardInfo = shop[i];
                        break;
                    }
                }
                origBuy.call(this, goodsID);
                setTimeout(function() {
                    var stateAfter = collectFullState();
                    recordAction('buy', {
                        goodsID: goodsID,
                        slotIndex: slotIndex,
                        chessID: cardInfo ? (cardInfo.chessID || cardInfo.ChessID || 0) : 0,
                        spellID: cardInfo ? (cardInfo.spellID || cardInfo.SpellID || 0) : 0,
                        cost: m.GetShopBuyCost ? m.GetShopBuyCost(goodsID) : 0
                    }, stateBefore, stateAfter);
                }, 500);
            };
            m.ReqShopBuyChess.__hooked = true;
            console.log('[数据] Hook: 购买');
        }

        // ----- 4. 遣散 -----
        var origSell = m.ReqShopRecycleChess;
        if (origSell && !origSell.__hooked) {
            m.ReqShopRecycleChess = function(goodsID) {
                var stateBefore = collectFullState();
                // 查找卡牌信息
                var cardInfo = null;
                var hand = this.HandChess || [];
                for (var i = 0; i < hand.length; i++) {
                    if (hand[i] && (hand[i].goodsID === goodsID || hand[i].GoodsID === goodsID)) {
                        cardInfo = hand[i];
                        break;
                    }
                }
                if (!cardInfo) {
                    var lineup = this.SelfInfo ? (this.SelfInfo.LineUpChess || []) : [];
                    for (var i = 0; i < lineup.length; i++) {
                        if (lineup[i] && (lineup[i].goodsID === goodsID || lineup[i].GoodsID === goodsID)) {
                            cardInfo = lineup[i];
                            break;
                        }
                    }
                }
                origSell.call(this, goodsID);
                setTimeout(function() {
                    var stateAfter = collectFullState();
                    recordAction('sell', {
                        goodsID: goodsID,
                        chessID: cardInfo ? (cardInfo.chessID || cardInfo.ChessID || 0) : 0,
                        spellID: cardInfo ? (cardInfo.spellID || cardInfo.SpellID || 0) : 0,
                        isFollowUp: cardInfo ? isFollowUpCard(cardInfo) : false
                    }, stateBefore, stateAfter);
                }, 400);
            };
            m.ReqShopRecycleChess.__hooked = true;
            console.log('[数据] Hook: 遣散');
        }

        // ----- 5. 上阵 -----
        var origLineUp = m.ReqChessLineUp;
        if (origLineUp && !origLineUp.__hooked) {
            m.ReqChessLineUp = function(positionChess, force, checkOperate) {
                var stateBefore = collectFullState();
                // 记录变化
                var oldLineup = this.SelfInfo ? this.SelfInfo.LineUpGoodsIDs : [];
                origLineUp.call(this, positionChess, force, checkOperate);
                setTimeout(function() {
                    var stateAfter = collectFullState();
                    // 找出变化
                    var changes = [];
                    var newLineup = stateAfter.lineup || [];
                    for (var i = 0; i < Math.max(oldLineup.length, positionChess.length); i++) {
                        var oldVal = oldLineup[i] || 0;
                        var newVal = positionChess[i] || 0;
                        if (oldVal !== newVal) {
                            changes.push({
                                position: i,
                                oldGoodsID: oldVal,
                                newGoodsID: newVal
                            });
                        }
                    }
                    recordAction('lineup', {
                        changes: changes,
                        newLineup: positionChess,
                        oldLineup: oldLineup
                    }, stateBefore, stateAfter);
                }, 500);
            };
            m.ReqChessLineUp.__hooked = true;
            console.log('[数据] Hook: 上阵');
        }

        // ----- 6. 使用锦囊 -----
        var origUseSpell = m.ReqChessUseSpell;
        if (origUseSpell && !origUseSpell.__hooked) {
            m.ReqChessUseSpell = function(spellGoodsID, targets) {
                var stateBefore = collectFullState();
                // 查找锦囊信息
                var hand = this.HandChess || [];
                var cardInfo = null;
                for (var i = 0; i < hand.length; i++) {
                    if (hand[i] && (hand[i].goodsID === spellGoodsID || hand[i].GoodsID === spellGoodsID)) {
                        cardInfo = hand[i];
                        break;
                    }
                }
                origUseSpell.call(this, spellGoodsID, targets);
                setTimeout(function() {
                    var stateAfter = collectFullState();
                    recordAction('useSpell', {
                        goodsID: spellGoodsID,
                        spellID: cardInfo ? (cardInfo.spellID || cardInfo.SpellID || 0) : 0,
                        targets: targets || []
                    }, stateBefore, stateAfter);
                }, 600);
            };
            m.ReqChessUseSpell.__hooked = true;
            console.log('[数据] Hook: 使用锦囊');
        }

        // ----- 7. 随征 -----
        var origFollowUp = m.ReqChessFollowUp;
        if (origFollowUp && !origFollowUp.__hooked) {
            m.ReqChessFollowUp = function(targetGoodsID, followUpGoodsID) {
                var stateBefore = collectFullState();
                // 查找随征卡信息
                var hand = this.HandChess || [];
                var followUpInfo = null;
                for (var i = 0; i < hand.length; i++) {
                    if (hand[i] && (hand[i].goodsID === followUpGoodsID || hand[i].GoodsID === followUpGoodsID)) {
                        followUpInfo = hand[i];
                        break;
                    }
                }
                // 查找目标信息
                var lineup = this.SelfInfo ? (this.SelfInfo.LineUpChess || []) : [];
                var targetInfo = null;
                for (var i = 0; i < lineup.length; i++) {
                    if (lineup[i] && (lineup[i].goodsID === targetGoodsID || lineup[i].GoodsID === targetGoodsID)) {
                        targetInfo = lineup[i];
                        break;
                    }
                }
                origFollowUp.call(this, targetGoodsID, followUpGoodsID);
                setTimeout(function() {
                    var stateAfter = collectFullState();
                    recordAction('followUp', {
                        targetGoodsID: targetGoodsID,
                        targetChessID: targetInfo ? (targetInfo.chessID || targetInfo.ChessID || 0) : 0,
                        followUpGoodsID: followUpGoodsID,
                        followUpChessID: followUpInfo ? (followUpInfo.chessID || followUpInfo.ChessID || 0) : 0
                    }, stateBefore, stateAfter);
                }, 500);
            };
            m.ReqChessFollowUp.__hooked = true;
            console.log('[数据] Hook: 随征');
        }

        // ----- 8. 升级营帐 -----
        var origLevelUp = m.ReqShopLevelUp;
        if (origLevelUp && !origLevelUp.__hooked) {
            m.ReqShopLevelUp = function() {
                var stateBefore = collectFullState();
                var cost = this.ShopLevelUpCost || 0;
                origLevelUp.call(this);
                setTimeout(function() {
                    var stateAfter = collectFullState();
                    recordAction('levelUp', {
                        cost: cost,
                        newLevel: stateAfter.shopLevel || 0
                    }, stateBefore, stateAfter);
                }, 400);
            };
            m.ReqShopLevelUp.__hooked = true;
            console.log('[数据] Hook: 升级营帐');
        }

        // ----- 9. 游戏结束 -----
        var origGameOver = m.onNotifyChessGameOver;
        if (origGameOver && !origGameOver.__hooked) {
            m.onNotifyChessGameOver = function(e) {
                gameData.isGameOver = true;
                gameData.endTime = new Date().toISOString();
                // 记录最终状态
                var finalState = collectFullState();
                recordAction('gameOver', {
                    rank: m.BattleEndProtoData ? m.BattleEndProtoData.rank : 0,
                    finalState: finalState
                }, finalState, null);
                // 完整下载
                downloadData('gameOver');
                origGameOver.call(this, e);
            };
            m.onNotifyChessGameOver.__hooked = true;
            console.log('[数据] Hook: 游戏结束');
        }

        console.log('[数据] Hook完成！');
    }

    // ============================================================
    // 数据下载
    // ============================================================
    function downloadData(reason) {
        if (!gameData || gameData.trajectory.length === 0) {
            console.log('[数据] 无数据可下载');
            return;
        }

        var data = {
            metadata: {
                version: '1.0.0',
                exportedAt: new Date().toISOString(),
                reason: reason || 'manual',
                totalSteps: gameData.stepCount,
                totalRounds: Object.keys(gameData.rounds).length
            },
            global: gameData.global,
            rounds: gameData.rounds,
            trajectory: gameData.trajectory,
            summary: {
                actionCounts: {},
                roundCount: Object.keys(gameData.rounds).length
            }
        };

        // 统计动作类型
        data.trajectory.forEach(function(t) {
            var type = t.type || 'unknown';
            data.summary.actionCounts[type] = (data.summary.actionCounts[type] || 0) + 1;
        });

        var json = JSON.stringify(data, null, 2);
        var filename = 'tavern_data_' + gameData.global.gameId + '_' + Date.now() + '.json';

        // 尝试下载
        try {
            if (typeof GM_download === 'function') {
                GM_download({
                    url: 'data:application/json;charset=utf-8,' + encodeURIComponent(json),
                    name: filename,
                    saveAs: false
                });
                console.log('[数据] 下载成功:', filename);
            } else {
                // 备用：使用Blob下载
                var blob = new Blob([json], { type: 'application/json' });
                var url = URL.createObjectURL(blob);
                var link = document.createElement('a');
                link.href = url;
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                link.remove();
                URL.revokeObjectURL(url);
                console.log('[数据] 下载成功 (备用):', filename);
            }
        } catch(e) {
            console.error('[数据] 下载失败:', e);
            // 在控制台显示数据
            console.log('[数据] 可复制数据:', json);
        }
    }

    // ============================================================
    // 获取状态（带缓存）
    // ============================================================
    var cachedState = null;
    var cacheTime = 0;
    var CACHE_TTL = 100;

    function getCachedState() {
        var now = Date.now();
        if (cachedState && (now - cacheTime) < CACHE_TTL) {
            return cachedState;
        }
        cachedState = collectFullState();
        cacheTime = now;
        return cachedState;
    }

    // ============================================================
    // 初始化
    // ============================================================
    function init() {
        // 收集全局信息
        var global = collectGlobalInfo();
        if (global) {
            gameData.global = global;
            // 更新玩家数量
            try {
                var m = getManager();
                if (m && m.headInfoList) {
                    gameData.global.playerCount = m.headInfoList.length;
                }
            } catch(e) {}
            console.log('[数据] 全局信息:', global);
        }

        // 初始化回合
        var m = getManager();
        if (m) {
            gameData.currentRound = m.CurRound || m.curRound || m.Turn || m.turn || 0;
        }

        // 记录初始状态
        var initialState = collectFullState();
        if (initialState) {
            recordAction('init', {
                initial: true,
                phase: initialState.phase
            }, null, initialState);
        }

        // Hook游戏操作
        hookGameOperations();

        console.log('[数据] 数据收集器已启动');
        console.log('[数据] 当前数据:', gameData);
        console.log('[数据] 命令:');
        console.log('  __data.download() - 下载数据');
        console.log('  __data.status()   - 查看状态');
        console.log('  __data.state()    - 获取当前状态');
        console.log('  __data.clear()    - 清空数据');
    }

    // ============================================================
    // 暴露控制台接口
    // ============================================================
    window.__data = {
        download: function() { downloadData('manual'); },
        status: function() {
            console.log('===== 数据收集状态 =====');
            console.log('步数:', gameData.stepCount);
            console.log('回合:', gameData.currentRound);
            console.log('轨迹长度:', gameData.trajectory.length);
            console.log('是否结束:', gameData.isGameOver);
            console.log('全局:', gameData.global);
            console.log('回合数:', Object.keys(gameData.rounds).length);
        },
        state: function() {
            var state = collectFullState();
            console.log('===== 当前状态 =====');
            console.log(state);
            return state;
        },
        clear: function() {
            gameData.trajectory = [];
            gameData.rounds = {};
            gameData.stepCount = 0;
            console.log('[数据] 已清空');
        },
        // 获取完整数据
        get: function() {
            return gameData;
        },
        // 导出为JSON
        export: function() {
            var data = {
                global: gameData.global,
                rounds: gameData.rounds,
                trajectory: gameData.trajectory,
                stepCount: gameData.stepCount
            };
            return JSON.stringify(data, null, 2);
        }
    };

    // ============================================================
    // 启动
    // ============================================================
    setTimeout(init, 3000);

    console.log('========================================');
    console.log('📊 自走棋训练数据收集器 v1.0.0');
    console.log('========================================');
    console.log('📌 功能:');
    console.log('  ✅ 收集商店/手牌/上阵状态');
    console.log('  ✅ 收集金币/装备/回合信息');
    console.log('  ✅ Hook 7种操作: 刷新/锁定/购买/遣散/上阵/锦囊/随征');
    console.log('  ✅ 自动下载 (每100步)');
    console.log('💻 控制台命令:');
    console.log('  __data.download() - 下载数据');
    console.log('  __data.status()   - 查看状态');
    console.log('  __data.state()    - 获取当前状态');
    console.log('  __data.clear()    - 清空数据');
    console.log('========================================');

})();