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

for id_, name in chess_id_to_name.items():
	if id_.endswith('1'):
		name_to_id[name] = id_

for id_, name in spell_id_to_name.items():
	name_to_id[name] = id_

for filename in os.listdir(card_root):
	name = filename.split('.')[0]
	suffix = filename.split('.')[-1]
	if name in name_to_id:
		os.rename(f"{card_root}/{filename}", f"{card_root}/{name_to_id[name]}.{suffix}")
	else:
		print(f"{name} is not in dict")
