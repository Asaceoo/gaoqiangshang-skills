#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
索引回归测试：用「独立对抗验证」产出的真实用户口语，检查场景索引是否仍能命中。

设计要点（教训来自 v1.37.4）：
- 出题人 ≠ 索引作者。本测试集的用例来自独立 subagent 的对抗测试，
  因而包含索引作者的系统性盲区（被动挨骂、跨库、跨视角）。
- 作者自测容易「按索引的语言出题」，导致虚高命中率；必须用固定外部用例回归。

用法:
    python tests/index_regression.py            # 跑测试
    python tests/index_regression.py --verbose  # 显示每条命中详情
退出码: 0 = 全部命中; 1 = 有缺口
"""
import os, re, sys, json, argparse
sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, 'tests', 'index_regression.json')
REF11 = os.path.join(ROOT, 'references', '11-平台榜单与实战话术库.md')
REF09 = os.path.join(ROOT, 'references', '09-高频场景回复案例集.md')


def load_index():
    """返回 (11库场景索引文本, 11库全文, 09库全文)"""
    c11 = open(REF11, encoding='utf-8').read()
    c09 = open(REF09, encoding='utf-8').read()
    m = re.search(r'^## 场景索引.*?(?=^## )', c11, re.S | re.M)
    return (m.group(0) if m else ''), c11, c09


def run(verbose=False):
    data = json.load(open(TESTS, encoding='utf-8'))
    idx, c11, c09 = load_index()
    if not idx:
        print('❌ 未找到 `## 场景索引`'); return 1

    hits, misses = [], []
    print('=' * 80)
    print('索引回归测试（用例来自独立对抗验证，含作者盲区）')
    print('=' * 80)
    for c in data['cases']:
        q = c['q']
        kws = c['must_match_any']
        # must_match_any: 任一关键词命中；must_match_all: 全部命中（用于收紧过宽的用例）
        need_all = c.get('must_match_all') or []
        def _ok(line):
            if not line.strip().startswith('|'): return False
            if any(k in line for k in kws) is False and kws: return False
            return all(k in line for k in need_all)
        matched = [l.strip() for l in idx.split('\n') if _ok(l)]
        if matched:
            hits.append(c)
            if verbose:
                print(f"\n✅ [{c['id']}] {q}")
                print(f"   类型: {c.get('type','')}")
                for m in matched[:2]:
                    print(f"   → {m[:96]}")
        else:
            misses.append(c)
            print(f"\n❌ [{c['id']}] {q}")
            print(f"   类型: {c.get('type','')}")
            print(f"   期望关键词(任一): {kws}")
            if c.get('note'):
                print(f"   备注: {c['note']}")

    total = len(data['cases'])
    print('\n' + '=' * 80)
    print(f'命中 {len(hits)}/{total}  ({len(hits)/total*100:.0f}%)')
    if misses:
        print(f'\n缺口 {len(misses)} 条：')
        for c in misses:
            print(f"  · [{c['id']}] {c['q']}  ← 关键词 {c['must_match_any']}")
    print('=' * 80)
    return 1 if misses else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--verbose', '-v', action='store_true')
    a = ap.parse_args()
    sys.exit(run(a.verbose))
