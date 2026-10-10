# -*- coding: utf-8 -*-
"""结构回归测试（原名「端到端行为测试」，名不副实，v1.55.1 更名）：
验证 SKILL.md 路由可达性 + 输出格式完整性 + 自检机制存在性。
**不调用 AI**，只做静态结构断言——真正的行为级测试需固定 prompt + 期望结构实跑并存档，尚未实现。"""
import re, os, sys, json
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, 'SKILL.md')
REFS = os.path.join(ROOT, 'references')
TP = os.path.join(ROOT, 'test-prompts.json')

fails = []
def check(cond, msg, detail=''):
    if cond:
        print(f'  ✅ {msg}')
    else:
        print(f'  ❌ {msg}' + (f' — {detail}' if detail else ''))
        fails.append(msg)

print('=' * 70)
print('端到端行为测试（路由可达性 + 输出格式 + 自检机制）')
print('=' * 70)

sk = open(SKILL, encoding='utf-8').read()
tp = json.load(open(TP, encoding='utf-8'))
prompts = tp.get('prompts', [])

# === 1. 路由可达性：每个 prompt 的 expects 应能映射到 SKILL.md 路由表 ===
print('\n[1. 路由可达性]')
# Extract routing table from SKILL.md
# v1.40.2 修复：兼容路由表尾部的 ` ~XK tok` 标注（原正则要求反引号后紧跟 |，token 标注后恒为 0 匹配）
route_rows = re.findall(r'\|\s*([^|]+?)\s*\|\s*' + chr(96) + r'references/([^' + chr(96) + r']+)' + chr(96) + r'[^|]*\|', sk)
route_map = {}
for scenario, fname in route_rows:
    route_map[fname.strip()] = scenario.strip()

check(len(route_map) >= 24, f'路由表解析成功（{len(route_map)} 条）', '正则失效或路由表缩水')
_ghost_routes = sorted(f for f in route_map if not os.path.exists(os.path.join(REFS, f)))
check(not _ghost_routes, '路由表指向的文件全部存在', str(_ghost_routes[:4]))

# All reference files
all_refs = sorted([f for f in os.listdir(REFS) if f.endswith('.md')])
# Check every reference file is mentioned in SKILL.md (routing table or text)
for f in all_refs:
    check(f in sk, f'SKILL.md 引用 {f}', f'未在 SKILL.md 中出现')

# === 2. 输出格式完整性：SKILL.md Step 5 必须指定所有输出要素 ===
print('\n[2. 输出格式完整性]')
step5 = re.search(r'### Step 5.*?(?=###|## )', sk, re.S | re.M)
if step5:
    s5 = step5.group(0)
    check('最推荐' in s5, 'Step5 含「最推荐的一版」')
    check('备选' in s5, 'Step5 含「备选」')
    check('为什么' in s5 and '有效' in s5, 'Step5 含「为什么有效」')
    check('避坑' in s5, 'Step5 含「避坑提醒」')
    check('自检' in s5, 'Step5 含「自检记录」')
    check('改写对比' in s5 or '原句' in s5, 'Step5 含「改写对比表」')
    check('≤3 句' in s5 or '≤5 行' in s5, 'Step5 含「长度适配」')
else:
    check(False, 'Step 5 未找到')

# === 3. 自检机制存在性 ===
print('\n[3. 自检机制]')
step4 = re.search(r'### Step 4.*?(?=### Step 5)', sk, re.S | re.M)
if step4:
    s4 = step4.group(0)
    check('3~5 遍' in s4 or '3 遍' in s4, 'Step4 含自检遍数（3~5）')
    check('高风险' in s4, 'Step4 含高风险判定')
    check('低风险' in s4, 'Step4 含低风险判定')
    check('STOP' in s4, 'Step4 含 STOP 约束')
    check('语气' in s4 and '温度' in s4, 'Step4 含第1遍（语气温度）')
    check('环境' in s4 and '场合' in s4, 'Step4 含第2遍（环境场合）')
    check('分寸' in s4, 'Step4 含第3遍（方式分寸）')
    check('逻辑' in s4 and '事实' in s4, 'Step4 含第4遍（逻辑事实）')
    check('目标' in s4 and '边界' in s4, 'Step4 含第5遍（目标边界）')
else:
    check(False, 'Step 4 未找到')

# === 4. 模式判定完整性 ===
print('\n[4. 模式判定]')
check('实战' in sk and '教练' in sk and '实时' in sk, '三种模式均存在')
check('反触发' in sk, '反触发机制存在')
check('安全升级' in sk, '安全升级条款存在')
check('铁律' in sk, '铁律存在')

# === 5. test-prompts 覆盖度 ===
print('\n[5. test-prompts 覆盖度]')
check(len(prompts) >= 26, f'prompt 数量充足（{len(prompts)}，阈值 26）')
# Check each prompt has required fields
for p in prompts:
    check('id' in p and 'prompt' in p and 'expects' in p, f'prompt {p.get("id","?")} 字段完整')

# === 6. 跨库引用可达性（e2e 视角）===
print('\n[6. 跨库引用可达性]')
# All 11X sub-files
subs = [f for f in all_refs if re.match(r'11[a-g]-', f)]
# Collect all ### N.M definitions across sub-files
defined = set()
for f in subs:
    content = open(os.path.join(REFS, f), encoding='utf-8').read()
    defined |= set(re.findall(r'^###\s+(\d+\.\d+)\s', content, re.M))
    defined |= set(re.findall(r'§(\d+\.\d+)', content))
# Check 09库 references
_09_subs = ['09a-职场与面试.md','09b-亲密与家庭.md','09c-社交与线上.md','09d-消费与维权.md','09e-目录与索引.md']
c09 = '\n'.join(open(os.path.join(REFS, f), encoding='utf-8').read() for f in _09_subs)
refs_09 = set(re.findall(r'11([a-g])\s*库\s*§(\d+\.\d+)', c09))
dangling = [(p, r) for p, r in refs_09 if r not in defined]
check(not dangling, f'09库→11X库引用全可达（{len(refs_09)} unique）', str(dangling[:3]))
# v1.40.1 新增：04库→11X库引用可达性
if os.path.exists(os.path.join(REFS, '04-生活社交话术库.md')):
    c04 = open(os.path.join(REFS, '04-生活社交话术库.md'), encoding='utf-8').read()
    refs_04 = set(re.findall(r'11([a-g])\s*库\s*§(\d+\.\d+)', c04))
    dangling_04 = [(p, r) for p, r in refs_04 if r not in defined]
    check(not dangling_04, f'04库→11X库引用全可达（{len(refs_04)} unique）', str(dangling_04[:3]))
# v1.40.1 新增：SKILL.md→11X库引用可达性
refs_sk = set(re.findall(r'11([a-g])\s*库\s*§(\d+\.\d+)', sk))
dangling_sk = [(p, r) for p, r in refs_sk if r not in defined]
check(not dangling_sk, f'SKILL.md→11X库引用全可达（{len(refs_sk)} unique）', str(dangling_sk[:3]))

# === 结果 ===
print('\n' + '=' * 70)
print(f'端到端行为测试：{len(fails)} 项失败' + ('' if fails else ' ✅ 全通过'))
print('=' * 70)
sys.exit(1 if fails else 0)
