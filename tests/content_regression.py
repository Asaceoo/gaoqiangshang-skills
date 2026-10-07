#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
内容质量回归测试：法律准确性 / 红线一致性 / 过期声明。

设计理由（v1.37.6）：
索引回归与边界回归都不验「内容事实正确性」。独立审查发现的
4 项法律错误（定金成立要件、主动辞职补偿、刑法条号、监管机构名称）
全部逃过了 48 项自动自检 —— 因为 verify 只验结构与口径，不验事实。

本测试把已确认的事实错误固化为断言，防止回退。

用法: python tests/content_regression.py [--verbose]
退出码: 0 全部通过; 1 有问题
"""
import os, re, sys, json, argparse
sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, 'tests', 'content_regression.json')


def read_all_refs():
    d = os.path.join(ROOT, 'references')
    out = {}
    for f in sorted(os.listdir(d)):
        out[f] = open(os.path.join(d, f), encoding='utf-8').read()
    return out


def run(verbose=False):
    data = json.load(open(TESTS, encoding='utf-8'))
    refs = read_all_refs()
    blob = '\n'.join(refs.values())
    skill = open(os.path.join(ROOT, 'SKILL.md'), encoding='utf-8').read()
    alltext = blob + '\n' + skill
    refs_blob = blob

    print('=' * 80)
    print('内容质量回归测试（法律准确性 / 红线一致性 / 过期声明）')
    print('=' * 80)
    fails = []

    def check(ok, label, detail=''):
        if not ok:
            fails.append(label)
        if verbose or not ok:
            print(f"  {'✅' if ok else '❌'} {label}" + (f"  {detail}" if detail else ""))

    # --- 法律准确性（默认全库；scope=references_only 时仅查 references）---
    print('\n[法律准确性]')
    for c in data['legal']:
        scope = refs_blob if c.get('scope') == 'references_only' else alltext
        for kw in c.get('must_contain', []):
            check(kw in scope, f"{c['id']} {c['topic']}：含「{kw}」", c['basis'])
        for kw in c.get('must_not_contain', []):
            check(kw not in scope, f"{c['id']} {c['topic']}：不应含「{kw}」", c['basis'])

    # --- 一致性 ---
    print('\n[红线与规则一致性]')
    for c in data['consistency']:
        for kw in c.get('must_contain', []):
            check(kw in alltext, f"{c['id']} {c['topic']}：含「{kw}」", c['basis'])
        for kw in c.get('must_not_contain', []):
            check(kw not in alltext, f"{c['id']} {c['topic']}：不应含「{kw}」", c['basis'])

    # --- 过期声明 ---
    print('\n[过期声明]')
    c11 = refs.get('11-平台榜单与实战话术库.md', '')
    lines = c11.split('\n')
    for c in data['stale_claims']:
        if c['id'] == 'S1':
            for name, expect_line in c['expect_actual'].items():
                m = re.search(r'^##\s*' + ('场景索引' if '索引' in name else r'五、「症状 → 方法」检索速查表'), c11, re.M)
                actual = c11[:m.start()].count('\n') + 1 if m else -1
                check(actual == expect_line or f'offset={actual}' in skill,
                      f"S1 {name} 坐标：实测 L{actual}",
                      f"SKILL.md 应引用 offset={actual}")
        elif c['id'] == 'S2':
            for kw in c.get('must_not_contain', []):
                check(kw not in skill, f"S2 {c['topic']}：不应含「{kw}」", c['basis'])
        elif c['id'] == 'S3':
            ver = re.search(r'version:\s*"([^"]+)"', skill)
            if ver:
                v = ver.group(1)
                rd = open(os.path.join(ROOT, 'README.md'), encoding='utf-8').read()
                check(f'v{v}' in rd, f"S3 README 版本声明含 v{v}", 'README 版本须与 SKILL 一致')

    # --- v1.39.0 新库完整性 ---
    print('\n[新库完整性]')
    nlibs = data.get('new_libraries', {}).get('checks', [])
    for c in nlibs:
        fp = os.path.join(ROOT, 'references', c['lib'])
        if not os.path.exists(fp):
            check(False, f"{c['id']} {c['lib']} 存在", '文件缺失')
            continue
        body = open(fp, encoding='utf-8').read()
        check(len(body) > 2000, f"{c['id']} {c['lib']} 非空壳（{len(body):,} 字符）")
        for kw in c.get('must_contain', []):
            check(kw in body, f"{c['id']} {c['lib']}：含「{kw}」", c.get('note', ''))

    # --- 路由可达性：SKILL.md 必须引用全部 references 库 ---
    print('\n[路由可达性]')
    refd = set(re.findall(r'references/([0-9]{2}-[^\s`|)]+\.md)', skill))
    actual = {f for f in os.listdir(os.path.join(ROOT, 'references')) if f.endswith('.md')}
    check(not (refd - actual), f"SKILL.md 引用的库全部存在（{len(refd)} 个）", f"缺失 {refd - actual}")
    check(not (actual - refd), f"所有库都被 SKILL.md 引用（{len(actual)} 个）", f"未引用 {actual - refd}")

    print('\n' + '=' * 80)
    total = len(fails)
    print(f"失败项：{total}")
    for f in fails:
        print(f"  ❌ {f}")
    print('=' * 80)
    return 1 if fails else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--verbose', '-v', action='store_true')
    a = ap.parse_args()
    sys.exit(run(a.verbose))
