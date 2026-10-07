#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
边界与鲁棒性回归测试。

设计理由（来自 v1.37.5 独立测试）：
此前的 index_regression 只测「索引能否命中」，完全不覆盖「红线与超范围」，
而独立边界测试 8 题中有 5 题暴露未覆盖或矛盾。

本测试检查 SKILL.md 是否**具备**处理这些边界的明文规程（而非检查话术质量）。

用法: python tests/edge_regression.py [--verbose]
退出码: 0 全部通过; 1 有缺失
"""
import os, re, sys, json, argparse
sys.stdout.reconfigure(encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, 'tests', 'edge_regression.json')
SKILL = os.path.join(ROOT, 'SKILL.md')


def run(verbose=False):
    cases = json.load(open(TESTS, encoding='utf-8'))['cases']
    skill = open(SKILL, encoding='utf-8').read()

    print('=' * 80)
    print('边界与鲁棒性回归测试（用例来自独立测试 indep-C-edge.md）')
    print('=' * 80)
    fails = []
    for c in cases:
        missing = [k for k in c['must_exist'] if k not in skill]
        ok = not missing
        if verbose or not ok:
            print(f"\n{'✅' if ok else '❌'} [{c['id']}] {c['input']}")
            print(f"   类型: {c['type']}")
            print(f"   期望规程: {c['expect_rule']}")
            if missing:
                print(f"   ❌ 缺少明文: {missing}")
                if c.get('note'):
                    print(f"   备注: {c['note']}")
        if not ok:
            fails.append(c)

    print('\n' + '=' * 80)
    print(f'通过 {len(cases)-len(fails)}/{len(cases)}')
    if fails:
        print('\n缺失规程：')
        for c in fails:
            print(f"  · [{c['id']}] {c['type']}  ← 缺 {[k for k in c['must_exist'] if k not in skill]}")
    print('=' * 80)
    return 1 if fails else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--verbose', '-v', action='store_true')
    a = ap.parse_args()
    sys.exit(run(a.verbose))
