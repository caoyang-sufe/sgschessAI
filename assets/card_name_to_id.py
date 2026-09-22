# -*- coding: utf-8 -*-
# @author: caoyang
# @email: caoyang@stu.sufe.edu.cn

import os
import pandas as pd

card_root = "./card"
chess_df = pd.read_csv("ChessMap.txt", sep='\t', header=0, dtype=str)
spell_df = pd.read_csv("SpellMap.txt", sep='\t', header=0, dtype=str)

chess_id_to_name = {chess_df.loc[i, "ChessID"]: chess_df.loc[i, "DefaultSkin"] for i in range(chess_df.shape[0])}
spell_id_to_name = {spell_df.loc[i, "SpellID"]: spell_df.loc[i, "DefaultSkin"] for i in range(spell_df.shape[0])}

name_to_id = dict()

# 同一个 chessName 只可能对应一个 ID，映射为 String
for id_, name in chess_id_to_name.items():
	if id_.endswith('1'):
		name_to_id[name] = id_

# 同一个 SpellName 可能对应多个 ID（先驱·一、先驱·二），映射为 List
for id_, name in spell_id_to_name.items():
	if name in name_to_id:
		name_to_id[name].append(id_)
	else:
		name_to_id[name] = [id_]

for filename in os.listdir(card_root):
	name = filename.split('.')[0]
	suffix = filename.split('.')[-1]
	if name in name_to_id:
		if isinstance(name, list):
			# 锦囊可能要复制多个图片
			for id_ in name_to_id[name]:
				os.system(f"copy {card_root}/{filename} {card_root}/{id_}.{suffix}")
		elif isinstance(name, str):
			os.rename(f"{card_root}/{filename}", f"{card_root}/{name_to_id[name]}.{suffix}")
		else:
			raise Exception(f"Unknown data type: {type(name)}")

	else:
		print(f"{name} is not in dict")
