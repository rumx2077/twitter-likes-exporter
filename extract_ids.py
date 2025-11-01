import re
import os
from collections import defaultdict

# --- 配置 ---
# 正则表达式查找 tweet_id (匹配 "id": "123..." 或 "tweet_id": "123...")
pattern = r'^(?: {4}"id"| {6}"tweet_id")\s*:\s*"(\d+)"'
# 需要处理的 JSON 文件列表 (或纯ID的TXT文件)
input_files = [
    'sites/liked_tweets/liked_tweets.7.json',
    'twitter-喜欢-1746605058355.json',
]
summary_file_name = 'unique_ids_summary.txt'  # 存储独有ID的摘要文件名
# -------------

all_ids_by_file = {}  # 存储每个文件的ID原始列表 {文件名: [id1, id2, ...]}
all_ids_sets = {}  # 存储每个文件的ID集合 {文件名: {id1, id2, ...}} (用于快速比较)

# 1. 提取每个文件的ID并保存(保持原始顺序，不去重)
print("--- Extracting IDs from files ---")
for input_filename in input_files:
    base_name, _ = os.path.splitext(input_filename)
    output_filename = f'ids_{base_name}.txt'
    print(f"Processing '{input_filename}' -> '{output_filename}'")

    try:
        with open(input_filename, 'r', encoding='utf-8') as f_in:
            content = f_in.read()
        if input_filename.split('.')[-1] == 'txt':
            ids_found = content.splitlines()
        else:
            ids_found = re.findall(pattern, content, re.MULTILINE)
        if ids_found:
            # 保存完整列表(不去重)
            all_ids_by_file[input_filename] = ids_found

            # 保存集合用于比较(这里需要去重)
            all_ids_sets[input_filename] = set(ids_found)

            # 写入文件 - 保持原始顺序且不去重
            if input_filename.split('.')[-1] != 'txt':
                with open(output_filename, 'w', encoding='utf-8') as f_out:
                    f_out.write('\n'.join(ids_found) + '\n')

            total_ids = len(ids_found)
            unique_ids = len(all_ids_sets[input_filename])
            print(f"  Found {total_ids} total IDs (including duplicates)")
            print(f"  Of which {unique_ids} are unique IDs")

    except FileNotFoundError:
        print(f"  Error: File '{input_filename}' not found. Skipping.")
    except Exception as e:
        print(f"  An error occurred processing '{input_filename}': {e}. Skipping.")

# 2. 比较并找出每个文件独有的ID
print("\n--- Finding unique IDs per file ---")
unique_ids_summary = {}  # {文件名: [独有id1, 独有id2, ...]}

if len(all_ids_sets) > 1:  # 只有多于一个文件时比较才有意义
    filenames = list(all_ids_sets.keys())
    for i, current_filename in enumerate(filenames):
        current_ids_set = all_ids_sets[current_filename]
        if not current_ids_set:
            continue  # 跳过没有ID的文件

        # 合并 *其他* 所有文件的ID集合
        other_ids_union = set()
        for j, other_filename in enumerate(filenames):
            if i != j:  # 跳过当前文件自身
                other_ids_union.update(all_ids_sets[other_filename])

        # 计算差集，得到当前文件独有的ID
        unique_to_current_set = current_ids_set - other_ids_union

        if unique_to_current_set:
            # 提取独有ID时保持原始顺序并去除重复
            # (这里去重是为了摘要文件的清晰性)
            unique_in_order = []
            seen = set()
            for id in all_ids_by_file[current_filename]:
                if id in unique_to_current_set and id not in seen:
                    unique_in_order.append(id)
                    seen.add(id)

            unique_ids_summary[current_filename] = unique_in_order
            print(f"  '{current_filename}' has {len(unique_in_order)} unique IDs")

# 3. 写入独有ID摘要文件
print(f"\n--- Writing summary to '{summary_file_name}' ---")
if unique_ids_summary:
    with open(summary_file_name, 'w', encoding='utf-8') as f_summary:
        for filename, unique_list in unique_ids_summary.items():
            f_summary.write(f"---{filename}\'s unique IDs---\n")
            f_summary.write('\n'.join(unique_list) + '\n\n')
    print("Summary file created.")
elif len(all_ids_sets) <= 1:
    print("Skipping summary: Need at least two files with IDs to compare.")
else:
    print("No unique IDs found for any file compared to the others.")

print("\nProcessing finished.")
