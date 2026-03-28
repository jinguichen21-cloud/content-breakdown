# -*- coding: utf-8 -*-
"""修复 B 站 API 的中文编码问题"""

import re

file_path = r"C:\Users\li'shang\Desktop\skill-content-crawler\scripts\bilibili\bilibili_api.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 替换查询字符串构建部分，添加 URL 编码
old_code = 'query_string = "&".join([f"{k}={v}" for k, v in params.items()])'
new_code = 'query_string = "&".join([f"{k}={quote(str(v), safe=\'\')}" for k, v in params.items()])'

if old_code in content:
    content = content.replace(old_code, new_code)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("✅ 已成功修复 B 站 API 的中文编码问题")
else:
    print("❌ 未找到需要替换的代码，可能已经修复过")
    # 显示当前代码
    match = re.search(r'query_string = .*?params\.items\(\)\)', content)
    if match:
        print(f"当前代码：{match.group()}")
