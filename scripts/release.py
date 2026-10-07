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
import os, re, sys, json, zipfile, hashlib, datetime, argparse, shutil, subprocess
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
            if not f.endswith('.md'):
                continue  # 【v1.39.4·A线P2-3】只收库 .md，防杂散文件入包
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

    # 2) 用户手册 README.md —— 【v1.39.0 修复】标题行 + 版本历史行都要同步
    #    原缺陷：只改标题行，导致「（当前版本 **vX**）」长期停留在旧版本
    #    （独立审查 D 线发现 README 写 v1.37.0 而实际 v1.38.0；根因即此）
    r = open(README, encoding='utf-8').read()
    r2 = re.sub(r'(#\s*高情商聊天技能（gaoqing-shang-liaotian）)v[\d.]+', rf'\g<1>{new}', r, count=1)
    n_hist = len(re.findall(r'（当前版本 \*\*v[\d.]+\*\*）', r2))
    r2 = re.sub(r'（当前版本 \*\*v[\d.]+\*\*）', f'（当前版本 **{new}**）', r2)
    if not re.search(r'（当前版本 \*\*v[\d.]+\*\*）', r2):
        # 【v1.39.3 修复】原缺陷：版本历史行缺失时静默跳过（工具闭环实测发现）
        print('  ⚠️ README 未找到「（当前版本 **vX**）」声明行，跳过同步——请手动补回该行，否则 verify 将报警')
    open(README,'w',encoding='utf-8').write(r2)
    print(f'  ✓ 用户手册 README.md → {new}（标题行 + 版本历史 {n_hist} 处）')

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
        # 【v1.39.3 修复】detail 只在失败时显示。
        # 原缺陷：detail 无条件追加，导致成功行也挂着「正则零匹配，断言形同虚设」等
        # 失败说明，读者会误以为校验有问题（工具闭环实测发现）。
        (oks if cond else fails).append(f'{name}' + (f' — {detail}' if (detail and not cond) else ''))

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
    refd = set(re.findall(r'references/([0-9]{2}[a-g]?-[^\s`|)]+\.md)', s))
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
    for f in ['09e-目录与索引.md','11a-索引与平台调研.md']:
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

    # 拆分子文件列表与拼接全文（缺失时记录并降级，避免 FileNotFoundError 直接崩溃）
    _11_subs = ['11a-索引与平台调研.md','11b-职场与垂直行业.md','11c-饭局与家庭.md','11d-生活服务.md','11e-医疗与专业.md','11f-消费维权上.md','11g-消费维权下.md']
    _09_subs = ['09a-职场与面试.md','09b-亲密与家庭.md','09c-社交与线上.md','09d-消费与维权.md','09e-目录与索引.md']
    _missing_subs = [f for f in (_11_subs + _09_subs) if not os.path.exists(os.path.join(REFS, f))]
    chk(not _missing_subs, '拆分子文件齐全（09a-09e / 11a-11g）', f'缺失: {_missing_subs}')
    def _concat_sub(fs):
        return '\n'.join(open(os.path.join(REFS,f), encoding='utf-8').read() for f in fs if os.path.exists(os.path.join(REFS,f)))
    c11_txt = _concat_sub(_11_subs)
    c09_txt = _concat_sub(_09_subs)

    # 11 【v1.36.0 新增】11 库速查表无重复行
    p11 = os.path.join(REFS,'11a-索引与平台调研.md')
    if os.path.exists(p11):
        c11 = open(p11,encoding='utf-8').read()
        m5 = re.search(r'^##\s*五、「症状 → 方法」.*$', c11, re.M)
        m7 = re.search(r'^##\s*七、', c11, re.M)
        if m5:
            seg = c11[m5.start():(m7.start() if m7 else len(c11))]
            # 仅统计数据行：排除表头行（与「症状 / 场景」同形）与分隔行
            rows=[l.strip() for l in seg.split('\n')
                  if l.strip().startswith('|')
                  and not re.match(r'^\|[\s\-:|]+\|$', l.strip())
                  and '症状 / 场景' not in l]
            dup = len(rows) - len(set(rows))
            chk(dup==0, f'11 库速查表无重复行（{len(rows)} 数据行）', f'重复 {dup}')
            # § 引用可达性
            allref = set(re.findall(r'^###\s+(\d+)\.(\d+)', c11_txt, re.M))
            secs = set(re.findall(r'^§\s*(\d+)\.(\d+)', c11_txt, re.M))
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
    real09 = len(re.findall(r'^\|\s*\d+\s*\|', c09_txt, re.M))
    bad09 = []
    hits09 = list(re.finditer(r'09\s*库[^\n]{0,30}?(\d+)\s*条', c11_txt))
    for m in hits09:
        if int(m.group(1)) != real09:
            bad09.append((c11_txt[:m.start()].count('\n')+1, m.group(1)))
    chk(len(hits09) > 0, f'11 库存在「09 库 N 条」声明（实测 {len(hits09)} 处）', '正则零匹配')
    chk(not bad09, f'11 库中「09 库 N 条」口径与实测({real09})一致', str(bad09[:3]))

    # 17b 【v1.39.8 更新】11 库拆分后各子文件字符数上限检查
    _11_max = max(len(open(os.path.join(REFS,f),encoding='utf-8').read()) for f in _11_subs)
    chk(_11_max <= 32000, f'11 库子文件均 ≤3.2万字符（最大 {_11_max/10000:.2f}万）', f'最大 {_11_max} 字符')

    # 17c 【v1.39.8 新增】跨库 §N.M 引用一致性（09库/04库/SKILL → 11库 ### N.M 定义）
    defined_nm = set(re.findall(r'^###\s+(\d+\.\d+)\s', c11_txt, re.M))
    # 也收集 11库内部 §N.M 文本引用作为补充定义集
    text_nm = set(re.findall(r'§(\d+\.\d+)', c11_txt))
    all_defined = defined_nm | text_nm
    dangling = []
    for src_name, src_path in [('09库', None),  # 09库拆分后用 c09_txt
                                 ('04库', os.path.join(REFS,'04-生活社交话术库.md')),
                                 ('SKILL.md', SKILL_MD)]:
        if src_name == '09库':
            src_txt = c09_txt
        else:
            if not os.path.exists(src_path): continue
            src_txt = open(src_path, encoding='utf-8').read()
        refs = set(re.findall(r'11[a-g]?\s*库\s*§(\d+\.\d+)', src_txt))
        for r in refs:
            if r not in all_defined:
                dangling.append(f'{src_name}→11库§{r}')
    chk(not dangling, f'跨库 §N.M 引用全可达（11库定义 {len(all_defined)} 个）', str(dangling[:6]))

    # 17d 【v1.40.2 修订】token 预算检查——改用中文感知估算（原 len//3 低估中文约 1.8x）
    def _tok(t):
        _cjk = len(re.findall(r'[\u4e00-\u9fff]', t))
        return int(_cjk * 0.85 + (len(t) - _cjk) / 3.5)
    _sk_tok = _tok(open(SKILL_MD, encoding='utf-8').read())
    _lib_toks = {f: _tok(open(os.path.join(REFS,f), encoding='utf-8').read()) for f in os.listdir(REFS) if f.endswith('.md')}
    _max_f = max(_lib_toks, key=_lib_toks.get) if _lib_toks else '?'
    _max_lib_tok = _lib_toks.get(_max_f, 0)
    chk(_sk_tok + _max_lib_tok <= 40000, f'token 预算：SKILL+最大单库 ≤40K（SKILL {_sk_tok} + {_max_f[:10]} {_max_lib_tok} = {_sk_tok+_max_lib_tok}）', f'超限 {_sk_tok+_max_lib_tok}')

    # 17e 【v1.40.1 新增】11 库子文件 ⏳ 时效标记分布检查
    _no_marker = [f for f in _11_subs if os.path.exists(os.path.join(REFS,f)) and open(os.path.join(REFS,f), encoding='utf-8').read().count('⏳') < 1]
    chk(not _no_marker, '11 库每个子文件至少 1 个 ⏳ 时效标记', f'缺失: {_no_marker}')

    # 17f 【v1.40.2 新增】SKILL.md 与 README 中一切「NNx-...md」提及必须真实存在（防参考库清单/文件树残留已删除文件）
    _real = set(os.listdir(REFS))
    _ghost = []
    for _doc_name, _doc_path in [('SKILL.md', SKILL_MD), ('README.md', README)]:
        if not os.path.exists(_doc_path): continue
        _dtxt = open(_doc_path, encoding='utf-8').read()
        for _mn in set(re.findall(r'([0-9]{2}[a-g]?-[^\s`|()）]+?\.md)', _dtxt)):
            if _mn not in _real:
                _ghost.append(f'{_doc_name}:{_mn}')
    chk(not _ghost, 'SKILL/README 提及的库文件全部存在', f'幽灵引用: {sorted(_ghost)[:6]}')

    # 17g 【v1.40.2 新增】09e 场景索引条目号可达性（数据驱动生成，防索引腐化误导路由）
    _p9e = os.path.join(REFS, '09e-目录与索引.md')
    if os.path.exists(_p9e):
        _c9e = open(_p9e, encoding='utf-8').read()
        _im = re.search(r'^## 场景索引.*?(?=^## )', _c9e, re.S | re.M)
        if _im:
            _ib = _im.group(0)
            _bad_idx = []
            _parsed = 0
            _cache = {}
            for _line in _ib.split('\n'):
                _cells = [c.strip() for c in _line.strip().strip('|').split('|')] if _line.strip().startswith('|') else []
                if len(_cells) < 3 or 'references/' not in _cells[1]:
                    continue
                _kw, _fcell, _ncell = _cells[0], _cells[1], _cells[2]
                _sub = _fcell.split('references/')[-1].strip()
                _parsed += 1
                if not os.path.exists(os.path.join(REFS, _sub)):
                    _bad_idx.append(f'路径无效:{_fcell}'); continue
                if _sub not in _cache:
                    _st = open(os.path.join(REFS, _sub), encoding='utf-8').read()
                    _cache[_sub] = (_st, dict(re.findall(r'^\|\s*(\d+)\s*\|([^\n]*)', _st, re.M)))
                _st, _erows = _cache[_sub]
                _mapped = [int(x) for x in re.findall(r'#(\d+)', _ncell)]
                if not _mapped:
                    _bad_idx.append(f'无条目号:{_kw}'); continue
                for _n in _mapped:
                    if str(_n) not in _erows:
                        _bad_idx.append(f'{_sub}#{_n}')
                # 语义校验：关键词须真出现在所映射的某条条目文本中（防「编号存在但语义错配」）
                if not any(_kw in _erows.get(str(_n), '') for _n in _mapped):
                    _bad_idx.append(f'语义错配:{_kw}->{_sub}')
            # 空断言防护：解析行数下界，防「解析 0 行却通过」
            chk(_parsed >= 20, f'09e 场景索引可解析（{_parsed} 行）', f'仅解析到 {_parsed} 行——格式或路径异常')
            chk(not _bad_idx, f'09e 场景索引路径/条目号/语义全部可达（校验 {_parsed} 行）', f'失效: {_bad_idx[:6]}')
        else:
            chk(False, '09e 含场景索引块')
    else:
        warns.append('未找到 09e-目录与索引.md，跳过索引完整性检查')

    # 18 【v1.36.4 新增】内容架构优化防回归
    c11_txt2 = open(os.path.join(REFS,'11a-索引与平台调研.md'), encoding='utf-8').read()
    chk('## 场景索引' in c11_txt2, '11 库含场景索引（按用户问法导航）')
    idx_m = re.search(r'^## 场景索引.*?(?=^## )', c11_txt2, re.S | re.M)
    if idx_m:
        idx_rows = len(re.findall(r'^\|(?!\s*什么情况|\s*-)', idx_m.group(0), re.M))
        chk(idx_rows >= 60, f'场景索引条目充足（{idx_rows} 行）')
        secs_idx = set(re.findall(r'§(\d+)', idx_m.group(0)))
        chk(len(secs_idx) >= 54, f'场景索引覆盖节数充足（{len(secs_idx)} 节，阈值 54）')
    else:
        fails.append('11 库场景索引块无法定位')

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

    chk('数据时效说明' in c11_txt, '11 库含平台数据时效说明')
    # 场景索引引用的节号必须真实存在（防索引腐化）
    _CN = '一二三四五六七八九十'
    def _cn2i(x):
        if x == '十': return 10
        if x.startswith('十'): return 10 + _CN.index(x[1]) + 1
        if '十' in x:
            a, b = x.split('十'); return (_CN.index(a)+1)*10 + (_CN.index(b)+1 if b else 0)
        return _CN.index(x)+1 if x in _CN else None
    _secs_real = {_cn2i(m.group(1)) for m in re.finditer(r'^##\s+([一二三四五六七八九十]+)、', c11_txt, re.M)}
    _secs_real.discard(None)
    if idx_m:
        # 用边界断言避免 §59.1 回溯出幻影 §5
        _idx_secs = {int(x) for x in re.findall(r'§(\d+)(?![.\d])', idx_m.group(0))}
        _dead = sorted(_idx_secs - _secs_real)
        chk(not _dead, '场景索引引用的节号全部存在', str(_dead[:5]))
        # 索引使用中的 §N.M 小节须可达
        _subs = {(int(a), int(b)) for a, b in re.findall(r'^#{3,4}\s*(?:§\s*)?(\d+)\.(\d+)', c11_txt, re.M)}
        _isub = {(int(a), int(b)) for a, b in re.findall(r'§(\d+)\.(\d+)', idx_m.group(0))}
        _deadsub = sorted(_isub - _subs)
        chk(not _deadsub, '场景索引 §N.M 引用全部可达', str(_deadsub[:5]))
        # 两套检索入口不得对同一问题指向互斥的节（防冲突复发）
        _B = None
        _m5 = re.search(r'^##\s*五、「症状 → 方法」检索速查表（本库）\s*$', c11_txt2, re.M)
        _m7 = re.search(r'^##\s*七、', c11_txt2, re.M)
        if _m5:
            _Btxt = c11_txt2[_m5.start():(_m7.start() if _m7 else len(c11_txt2))]
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
    chk(c11_txt.count('⏳') >= 10, f'11 库时效标记充足（{c11_txt.count("⏳")} 处）')

    _sk = open(SKILL_MD, encoding='utf-8').read()
    _fm = _sk.split('---')[1]
    _allowed = {'name', 'description', 'version'}
    _present = set(re.findall(r'^([A-Za-z_][A-Za-z0-9_]*)\s*:', _fm, re.M))
    _extra = _present - _allowed
    chk(not _extra, 'frontmatter 无无效字段（运行时仅读 name/description）', str(sorted(_extra)))

    # 19 【v1.37.5 新增】索引回归测试（用例来自独立对抗验证，含作者盲区）
    _reg = os.path.join(ROOT, 'tests', 'index_regression.py')
    if os.path.exists(_reg):
        import subprocess as _sp
        _r = _sp.run([sys.executable, '-X', 'utf8', _reg], capture_output=True, text=True, encoding='utf-8', errors='replace')
        _m = re.search(r'命中 (\d+)/(\d+)', _r.stdout or '')
        if _m:
            _h, _t = int(_m.group(1)), int(_m.group(2))
            chk(_h == _t, f'索引回归测试全部命中（{_h}/{_t}）',
                '缺口见 tests/index_regression.json')
        else:
            chk(False, '索引回归测试可运行', '无统计输出')
    else:
        warns.append('未找到 tests/index_regression.py，跳过索引回归')

    # 20 【v1.37.6 新增】边界与鲁棒性回归（铁律/超范围/触发词冲突）
    _edge = os.path.join(ROOT, 'tests', 'edge_regression.py')
    if os.path.exists(_edge):
        import subprocess as _sp2
        _r2 = _sp2.run([sys.executable, '-X', 'utf8', _edge], capture_output=True, text=True, encoding='utf-8', errors='replace')
        _m2 = re.search(r'通过 (\d+)/(\d+)', _r2.stdout or '')
        if _m2:
            _h2, _t2 = int(_m2.group(1)), int(_m2.group(2))
            chk(_h2 == _t2, f'边界回归测试全部通过（{_h2}/{_t2}）',
                '缺口见 tests/edge_regression.json')
        else:
            chk(False, '边界回归测试可运行', '无统计输出')
    else:
        warns.append('未找到 tests/edge_regression.py，跳过边界回归')

    # 21 【v1.37.6 新增】09 场景层区间不得跨话题重叠（防「家长群读到装修」类错配）
    _c09b = c09_txt  # 使用拆分后拼接全文
    _toc9 = re.search(r'^## 目录.*?(?=^## )', _c09b, re.S | re.M)
    if _toc9:
        _lay = re.search(r'### 🎯 场景层.*?(?=### 📚 批次层)', _toc9.group(0), re.S)
        if _lay:
            from collections import defaultdict as _dd
            _rev = _dd(set)
            _cur = None
            for _l in _lay.group(0).split('\n'):
                _m = re.match(r'^\*\*(.+?)\*\*$', _l.strip())
                if _m: _cur = _m.group(1); continue
                if not _l.strip().startswith('|') or _l.count('|') < 3: continue
                _p = [x.strip() for x in _l.strip().strip('|').split('|')]
                if len(_p) < 2 or _p[0] in ('什么情况',) or set(_p[0]) <= set('-'): continue
                for _a, _b in re.findall(r'#(\d+)(?:-(\d+))?', _p[1]):
                    _a2 = int(_a); _b2 = int(_b) if _b else _a2
                    for _k in range(_a2, _b2+1): _rev[_k].add(_cur)
            _overlap = {k: v for k, v in _rev.items() if len(v) >= 2}
            # 同一区间被两个「消费/生活」类话题认领属错配；职场跨部门等合理重叠不报
            chk(len(_overlap) <= 40,
                f'09 场景层区间重叠可控（{len(_overlap)} 个，阈值 40）',
                f'过高说明区间接管过宽，样例 {sorted(_overlap)[:6]}')

            # 21b 【v1.39.3 修复·补盲区】已知错配的精确断言（宽松阈值抓不住复发）
            # 破坏测试 (h) 证实：家长群 #198-200 → #191-200 只加 3 个重叠（23→26），
            # 宽松阈值 ≤40 完全漏掉。此处对 v1.38.0 修过的错配做精确锚定：
            _must_rows = {
                '装修增项、材料调包、验收扯皮': '#191-194',
                '闲鱼收货不符、退货扯皮、差评威胁': '#195-197',
                '家长群、老师点名、作业量与育儿沟通': '#198-200',
                '陪诊陪护、认知症老人就医、陪诊员资质': '#275-277',
                '养老分工推诿、老人不愿被照顾': '#228-230',
                '求职陷阱吸费、试岗白干、简历夸大': '#271-274',
                '被要求写辞职、只给 N、离职后被找麻烦': '#278-280',
            }
            _lay_all = _lay.group(0)
            _bad_map = []
            for _topic, _range in _must_rows.items():
                _found = [l for l in _lay_all.split('\n') if _topic in l]
                if not _found:
                    _bad_map.append(f'「{_topic[:18]}」行缺失')
                elif _range not in _found[0]:
                    _bad_map.append(f'「{_topic[:18]}」应为 {_range}，实为 {_found[0].split("|")[2].strip() if _found[0].count("|")>=3 else "?"}')
            chk(not _bad_map,
                f'09 场景层已知错配精确锚定（{len(_must_rows)} 条映射逐一核对）',
                f'错配复发: {_bad_map[:3]}')

    # 22 【v1.37.6 新增】内容质量回归（法律准确性/红线一致性/过期声明）
    _ct = os.path.join(ROOT, 'tests', 'content_regression.py')
    if os.path.exists(_ct):
        import subprocess as _sp3
        _r3 = _sp3.run([sys.executable, '-X', 'utf8', _ct], capture_output=True, text=True, encoding='utf-8', errors='replace')
        _m3 = re.search(r'失败项：(\d+)', _r3.stdout or '')
        if _m3:
            _f3 = int(_m3.group(1))
            chk(_f3 == 0, f'内容质量回归全部通过（{_f3} 项失败）',
                '问题见 tests/content_regression.json')
        else:
            chk(False, '内容质量回归可运行', '无统计输出')
    else:
        warns.append('未找到 tests/content_regression.py，跳过内容回归')

    # 22b 【v1.39.8 新增】端到端行为测试（路由可达性 + 输出格式 + 自检机制）
    _e2e = os.path.join(ROOT, 'tests', 'e2e_regression.py')
    if os.path.exists(_e2e):
        try:
            _r = subprocess.run([sys.executable, '-X', 'utf8', _e2e], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
            if _r.returncode == 0:
                chk(True, '端到端行为测试全通过')
            else:
                _e2e_fails = [l for l in _r.stdout.split('\n') if '❌' in l]
                chk(False, '端到端行为测试全通过', f'{len(_e2e_fails)} 项失败: {_e2e_fails[:3]}')
        except Exception as _e:
            chk(False, '端到端行为测试可运行', str(_e))
    else:
        warns.append('未找到 tests/e2e_regression.py，跳过端到端测试')

    # 23 【v1.37.6 新增·修 D 线指出的空断言】关键断言须有实际匹配量
    # D 线指出：verify 输出自身暴露 2 项「正则零匹配」的空断言 —— 此处显式校验
    _empty_guard = [
        ('README→SKILL 引用', len(re.findall(r'（见\s*SKILL\.md[「"“]([^」"”]+)[」"”]）', open(README, encoding='utf-8').read()))),
        ('09库口径声明', len(re.findall(r'09\s*库[^\n]{0,30}?(\d+)\s*条', c11_txt))),
        ('场景索引条目', len(re.findall(r'^\|(?!\s*你会怎么说|\s*-)', idx_m.group(0), re.M)) if idx_m else 0),
        ('09场景层条目', len(re.findall(r'^\|\s*[^|]+\s*\|\s*#', _toc9.group(0), re.M)) if _toc9 else 0),
    ]
    for _n, _c in _empty_guard:
        chk(_c > 0, f'断言有效性：{_n} 有实际匹配（{_c}）', '零匹配=空断言')

    # 24 【v1.39.0 新增·补 D 线盲区】README 内所有版本声明必须一致
    #    D 线发现：release.py 的「过期当前 vX」断言只查 voice-call-guide，README 不在范围，
    #    导致 README 标题已是新版本、版本历史行却停在旧版本而校验全绿。
    #    此处做「类级」检查：抓出 README 中所有 vX.Y.Z 形态的版本声明，必须全部相等。
    _rd = open(README, encoding='utf-8').read()
    _decls = set(re.findall(r'当前版本 \*\*(v[\d.]+)\*\*', _rd)) | set(re.findall(r'高情商聊天技能（gaoqing-shang-liaotian）(v[\d.]+)', _rd))
    _sv = re.search(r'^version:\s*"([^"]+)"', open(SKILL_MD, encoding='utf-8').read(), re.M)
    _svv = 'v' + _sv.group(1) if _sv else None
    _has_hist = bool(re.search(r'（当前版本 \*\*v[\d.]+\*\*）', _rd))
    chk(_has_hist,
        'README 含「（当前版本 **vX**）」声明行',
        '声明行缺失（被删且未补回）——bump 的 ⚠️ 警告由此兑现')
    chk(_decls and _decls == {_svv},
        f'README 版本声明一致（{sorted(_decls)} vs SKILL {_svv}）',
        'README 内有版本声明与 SKILL 不符（bump 未同步）')

    # 26 【v1.39.4 新增·T3 发现】禁止「抓取时间冒充数据时间」
    _c15v = open(os.path.join(REFS, '15-资源地图与源可信度评级.md'), encoding='utf-8').read()
    # 【v1.39.4 修正】只查标题行——正文更正说明里合法引用旧错误标题不算违规
    _c15_hdr = next((l for l in _c15v.split('\n') if l.startswith('## 八、')), '')
    chk('2021 年快照' in _c15_hdr and '2026-10 抓取' in _c15_hdr and '2026-10 微信读书数据' not in _c15_hdr,
        '15库 §八标题 = 数据年代（2021 快照）与抓取时间（2026-10）分离',
        f'标题仍在伪装数据年代: {_c15_hdr[:60]}')
    chk('2021 年的快照' in _c15v and '2021-07-18' in _c15v,
        '15库 已标注数据真实年代（2021 快照 + 仓库最后更新日）',
        '缺 2021 年代标注')
    # 27 【v1.39.4 新增·T3 发现】安全升级条款必须存在且被 16库 引用
    _skv = open(SKILL_MD, encoding='utf-8').read()
    chk('安全升级条款' in _skv and '12356' in _skv,
        'SKILL 含自伤/危机「安全升级条款」（热线与转介指引）',
        '缺安全升级条款——16库 §2.1b 的自伤指针会悬空')
    _p16 = os.path.join(REFS, '16-分寸感与边界感.md')
    chk(os.path.exists(_p16) and '安全升级条款' in open(_p16, encoding='utf-8').read(),
        '16库 自伤指引已接到 SKILL 安全升级条款',
        '16库 缺失或自伤指引悬空')
    # 28 【v1.39.4 新增·T2 发现】模板占位规则
    chk('占位替换规则' in _skv and '照抄即撒谎' in _skv,
        'SKILL Step3 含模板占位替换规则（防照抄即撒谎）',
        '缺占位替换规则')
    _p05 = os.path.join(REFS, '05-自我检查清单.md')
    chk(os.path.exists(_p05) and '占位检查' in open(_p05, encoding='utf-8').read(),
        '05库 自检第4遍含占位检查',
        '05库 缺失或缺占位检查')

    # 25 【v1.39.5·A线P1-1 重构】README 声明的校验项数 == 真实总数
    #     原缺陷：_actual 中途计算（len(oks)+1），漏算自身与 #26-28 共 7 项，
    #     且容差 ±3 —— README 写过期值 PASS、写真实值 FAIL（逻辑反转）。
    #     修法：移到全部 chk 之后，真实总数零容差比对。
    _rd_final = open(README, encoding='utf-8').read()
    _m_cnt = re.search(r'清单校验（(\d+) 项）', _rd_final)
    _total = len(oks) + len(warns) + len(fails)
    if _m_cnt:
        _declared = int(_m_cnt.group(1))
        chk(_declared == _total,
            f'README 校验项数与实际一致（声明 {_declared} / 实际 {_total}）',
            f'声明 {_declared} ≠ 实际 {_total}——请把 README 的「清单校验（N 项）」改为 {_total}')
    else:
        chk(False, 'README 含「清单校验（N 项）」声明', '未找到声明行')

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
