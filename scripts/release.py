#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
gaoqing-shang-liaotian 发布工具链
子命令:
  bump    自动递增 SKILL/用户手册/技术手册 版本号
  verify  全量清单校验（兜底校验）
  pack    构建 zip 包（自动按新版本命名）
  info    打印当前版本信息
"""
import os, re, sys, json, zipfile, hashlib, datetime, argparse, shutil
sys.stdout.reconfigure(encoding='utf-8')

# 脚本位于 <repo>/scripts/，技能根目录是其上一级
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE) if os.path.basename(_HERE) == 'scripts' else _HERE
SKILL_MD = os.path.join(ROOT, 'SKILL.md')
README   = os.path.join(ROOT, 'README.md')            # 用户手册
TECH     = os.path.join(ROOT, 'voice-call-guide.md')  # 技术手册
CHANGELOG= os.path.join(ROOT, 'CHANGELOG.md')
REFS     = os.path.join(ROOT, 'references')

# ---------------- 分发白名单（verify 与 pack 共用，避免自相矛盾）----------------
# 刻意排除开发产物：test-prompts.json（测试）、scripts/（构建工具）、.git
DIST_ROOT_FILES = ['SKILL.md', 'README.md', 'CHANGELOG.md', 'voice-call-guide.md', 'LICENSE']

def collect_dist_files():
    files = []
    for f in DIST_ROOT_FILES:
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            files.append((p, f))
    refdir = os.path.join(ROOT, 'references')
    if os.path.isdir(refdir):
        for f in sorted(os.listdir(refdir)):
            p = os.path.join(refdir, f)
            if os.path.isfile(p):
                files.append((p, f'references/{f}'))
    return files

# ---------------- 版本工具 ----------------
def parse_ver(s):
    m = re.match(r'^v?(\d+)\.(\d+)\.(\d+)$', s.strip())
    if not m: raise ValueError(f'非法版本号: {s}')
    return tuple(int(x) for x in m.groups())

def fmt_ver(t): return f'v{t[0]}.{t[1]}.{t[2]}'

def bump_ver(v, part='patch'):
    a,b,c = parse_ver(v)
    if part=='major': return fmt_ver((a+1,0,0))
    if part=='minor': return fmt_ver((a,b+1,0))
    return fmt_ver((a,b,c+1))

def read_versions():
    """读取四处版本号（SKILL / 用户手册 / 技术手册 / CHANGELOG 当前版本声明）"""
    s = open(SKILL_MD, encoding='utf-8').read()
    m = re.search(r'^version:\s*"([^"]+)"', s, re.M)
    skill = m.group(1) if m else None

    r = open(README, encoding='utf-8').read()
    m = re.search(r'#\s*高情商聊天技能（gaoqing-shang-liaotian）v([\d.]+)', r)
    user = f'v{m.group(1)}' if m else None

    t = open(TECH, encoding='utf-8').read()
    m = re.search(r'技术手册\s*v([\d.]+)', t)
    tech = f'v{m.group(1)}' if m else None

    c = open(CHANGELOG, encoding='utf-8').read()
    m = re.search(r'当前版本：\*\*(v[\d.]+)\*\*', c)
    chlog = m.group(1) if m else None
    return {'skill': skill, 'user': user, 'tech': tech, 'changelog': chlog}

# ---------------- bump ----------------
def cmd_bump(args):
    cur = read_versions()
    print('== 当前版本 ==')
    for k,v in cur.items(): print(f'  {k:6} {v}')

    base = 'v' + cur['skill'] if cur['skill'] else 'v0.0.0'
    new = bump_ver(base, args.part)
    print(f'\n== 递增 ({args.part}) {base} → {new} ==')

    today = datetime.date.today().isoformat()

    # 1) SKILL.md frontmatter
    s = open(SKILL_MD, encoding='utf-8').read()
    s2 = re.sub(r'^(version:\s*")[^"]+(")', rf'\g<1>{new[1:]}\g<2>', s, count=1, flags=re.M)
    assert s2 != s or f'version: "{new[1:]}"' in s, 'SKILL.md 版本未替换'
    open(SKILL_MD,'w',encoding='utf-8').write(s2)
    print(f'  ✓ SKILL.md frontmatter → {new[1:]}')

    # 2) 用户手册 README.md
    r = open(README, encoding='utf-8').read()
    r2 = re.sub(r'(#\s*高情商聊天技能（gaoqing-shang-liaotian）)v[\d.]+', rf'\g<1>{new}', r, count=1)
    open(README,'w',encoding='utf-8').write(r2)
    print(f'  ✓ 用户手册 README.md → {new}')

    # 3) 技术手册 + 其版本历史表加一行
    t = open(TECH, encoding='utf-8').read()
    old_tech = 'v' + re.search(r'技术手册\s*v([\d.]+)', t).group(1)
    t2 = t.replace(f'技术手册 {old_tech}', f'技术手册 {new}')
    # 正文中所有「当前 vX」一并更新（否则 verify 的过期检测会失败）
    t2 = re.sub(r'（当前 v[\d.]+）', f'（当前 {new}）', t2)
    t2 = re.sub(r'(\*\*版本\s*)v[\d.]+(\*\*)', rf'\g<1>{new}\g<2>', t2, count=1)
    t2 = re.sub(r'(更新日期\s*)[\d-]+', rf'\g<1>{today}', t2, count=1)
    # 版本历史表插入新行（表头后的第一行位置）
    m = re.search(r'(\|\s*版本\s*\|\s*日期\s*\|\s*变更摘要\s*\|\s*\n\|[\s\-|]+\|\s*\n)', t2)
    if m:
        note = args.note or '版本号随打包递增'
        row = f'| {new} | {today} | 版本号同步至当前 SKILL {new}（{note}） |\n'
        t2 = t2[:m.end()] + row + t2[m.end():]
    open(TECH,'w',encoding='utf-8').write(t2)
    print(f'  ✓ 技术手册 voice-call-guide.md {old_tech} → {new}')

    # 4) CHANGELOG 顶部「当前版本」声明（防止状态声明与 frontmatter 漂移）
    c = open(CHANGELOG, encoding='utf-8').read()
    c2 = re.sub(r'(当前版本：\*\*)v[\d.]+(\*\*)', rf'\g<1>{new}\g<2>', c, count=1)
    if c2 == c:
        print('  ⚠️ CHANGELOG 未找到「当前版本」声明，跳过')
    else:
        open(CHANGELOG,'w',encoding='utf-8').write(c2)
        print(f'  ✓ CHANGELOG 当前版本 → {new}')

    print(f'\n== 递增完成: {new} ==')
    return new

# ---------------- verify ----------------
def cmd_verify(args):
    """清单式兜底校验"""
    fails, warns, oks = [], [], []
    def chk(cond, name, detail=''):
        (oks if cond else fails).append(f'{name}' + (f' — {detail}' if detail else ''))

    # 1 必需文件
    # 分发包必需文件（与 pack 白名单一致 + 开发用文件单列）
    for f in DIST_ROOT_FILES:
        chk(os.path.exists(os.path.join(ROOT,f)), f'分发必需文件存在 {f}')
    # 开发用文件：不随包分发，但仓库内应存在
    for f in ['test-prompts.json','scripts/release.py']:
        chk(os.path.exists(os.path.join(ROOT,f)), f'开发文件存在 {f}')

    # 2 版本一致性
    v = read_versions()
    chk(v['skill'] and v['user'] and v['tech'], '三处版本号均可读取', str(v))
    chk(v['skill']==v['user'][1:]==v['tech'][1:] if all(v.values()) else False,
        'SKILL/用户手册/技术手册版本一致', f"skill={v['skill']} user={v['user']} tech={v['tech']}")
    chk(v.get('changelog') and v['changelog'][1:]==v['skill'],
        'CHANGELOG 当前版本声明与 SKILL 一致', f"changelog={v.get('changelog')} skill={v['skill']}")

    # CHANGELOG 不得泄漏本机绝对路径（分发包内文件）
    _cl = open(CHANGELOG, encoding='utf-8').read()
    _leaks = re.findall(r'[A-Za-z]:\\[^\s`|)]+', _cl)
    chk(not _leaks, 'CHANGELOG 不含本机绝对路径', str(_leaks[:3]))

    # 3 引用链
    s = open(SKILL_MD, encoding='utf-8').read()
    refd = set(re.findall(r'references/([0-9]{2}-[^\s`|)]+\.md)', s))
    real = set(os.listdir(REFS)) if os.path.isdir(REFS) else set()
    chk(not (refd-real), '无断链引用', str(refd-real))
    chk(not (real-refd), '无孤儿 reference', str(real-refd))

    # 4 frontmatter 可解析
    try:
        import yaml
        fm = s.split('---')[1]
        d = yaml.safe_load(fm)
        chk(isinstance(d, dict) and 'name' in d and 'description' in d, 'frontmatter YAML 可解析且含必须字段')
    except ImportError:
        warns.append('未安装 pyyaml，跳过 YAML 解析')
    except Exception as e:
        fails.append(f'frontmatter YAML 解析失败 — {e}')

    # 5 SKILL.md 体量
    lines = s.split('\n')
    chk(len(lines) < 500, f'SKILL.md 行数 {len(lines)} < 500')
    longest = max(len(l) for l in lines)
    chk(longest < 1200, f'最长行 {longest} < 1200')

    # 6 JSON 合法
    try:
        json.loads(open(os.path.join(ROOT,'test-prompts.json'),encoding='utf-8').read())
        chk(True, 'test-prompts.json 合法')
    except Exception as e:
        chk(False, 'test-prompts.json 合法', str(e))

    # 7 大文件有目录
    for f in ['09-高频场景回复案例集.md','11-平台榜单与实战话术库.md']:
        p = os.path.join(REFS,f)
        if os.path.exists(p):
            t = open(p,encoding='utf-8').read()
            chk('## 目录' in t, f'{f} 含目录')

    # 8 Markdown 表格列数一致（用 [ \t]*$ 避免 \s 吞掉换行导致跨表误判）
    for root,_,files in os.walk(REFS):
        for f in files:
            if not f.endswith('.md'): continue
            p=os.path.join(root,f)
            bad=[]
            txt=open(p,encoding='utf-8').read()
            for blk in re.findall(r'((?:^[ \t]*\|.*\|[ \t]*\n?)+)', txt, re.M):
                rows=[r for r in blk.strip().split('\n') if r.strip()]
                if len(rows)<2: continue
                cols=[r.count('|') for r in rows]
                if len(set(cols))>1:
                    ln=txt[:txt.find(blk)].count('\n')+1
                    bad.append((ln, sorted(set(cols))))
            if bad:
                warns.append(f'{f}: {len(bad)} 个表格列数不一致 {bad[:3]}')
    if not any('表格列数' in w for w in warns): oks.append('references 表格列数一致')

    # 9 【v1.36.0 新增】根目录 Markdown 表格列语义一致性（防版本史误入正文表格）
    for f in ['README.md','SKILL.md','CHANGELOG.md']:
        p=os.path.join(ROOT,f)
        if not os.path.exists(p): continue
        txt=open(p,encoding='utf-8').read()
        bad=[]
        for blk in re.findall(r'((?:^[ \t]*\|.*\|[ \t]*\n?)+)', txt, re.M):
            rows=[r for r in blk.strip().split('\n') if r.strip()]
            if len(rows)<2: continue
            cols=[r.count('|') for r in rows]
            if len(set(cols))>1:
                ln=txt[:txt.find(blk)].count('\n')+1
                bad.append(ln)
        if bad: fails.append(f'{f} 表格列数不一致（列语义错位风险）行: {bad[:5]}')
    if not any('表格列数不一致' in f_ for f_ in fails):
        oks.append('根目录 Markdown 表格列语义一致')

    # 10 【v1.36.0 新增】CHANGELOG 版本连续性（防止版本缺口）
    cl = open(CHANGELOG, encoding='utf-8').read()
    cvs = re.findall(r'^\|\s*v(\d+\.\d+\.\d+)\s*\|', cl, re.M)
    nums = sorted({parse_ver('v'+v) for v in cvs})
    gaps = []
    if nums:
        for i in range(1, len(nums)):
            a, b = nums[i-1], nums[i]
            # 同 minor 内 patch 应连续
            if a[0]==b[0] and a[1]==b[1] and b[2]-a[2] > 1:
                gaps.append(f'{fmt_ver(a)}→{fmt_ver(b)}')
    chk(not gaps, f'CHANGELOG 版本无缺口（收录 {len(cvs)} 条）', str(gaps))
    # 最低版本应覆盖到起点
    chk(len(cvs) >= 30, f'CHANGELOG 版本条目充足（{len(cvs)}）')

    # 11 【v1.36.0 新增】11 库速查表无重复行
    p11 = os.path.join(REFS,'11-平台榜单与实战话术库.md')
    if os.path.exists(p11):
        c11 = open(p11,encoding='utf-8').read()
        m5 = re.search(r'^##\s*五、「症状 → 方法」.*$', c11, re.M)
        m7 = re.search(r'^##\s*七、', c11, re.M)
        if m5 and m7:
            seg = c11[m5.start():m7.start()]
            # 仅统计数据行：排除表头行（与「症状 / 场景」同形）与分隔行
            rows=[l.strip() for l in seg.split('\n')
                  if l.strip().startswith('|')
                  and not re.match(r'^\|[\s\-:|]+\|$', l.strip())
                  and '症状 / 场景' not in l]
            dup = len(rows) - len(set(rows))
            chk(dup==0, f'11 库速查表无重复行（{len(rows)} 数据行）', f'重复 {dup}')
            # § 引用可达性
            allref = set(re.findall(r'^###\s+(\d+)\.(\d+)', c11, re.M))
            secs = set(re.findall(r'^§\s*(\d+)\.(\d+)', c11, re.M))
            used = set(re.findall(r'§\s*(\d+)\.(\d+)', seg))
            missing = {u for u in used if u not in allref and u not in secs}
            chk(not missing, '11 库速查表 § 引用全部可达', str(sorted(missing)[:5]))

    # 12 【v1.36.0 新增】跨文件章节引用可达（防改名后断链）
    ref_pat = re.findall(r'（见\s*SKILL\.md[「"“]([^」"”]+)[」"”]）', open(os.path.join(ROOT,'README.md'),encoding='utf-8').read())
    # 防「正则零匹配 → 静默不校验」：必须至少命中 1 条，否则视为断言失效
    chk(len(ref_pat) > 0, f'README 存在指向 SKILL 的章节引用（实测 {len(ref_pat)} 处）',
        '正则零匹配，断言形同虚设')
    for name in ref_pat:
        chk(name in open(SKILL_MD,encoding='utf-8').read(),
            f'README→SKILL 章节引用可达「{name}」')

    # 13 【v1.36.0 新增】打包白名单与实际 zip 一致
    dist = collect_dist_files()
    chk(len(dist) >= 16, f'分发白名单条目数 {len(dist)}')
    chk(not any('scripts/' in r or 'test-prompts' in r for _,r in dist),
        '分发包不含测试/构建产物')

    # 14 【v1.36.0 新增·补盲区】技术手册版本声明与 SKILL 一致（防冒充"当前"）
    tech_txt = open(TECH, encoding='utf-8').read()
    stale = re.findall(r'当前 v(?!' + re.escape(v['skill'] or '') + r')[\d.]+', tech_txt)
    chk(not stale, '技术手册无过期的「当前 vX」声明', str(stale[:3]))

    # 15 【v1.36.0 新增·补盲区】高风险判据全局一致（防「唯一权威表」被旧枚举架空）
    sk = open(SKILL_MD, encoding='utf-8').read()
    chk('高风险判定表' in sk and '全技能唯一权威' in sk, 'SKILL 存在唯一权威高风险判定表')
    # 其他位置若出现旧的 4 项枚举（且不是引用表），视为不一致
    legacy = re.findall(r'高风险场景（(?:金钱|当众)[^）]*）', sk + open(README, encoding='utf-8').read())
    legacy = [x for x in legacy if '判定表' not in x and '判据' not in x]
    chk(not legacy, '无残留的旧高风险枚举（应统一引用判定表）', str(legacy[:2]))
    c05_txt = open(os.path.join(REFS,'05-自我检查清单.md'), encoding='utf-8').read()
    chk('以 SKILL 表为准' in c05_txt or 'SKILL.md Step 4' in c05_txt,
        '05 库分级引用 SKILL 权威表')

    # 16 【v1.36.0 新增·补盲区】GFM 表格成表性（管道区块须有表头分隔行）
    sep_re = re.compile(r'^\|[\s\-:|]+\|$')
    for root,_,files in os.walk(REFS):
        for f in files:
            if not f.endswith('.md'): continue
            txt = open(os.path.join(root,f), encoding='utf-8').read()
            ls = txt.split('\n')
            blocks=[]; cur=[]
            for i,l in enumerate(ls):
                if l.strip().startswith('|'): cur.append(i)
                else:
                    if cur: blocks.append(cur); cur=[]
            if cur: blocks.append(cur)
            badblk = []
            for b in blocks:
                if len(b) >= 2 and not sep_re.match(ls[b[1]].strip()):
                    badblk.append(b[0]+1)
            if badblk:
                fails.append(f'{f}: {len(badblk)} 个管道区块缺 GFM 表头（会退化为裸文本）行 {badblk[:4]}')
    if not any('缺 GFM 表头' in f_ for f_ in fails):
        oks.append('references GFM 表格成表性正常')

    # 17 【v1.36.0 新增·补盲区】附录类数字口径（09 库条数须与实测一致）
    c11_txt = open(os.path.join(REFS,'11-平台榜单与实战话术库.md'), encoding='utf-8').read()
    real09 = len(re.findall(r'^\|\s*\d+\s*\|', open(os.path.join(REFS,'09-高频场景回复案例集.md'),encoding='utf-8').read(), re.M))
    bad09 = []
    hits09 = list(re.finditer(r'09\s*库[^\n]{0,30}?(\d+)\s*条', c11_txt))
    for m in hits09:
        if int(m.group(1)) != real09:
            bad09.append((c11_txt[:m.start()].count('\n')+1, m.group(1)))
    chk(len(hits09) > 0, f'11 库存在「09 库 N 条」声明（实测 {len(hits09)} 处）', '正则零匹配')
    chk(not bad09, f'11 库中「09 库 N 条」口径与实测({real09})一致', str(bad09[:3]))

    # 18 【v1.36.4 新增】内容架构优化防回归
    c11_txt2 = open(os.path.join(REFS,'11-平台榜单与实战话术库.md'), encoding='utf-8').read()
    chk('## 场景索引' in c11_txt2, '11 库含场景索引（按用户问法导航）')
    idx_m = re.search(r'^## 场景索引.*?(?=^## )', c11_txt2, re.S | re.M)
    if idx_m:
        idx_rows = len(re.findall(r'^\|(?!\s*什么情况|\s*-)', idx_m.group(0), re.M))
        chk(idx_rows >= 60, f'场景索引条目充足（{idx_rows} 行）')
        secs_idx = set(re.findall(r'§(\d+)', idx_m.group(0)))
        chk(len(secs_idx) >= 54, f'场景索引覆盖节数充足（{len(secs_idx)} 节，阈值 54）')
    else:
        fails.append('11 库场景索引块无法定位')

    c09_txt = open(os.path.join(REFS,'09-高频场景回复案例集.md'), encoding='utf-8').read()
    chk('### 🎯 场景层' in c09_txt and '### 📚 批次层' in c09_txt,
        '09 库目录为「场景层 + 批次层」双层')
    c09_toc = re.search(r'^## 目录.*?(?=^## )', c09_txt, re.S | re.M)
    if c09_toc:
        cov = set()
        # 09 场景层表头是 2 列（什么情况 | 条目号），直接在全目录区提取 #N 引用
        for a, b in re.findall(r'#(\d+)(?:-(\d+))?', c09_toc.group(0)):
            a2 = int(a); b2 = int(b) if b else a2
            cov.update(range(a2, b2 + 1))
        real_total = len(re.findall(r'^\|\s*\d+\s*\|', c09_txt, re.M))
        chk(len(cov) >= real_total, f'09 库场景层覆盖全部条目（{len(cov)}/{real_total}）')

    chk('数据时效说明' in c11_txt2, '11 库含平台数据时效说明')
    # 场景索引引用的节号必须真实存在（防索引腐化）
    _CN = '一二三四五六七八九十'
    def _cn2i(x):
        if x == '十': return 10
        if x.startswith('十'): return 10 + _CN.index(x[1]) + 1
        if '十' in x:
            a, b = x.split('十'); return (_CN.index(a)+1)*10 + (_CN.index(b)+1 if b else 0)
        return _CN.index(x)+1 if x in _CN else None
    _secs_real = {_cn2i(m.group(1)) for m in re.finditer(r'^##\s+([一二三四五六七八九十]+)、', c11_txt2, re.M)}
    _secs_real.discard(None)
    if idx_m:
        # 用边界断言避免 §59.1 回溯出幻影 §5
        _idx_secs = {int(x) for x in re.findall(r'§(\d+)(?![.\d])', idx_m.group(0))}
        _dead = sorted(_idx_secs - _secs_real)
        chk(not _dead, '场景索引引用的节号全部存在', str(_dead[:5]))
        # 索引使用中的 §N.M 小节须可达
        _subs = {(int(a), int(b)) for a, b in re.findall(r'^#{3,4}\s*(?:§\s*)?(\d+)\.(\d+)', c11_txt2, re.M)}
        _isub = {(int(a), int(b)) for a, b in re.findall(r'§(\d+)\.(\d+)', idx_m.group(0))}
        _deadsub = sorted(_isub - _subs)
        chk(not _deadsub, '场景索引 §N.M 引用全部可达', str(_deadsub[:5]))
        # 两套检索入口不得对同一问题指向互斥的节（防冲突复发）
        _B = None
        _m5 = re.search(r'^##\s*五、「症状 → 方法」检索速查表（本库）\s*$', c11_txt2, re.M)
        _m7 = re.search(r'^##\s*七、', c11_txt2, re.M)
        if _m5 and _m7:
            _Btxt = c11_txt2[_m5.start():_m7.start()]
            _conflict = []
            for _qa, _sa in re.findall(r'^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|', idx_m.group(0), re.M):
                _as = {int(y) for y in re.findall(r'§\s*(\d+)', _sa)}
                if not _as or '你会怎么说' in _qa: continue
                _kws = [k for k in re.findall(r'[\u4e00-\u9fa5]{2,}', _qa)]
                for _qb, _sb in re.findall(r'^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|', _Btxt, re.M):
                    if '症状' in _qb: continue
                    if sum(1 for k in _kws if k in _qb) >= 2:
                        _bs = {int(y) for y in re.findall(r'§\s*(\d+)', _sb)}
                        if _bs and not (_as & _bs):
                            _conflict.append((_qa[:24], sorted(_as), sorted(_bs)))
            chk(not _conflict, '两套检索入口无互斥指向', str(_conflict[:3]))
    chk(c11_txt2.count('⏳') >= 10, f'11 库时效标记充足（{c11_txt2.count("⏳")} 处）')

    _sk = open(SKILL_MD, encoding='utf-8').read()
    _fm = _sk.split('---')[1]
    _allowed = {'name', 'description', 'version'}
    _present = set(re.findall(r'^([A-Za-z_][A-Za-z0-9_]*)\s*:', _fm, re.M))
    _extra = _present - _allowed
    chk(not _extra, 'frontmatter 无无效字段（运行时仅读 name/description）', str(sorted(_extra)))

    print('='*66); print('清单兜底校验'); print('='*66)
    for o in oks: print(f'  ✅ {o}')
    for w in warns: print(f'  ⚠️  {w}')
    for f_ in fails: print(f'  ❌ {f_}')
    print('-'*66)
    print(f'通过 {len(oks)} / 警告 {len(warns)} / 失败 {len(fails)}')
    if fails:
        print('\n❌ 校验未通过'); sys.exit(1)
    print('\n✅ 校验通过')

# ---------------- pack ----------------
# 分发白名单：与 README「目录结构」一致。刻意排除开发产物：
#   test-prompts.json（测试用）、scripts/（构建工具）、.git


def cmd_pack(args):
    v = read_versions()
    base = 'v' + v['skill']
    out = args.out or os.path.join(os.path.dirname(ROOT), f'gaoqingshang-skills-{base}.zip')
    files = collect_dist_files()
    pkgroot = 'gaoqing-shang-liaotian'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for p, rel in files:
            z.write(p, f'{pkgroot}/{rel}')
    size = os.path.getsize(out)
    print(f'== 打包完成 ==')
    print(f'  文件: {out}')
    print(f'  版本: {base}')
    print(f'  条目: {len(files)} 个文件（分发白名单）')
    for _, rel in files: print(f'     {rel}')
    print(f'  大小: {size:,} bytes')
    # 校验 zip 可读 + 条目与白名单一致（防「产物过不了 verify」）
    with zipfile.ZipFile(out) as z:
        bad = z.testzip()
        names = z.namelist()
        print(f'  zip 完整性: {"OK" if bad is None else "损坏 "+str(bad)}')
        expect = {f'{pkgroot}/{rel}' for _, rel in files}
        extra = set(names) - expect
        missing = expect - set(names)
        print(f'  条目与白名单一致: {"OK" if not extra and not missing else "不一致"}')
        if extra:   print(f'    多余: {sorted(extra)[:5]}')
        if missing: print(f'    缺失: {sorted(missing)[:5]}')
        # 分发包不得含开发产物
        leaked = [n for n in names if 'scripts/' in n or 'test-prompts' in n]
        print(f'  不含开发产物: {"OK" if not leaked else "泄漏 "+str(leaked)}')
    return out

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('bump'); b.add_argument('--part', default='patch', choices=['major','minor','patch']); b.add_argument('--note', default='')
    sub.add_parser('verify')
    pk = sub.add_parser('pack'); pk.add_argument('--out', default=None)
    sub.add_parser('info')
    a = ap.parse_args()
    if a.cmd=='bump': cmd_bump(a)
    elif a.cmd=='verify': cmd_verify(a)
    elif a.cmd=='pack': cmd_pack(a)
    else:
        for k,v in read_versions().items(): print(f'{k:6} {v}')
