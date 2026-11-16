#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段 A：接口 × 漏洞类型 资格矩阵生成器

输入：Java/Spring/MyBatis 源码目录
输出：
  1. cells.json   全矩阵（applicable + not_applicable，后者带不可达证明）
  2. tasks.json   只含 applicable 的格子，按优先级排序，可直接派活
  3. 控制台       汇总 + Top 任务

判定模型：
  eligibility = 请求参数能否到达该漏洞类型的 Sink（参数级可达）
  priority    = base × exposure + taint×2 + guard

明确的能力边界：本原型用「正则 + 方法名调用图」，召回不完整；
           生产版本应换成 Joern CPG 的 reachableBy。
"""
import os, re, sys, json
from collections import defaultdict, deque

ROOT = sys.argv[1] if len(sys.argv) > 1 else '.'
PREFIX = sys.argv[2] if len(sys.argv)>2 else '/tmp/opencode'
DISPATCH_LOW = '--low' in sys.argv   # 默认不派发低置信格子（仍保留在矩阵里可见）
ASSET_MAP = {}
IDX_ARITY = {}    # 方法名 → 参数个数 → 定义列表（用于同名方法消歧）
# MyBatis-Plus / Spring Data 等框架方法：本类/父类找不到时视为外部调用，
# 不再当成"工程内同名方法"从而制造 ambiguous。
FRAMEWORK_METHODS = {
    'getOne','getById','getByIds','getObj','getMap','list','listByIds','listByMap',
    'page','count','save','saveBatch','saveOrUpdate','saveOrUpdateBatch',
    'update','updateById','updateBatchById','remove','removeById','removeByIds',
    'removeByMap','lambdaQuery','lambdaUpdate','query','getBaseMapper',
    'findById','findAll','findOne','existsById','deleteById','deleteAll','saveAll',
    'toString','equals','hashCode','build','builder','of','valueOf',
    # 静态导入/工具类常见方法：本类找不到时按外部处理
    'getRequest','getResponse','getSession','getRequestAttributes',
    'renderString','renderResultString','isNotEmpty','isNotBlank','hasText','hasLength',
    # 集合 / lambda 参数上的常见方法（接收者类型推不出时按外部处理）
    'get','put','remove','add','addAll','containsKey','containsValue','size','keySet','values',
    'entrySet','iterator','stream','forEach','collect','compareTo',
}
RAW_BODIES = {}   # (file, bline) → 未屏蔽字符串的方法体（守卫检测需要看到 ".." 这类字面量）
if os.path.exists('/tmp/opencode/asset_map.json'):
    try: ASSET_MAP = json.load(open('/tmp/opencode/asset_map.json'))
    except Exception: pass

# ══════════════════════════════════════════════════════════ 词法
def strip_comments(src):
    out=[]; i=0; n=len(src); st=None
    while i<n:
        c=src[i]; nx=src[i+1] if i+1<n else ''
        if st is None:
            if c=='/' and nx=='/': st='line'; out.append('  '); i+=2; continue
            if c=='/' and nx=='*': st='block'; out.append('  '); i+=2; continue
            if c=='"': st='str'; out.append('"'); i+=1; continue
            if c=="'": st='chr'; out.append("'"); i+=1; continue
            out.append(c); i+=1; continue
        if st=='line':
            if c=='\n': st=None; out.append('\n')
            else: out.append(' ')
            i+=1; continue
        if st=='block':
            if c=='*' and nx=='/': st=None; out.append('  '); i+=2; continue
            out.append('\n' if c=='\n' else ' '); i+=1; continue
        q='"' if st=='str' else "'"
        if c=='\\':
            out.append(c); i+=1
            if i<n:
                out.append(src[i]); i+=1
            continue
        if c==q: st=None; out.append(q); i+=1; continue
        out.append(c); i+=1
    return ''.join(out)

def mask_strings(src):
    out=list(src); i=0; n=len(src)
    while i<n:
        if src[i] in ('"',"'"):
            q=src[i]; i+=1
            while i<n and src[i]!=q:
                if src[i]=='\\':
                    out[i]=' '; i+=1
                    if i<n: out[i]=' '; i+=1
                    continue
                if src[i]!='\n': out[i]=' '
                i+=1
            if i<n: i+=1
        else: i+=1
    return ''.join(out)

def match_brace(t, o):
    d=0
    for i in range(o,len(t)):
        if t[i]=='{': d+=1
        elif t[i]=='}':
            d-=1
            if d==0: return i
    return -1

def line_of(t, i): return t.count('\n',0,i)+1

# ══════════════════════════════════════════════════════════ 配置
VULN_CN = {
 'file-upload':'文件上传','path-traversal':'路径穿越','sql-injection':'SQL 注入',
 'command-exec':'命令/表达式注入','ssrf':'SSRF','deserialization':'不安全反序列化',
 'xss':'XSS','authz':'越权',
}
SINK_PAT = {
 'file-upload': r'\.transferTo\s*\(|Files\.(write|copy|move)|FileOutputStream|FileUtils\.copyInputStreamToFile',
 'path-traversal': r'new\s+File\s*\(|Paths\.get\s*\(|\.resolve\s*\(|FileInputStream\s*\(|FileReader\s*\(|Files\.(read|list|walk|newInputStream)|\.getRealPath\s*\(|RandomAccessFile\s*\(',
 'sql-injection': r'\.executeQuery\s*\(|\.executeUpdate\s*\(|createStatement\s*\(|prepareStatement\s*\(|jdbcTemplate\.|\.last\s*\(|\.apply\s*\(|\.orderBy(Desc|Asc)?\s*\(',
 'command-exec': r'Runtime\.getRuntime|new\s+ProcessBuilder|\.exec\s*\(|ScriptEngine|\.eval\s*\(|GroovyShell|SpelExpressionParser|parseExpression\s*\(|QLExpress|ExpressRunner|VelocityEngine|\.evaluate\s*\(|new\s+Yaml\s*\(',
 'ssrf': r'new\s+URL\s*\(|\.openConnection\s*\(|HttpRequest\.(post|get)\s*\(|HttpUtil\.(createPost|createGet|post|get)\s*\(|\.(getForObject|postForObject|getForEntity|postForEntity|exchange)\s*\(|ImageIO\.read\s*\(',
 'deserialization': r'ObjectInputStream|\.readObject\s*\(|XMLDecoder|new\s+XStream|\.fromXML\s*\(|SupportAutoType|new\s+Yaml\s*\(',
 'xss': r'getWriter\s*\(\s*\)|\.addHeader\s*\(|sendRedirect\s*\(|ModelAndView|PrintWriter',
}
VULN_BASE = {'command-exec':9,'deserialization':9,'file-upload':8,'sql-injection':7,
             'path-traversal':7,'ssrf':6,'authz':6,'xss':3}
GUARD_PAT = {
 'file-upload': [(r'(?i)\.(jpg|jpeg|png|gif|bmp)\b','扩展名白名单'),
                 (r'FilenameUtils\.getName','文件名净化'),
                 (r'UUID\.randomUUID','UUID 重命名'),
                 (r'cleanPath\s*\(','cleanPath 净化'),
                 (r'contains\s*\(\s*"\.\."','.. 过滤'),
                 (r'checkPicSuffix|allowedExt|ALLOWED_EXT|suffixList|white_suffix|picSuffixList','后缀白名单'),
                 (r'maxFileSize|setMaxFileSize|MultipartConfig','大小限制')],
 'path-traversal': [(r'FilenameUtils\.getName','文件名净化'),
                    (r'getCanonicalPath|\.toRealPath\s*\(','路径规范化校验'),
                    (r'\.startsWith\s*\(','路径 startsWith 校验'),
                    (r'cleanPath\s*\(','cleanPath 净化'),
                    (r'contains\s*\(\s*"\.\."','.. 过滤'),
                    (r'Whitelist|whitelist|allowedPath|SAFE_PATH|pathFilter|checkPath','路径白名单/过滤')],
 'sql-injection': [(r'#\{','MyBatis 预编译'),
                   (r'sqlFilter|SqlFilter|FILTER_PATTERN','SQL 白名单过滤'),
                   (r'(?i)\w*(normalize|whitelist|allowed)\w*\s*\(','排序/字段白名单'),
                   (r'setString\s*\(|setLong\s*\(','PreparedStatement 占位符')],
 'command-exec': [(r'Pattern\.compile|\.matches\s*\(|cmdFilter|checkCmd','正则/命令白名单'),
                  (r'SimpleEvaluationContext','SpEL 只读上下文'),
                  (r'Whitelist|whitelist|ALLOWED_CMD','命令白名单')],
 'ssrf': [(r'Whitelist|whitelist|allowedHost|SafeDomain|safeDomain|checkSSRF|checkSSRFByWhitehosts|SSRFHook|checkURL|safeUrl|isHttp','域名/IP 白名单或 SSRF 钩子'),
          (r'startsWith\s*\(\s*"https?','协议校验')],
 'deserialization': [(r'SafeMode|setEnabledDefaultTyping|allowlist|Whitelist|AntObjectInputStream|blacklist|blackList|ClassFilter','反序列化白名单/黑名单')],
 'xss': [(r'HtmUtils|htmlEscape|escapeHtml|Encode\.forHtml|StringEscapeUtils\.escapeHtml','输出转义')],
}
CHECKLIST = {
 'file-upload': ['扩展名 / Content-Type 白名单', '文件名净化（../、绝对路径、空字节）', '存储目录是否可执行', '大小限制', '是否可覆盖已有文件'],
 'path-traversal': ['是否拼接了用户可控路径/文件名', '有无 ../ 过滤或规范化校验（getCanonicalPath）', '是否限制在固定根目录下'],
 'sql-injection': ['是否使用 #{} 占位符或 ? 参数化', '${} 或字符串拼接的位置', 'order by / like / in 等特殊位置的过滤'],
 'command-exec': ['参数是否进入执行/求值 API', '有无白名单或类型约束', '是否可通过表达式/编码绕过'],
 'ssrf': ['URL 是否完全可控', '有无协议 / 域名 / IP 白名单', '是否允许内网地址与重定向'],
 'deserialization': ['是否对不可信数据做原生反序列化', '有无类白名单 / SafeMode', '依赖是否存在可利用 gadget'],
 'xss': ['输出是否转义', '是否写入可渲染位置', '前端渲染方式'],
 'authz': ['是否有 principal 介入数据访问', '归属谓词写在哪（SQL / Java / 注解）', '是否把判定委托给外部服务'],
}

def match_paren(t,o):
    d=0
    for i in range(o,len(t)):
        if t[i]=='(': d+=1
        elif t[i]==')':
            d-=1
            if d==0: return i
    return -1

def find_methods(c):
    """返回 [{name,start,ps,pe,bo,bc}]；正确处理参数列表里注解的圆括号。"""
    out=[]
    for m in re.finditer(r'^\s*(?:public|protected|private)\s+(?:static\s+)?(?:final\s+)?',c,re.M):
        i=m.end()
        j=c.find('(',i)
        if j<0 or j-i>400: continue
        head=c[i:j]
        if ';' in head or '=' in head: continue
        nm=re.search(r'(\w+)\s*$',head)
        if not nm: continue
        close=match_paren(c,j)
        if close<0: continue
        k=close+1
        while k<len(c) and c[k] in ' \t\r\n': k+=1
        if c.startswith('throws',k):
            b=c.find('{',k)
            if b<0: continue
            k=b
        if k>=len(c) or c[k]!='{': continue
        bc=match_brace(c,k)
        if bc<0: continue
        out.append({'name':nm.group(1),'start':m.start(),'ps':j+1,'pe':close,'bo':k+1,'bc':bc})
    return out

# ══════════════════════════════════════════════════════════ 解析
def parse_project(root):
    RAW_BODIES.clear()
    files=[]
    for dp,_,fns in os.walk(root):
        if '/target/' in dp or '/.git' in dp: continue
        for fn in fns:
            if fn.endswith('.java'): files.append(os.path.join(dp,fn))
    files.sort() # 固定遍历顺序，保证跨机器/跨次运行结果一致
    clean={};masked={};raws={}
    for f in files:
        try:
            raw=open(f,encoding='utf-8',errors='replace').read()
            raws[f]=raw
            clean[f]=strip_comments(raw); masked[f]=mask_strings(clean[f])
        except Exception: pass

    xml_map={}
    for dp,_,fns in os.walk(root):
        for fn in fns:
            if not fn.endswith('.xml'): continue
            p=os.path.join(dp,fn)
            try: x=open(p,encoding='utf-8',errors='replace').read()
            except Exception: continue
            for m in re.finditer(r'<(select|insert|update|delete)\s+id="([^"]+)"[^>]*>(.*?)</\1>',x,re.S):
                xml_map[m.group(2)]=(m.group(3),p,line_of(x,m.start()))

    ann_map={}
    for f,c in clean.items():
        for m in re.finditer(r'@(Select|Update|Insert|Delete)\s*\(\s*(.+?)\)\s*(?:@\w+\s*)*[\w<>\[\],\s]+\s+(\w+)\s*\(',c,re.S):
            ann_map.setdefault(m.group(3),[]).append((m.group(2),f,line_of(c,m.start())))

    # 类索引：类 → 方法 / 字段 / 父类 / 实现
    # 目的：把 `xxxService.foo()` 从"按方法名猜"改成"按接收者静态类型解析"，
    #       把同名歧义挡在门外（这是 v1.2 的主要精度来源，不需要 Joern）。
    CLASS_RE = re.compile(r'\b(?:class|interface|enum)\s+(\w+)([^{;]*)\{')
    FIELD_RE = re.compile(r'^\s*(?:@[\w.]+(?:\s*\([^)]*\))?\s*)*'
                          r'(?:private|protected|public)\s+(?:static\s+)?(?:final\s+)?'
                          r'([A-Z][\w.]*(?:\s*<[^;{}()]*>)?(?:\[\])?)\s+(\w+)\s*(?:=|;)', re.M)
    proj={'methods':defaultdict(lambda: defaultdict(list)),'fields':defaultdict(dict),
          'parents':{},'impls':defaultdict(list),'classes':set()}
    idx=defaultdict(list)
    for f,c in masked.items():
        classes=[]
        for m in CLASS_RE.finditer(c):
            head=m.group(2)
            b=c.find('{',m.start())
            if b<0: continue
            bc=match_brace(c,b)
            if bc<0: continue
            extm=re.search(r'\bextends\s+([\w.]+)', head)
            implm=re.search(r'\bimplements\s+([\w.,\s]+?)\s*$', head)
            classes.append((m.group(1),
                            (extm.group(1).split('.')[-1] if extm else ''),
                            (implm.group(1) if implm else ''), b, bc))
        for nm,ext,impls,b,bc in classes:
            proj['classes'].add(nm)
            if ext: proj['parents'][nm]=ext
            for i in (impls or '').split(','):
                i=i.strip().split('.')[-1]
                if i: proj['impls'][i].append(nm)
            for fm in FIELD_RE.finditer(c,b+1,bc):
                ty=fm.group(1).split('<')[0].split('.')[-1]
                proj['fields'][nm].setdefault(fm.group(2), ty)
        # 方法归属到最内层类
        for md in find_methods(c):
            cls=''
            for nm,ext,impls,b,bc in classes:
                if b<md['start']<bc: cls=nm
            params=parse_params(clean[f][md['ps']:md['pe']])
            RAW_BODIES[(f, line_of(c,md['bo']))] = clean[f][md['bo']:md['bc']]
            d={'file':f,'body':c[md['bo']:md['bc']],'line':line_of(c,md['start']),
               'bline':line_of(c,md['bo']),'params':params,
               'raw_params':clean[f][md['ps']:md['pe']],'cls':cls}
            idx[md['name']].append(d)
            if cls: proj['methods'][cls][md['name']].append(d)
    for k in idx:
        idx[k].sort(key=lambda d: (d['file'], d.get('bline', d['line'])))
    IDX_ARITY.clear()
    for k, defs in idx.items():
        by = defaultdict(list)
        for d in defs:
            by[len(d['params'])].append(d)
        IDX_ARITY[k] = dict(by)
    # 类方法列表也排序，保证确定性
    for cls in proj['methods']:
        for nm in proj['methods'][cls]:
            proj['methods'][cls][nm].sort(key=lambda d: (d['file'], d.get('bline', d['line'])))
    return clean,masked,raws,xml_map,ann_map,idx,proj

ANNO_PARAM=re.compile(r'@\w+(?:\s*\([^)]*\))?\s*')
def parse_params(sig):
    """返回 [{name,type,anno,location}]"""
    out=[]
    if not sig.strip(): return out
    depth=0; buf=''; parts=[]
    for ch in sig:
        if ch=='<': depth+=1
        elif ch=='>': depth-=1
        if ch==',' and depth==0: parts.append(buf); buf=''
        else: buf+=ch
    if buf.strip(): parts.append(buf)
    for p in parts:
        p=p.strip()
        loc='query'
        if 'MultipartFile' in p or 'MultipartHttpServletRequest' in p: loc='multipart'
        if '@RequestBody' in p: loc='body'
        if '@PathVariable' in p: loc='path'
        if '@RequestHeader' in p: loc='header'
        if 'RedirectAttributes' in p: continue
        if 'HttpServletRequest' in p: loc='request'
        if 'HttpServletResponse' in p: loc='response'
        noanno=ANNO_PARAM.sub('',p).strip()
        toks=noanno.split()
        if len(toks)<2: continue
        typ=toks[-2]; name=toks[-1].replace('[]','')
        out.append({'name':name,'type':typ,'location':loc})
    return out

def collect_calls(body):
    """返回 [(callee, args_text, offset)]"""
    out=[]
    for m in re.finditer(r'(\w+)\s*\(',body):
        nm=m.group(1)
        if nm in ('if','for','while','switch','catch','return','new','synchronized','super','this'): continue
        if re.search(r'\bnew\s*$', body[:m.start()]): continue   # 构造器：new Foo(...)
        o=body.find('(',m.end()-1); 
        if o<0: continue
        d=0; close=len(body)
        for i in range(o,len(body)):
            if body[i]=='(': d+=1
            elif body[i]==')':
                d-=1
                if d==0: close=i; break
        out.append((nm,body[o+1:close],m.start()))
    return out

OWNER_RE=re.compile(r'(?i)(?:checkOwner|checkOwnership|checkPermission|assertOwner|verifyOwner)\s*\(|Objects\.equals\s*\([^;]{0,120}get(?:PatientId|UserId|OwnerId)[^;]{0,120}(?:user|principal|loginUser)\.|(?:user|principal|loginUser)\.\w+\s*\.equals\s*\([^;]{0,120}get(?:PatientId|UserId|OwnerId)|(?:Mapper|Repository|Dao)\.\w+\s*\(\s*(?:user|principal|loginUser)\.getId\s*\(\s*\)')
DETRUST=re.compile(r'(?i)(Mapper\.|Repository\.|settingService|SettingService|redisService|RedisService|\.select(One|List|ById)?\s*\(|\.getById\s*\(|\.getOne\s*\(|getHospSetting|getConfig|Properties)')
STR_TYPES={'String','CharSequence','URI','URL','StringBuilder','StringBuffer'}
def string_params(params):
    return tuple(p['name'] for p in params if p['type'].split('<')[0] in STR_TYPES)
def taint_names(body, seeds, declassify=False):
    names=set(seeds)
    changed=True
    while changed:
        changed=False
        for m in re.finditer(r'(?:[\w<>\[\],\.\?]+)\s+(\w+)\s*=\s*([^;]+);',body):
            if m.group(1) in names: continue
            rhs=m.group(2)
            if DETRUST.search(rhs): continue
            if declassify and re.search(r'(?i)\w+(Service|Mapper|Dao|Repository|Client|Utils?)\s*\.\s*\w+\s*\(', rhs): continue
            if any(re.search(r'\b'+re.escape(v)+r'\b',rhs) for v in names):
                names.add(m.group(1)); changed=True
        for m in re.finditer(r'(\w+)\s*\.\s*(?:set|add|put|append|build)\w*\s*\(([^;]*)\)\s*;',body):
            if m.group(1) in names: continue
            rhs=m.group(2)
            if DETRUST.search(rhs): continue
            if declassify and re.search(r'(?i)\w+(Service|Mapper|Dao|Repository|Client|Utils?)\s*\.\s*\w+\s*\(', rhs): continue
            if any(re.search(r'\b'+re.escape(v)+r'\b',rhs) for v in names):
                names.add(m.group(1)); changed=True
    return names

# ══════════════════════════════════════════════════════════ 接口枚举
MAP=re.compile(r'@(Get|Post|Put|Delete|Patch|Request)Mapping\s*\(([^)]*)\)',re.S)
def endpoints(clean,masked,idx,raws=None):
    eps=[]
    for f,c in masked.items():
        if '@RestController' not in c and '@Controller' not in c: continue
        cls=re.search(r'@RequestMapping\s*\(([^)]*)\)\s*(?:@[^;{]*?\s*)*(?:public\s+)?class\s+(\w+)',c,re.S)
        base=''
        if cls:
            pm=re.search(r'"([^"]*)"',clean[f][cls.start(1):cls.end(1)])
            base=pm.group(1) if pm else ''
        meths=find_methods(c)
        for m in MAP.finditer(c):
            if m.group(1)=='Request' and cls and m.start()<cls.end(): continue
            nxt=None; prev=None
            for _i,md in enumerate(meths):
                if md['start']>m.end() and md['start']-m.end()<600:
                    nxt=md; prev=meths[_i-1] if _i>0 else None; break
            if not nxt: continue
            pm=re.search(r'"([^"]*)"',clean[f][m.start(2):m.end(2)])
            path=pm.group(1) if pm else ''
            eps.append({'file':f,'http':'ANY' if m.group(1)=='Request' else m.group(1).upper(),
                        'url':(base.rstrip('/')+'/'+path.lstrip('/')).replace('//','/'),
                        'handler':nxt['name'],'body':c[nxt['bo']:nxt['bc']],
                        'params':nxt['params'] if 'params' in nxt else parse_params(clean[f][nxt['ps']:nxt['pe']]),
                        'line':line_of(c,m.start()),
                        'bline':line_of(c,nxt['bo']),
                        'comments':collect_doc(raws.get(f,'') if raws else '', line_of(c,prev['bc'])+1 if prev else 1, line_of(c,nxt['bc']))})
    return eps

# ══════════════════════════════════════════════════════════ 权限
def load_permission(root):
    pub=[]
    for dp,_,fns in os.walk(root):
        for fn in fns:
            if not (fn.endswith('.properties') or fn.endswith('.yml') or fn.endswith('.yaml')): continue
            try: c=open(os.path.join(dp,fn),encoding='utf-8',errors='replace').read()
            except Exception: continue
            for m in re.finditer(r'(?i)no\.?need\.?login\.?url\s*[=:]\s*([^\n]+)',c):
                pub += [x.strip() for x in m.group(1).split(',') if x.strip()]
            for m in re.finditer(r'(?im)^\s*whitelist\s*:\s*\n((?:[ \t]*-\s*[^\n]+\n?)+)',c):
                pub += [u.strip() for u in re.findall(r'-\s*([^\s#]+)', m.group(1))]
    for f,c in clean_java(root):
        if not f.endswith('WebSecurityConfig.java'): continue
        for mm in re.finditer(r'antMatchers\(([^)]*)\)\s*\.permitAll',c):
            for u in re.findall(r'"([^"]+)"',mm.group(1)): pub.append(u)
        for mm in re.finditer(r'\.(?:loginPage|logoutUrl)\(\s*"([^"]+)"',c): pub.append(mm.group(1))
    return pub

def clean_java(root):
    for dp,_,fns in os.walk(root):
        for fn in fns:
            if fn.endswith('.java'):
                p=os.path.join(dp,fn)
                try: yield p,strip_comments(open(p,encoding='utf-8',errors='replace').read())
                except Exception: pass

def load_auth_policy(clean):
    """解析全局拦截器：哪些前缀要求 ADMIN、以及角色校验是否真的存在。

    v1 的 AuthInterceptor 有 "ADMIN".equals(user.getRole())；
    v2 删掉后只剩 needAdmin 方法（没有调用点）→ has_role=False，不能算有校验。
    """
    has_role=False; admin=[]
    for f,c in clean.items():
        if re.search(r'"ADMIN"\s*\.\s*equals|hasRole\s*\(\s*"ADMIN"|hasAuthority\s*\(\s*"ADMIN"', c):
            has_role=True
        if 'pathMatcher.match' in c:
            admin += re.findall(r'pathMatcher\.match\s*\(\s*"([^"]+)"', c)
    return {'has_role':has_role,'admin':sorted(set(admin)) if has_role else []}

def permission_of(url,pub,admin=None):
    for p in (admin or []):
        if p.endswith('/**'):
            if url.startswith(p[:-3]): return '管理员'
        elif p.rstrip('/')==url.rstrip('/'): return '管理员'
    for p in pub:
        if p.endswith('/**'):
            if url.startswith(p[:-3]): return '公开'
        elif p.rstrip('/')==url.rstrip('/'): return '公开'
    return '登录用户'

# ══════════════════════════════════════════════════════════ 资格 + 优先级

def type_plausible(vuln, ep):
    """该接口是否存在该类漏洞的 source 前提（按**类型**判定，名字只作补充）。"""
    ps = ep.get('params') or []
    if not ps:
        return False
    locs = {p.get('location') for p in ps}
    types = {p.get('type','').split('<')[0].split('.')[-1] for p in ps}
    names = ' '.join(p.get('name','') for p in ps)
    if vuln == 'file-upload':
        return ('multipart' in locs) or bool(types & {'MultipartFile','Part','CommonsMultipartFile','MultipartHttpServletRequest'})
    if vuln == 'path-traversal':
        return bool(types & {'File','Path'}) or (bool(types & {'String'}) and bool(re.search(r'(?i)path|file|name|dir', names)))
    if vuln == 'ssrf':
        return bool(types & {'URL','URI'}) or (bool(types & {'String'}) and bool(re.search(r'(?i)url|uri|host|domain|callback|redirect|target|webhook|image', names)))
    if vuln == 'deserialization':
        # Spring @RequestBody 默认由 Jackson 解析，不等于"原生反序列化"；
        # 只有显式反序列化信号或 byte[]/Object 入口才算相关。
        return bool(types & {'byte[]','Object','Serializable'}) or (
            ('body' in locs) and bool(signal_hits(ep, 'deserialization')))
    if vuln == 'sql-injection':
        return bool(types & {'String','StringBuilder','StringBuffer'}) or ('body' in locs)
    if vuln == 'command-exec':
        return bool(types & {'String'}) and bool(re.search(r'(?i)cmd|command|exec|script|expression|template|content|code', names))
    if vuln == 'xss':
        # 后端返回 JSON（Result<T>）不等于 XSS；只有直接写响应/模板/有输出信号才相关。
        return ('response' in locs) or bool(signal_hits(ep, 'xss'))
    return True

# ── 接收者类型推断 / 调用解析 ─────────────────────────────
def infer_type(expr, body, off, params, proj, cls):
    """尽力推断表达式的静态类型；推不出返回 ''。"""
    expr = (expr or '').strip()
    if not expr:
        return ''
    if re.fullmatch(r'this|super', expr):
        return proj['parents'].get(cls, cls) if expr == 'super' else (cls or '')
    m = re.fullmatch(r'(?:this\.)?(\w+)', expr)
    if m:
        n = m.group(1)
        for p in (params or []):
            if p['name'] == n:
                return p['type'].split('<')[0].split('.')[-1]
        # 局部变量：取调用点之前最后一次声明
        pat = re.compile(r'\b([A-Z][\w.]*(?:\s*<[^;{}()]*>)?(?:\[\])?)\s+' + re.escape(n) + r'\s*[=;,)]')
        ds = list(pat.finditer(body[:off]))
        if ds:
            return ds[-1].group(1).split('<')[0].split('.')[-1]
        # enhanced-for：for (Map.Entry<K,V> entry : ...)
        fe = list(re.finditer(r'for\s*\(\s*(?:final\s+)?([A-Z][\w.]*(?:\s*<[^;{}()]*>)?)\s+' + re.escape(n) + r'\s*:', body[:off]))
        if fe:
            return fe[-1].group(1).split('<')[0].split('.')[-1]
        ft = proj['fields'].get(cls, {}).get(n, '')
        return ft.split('<')[0].split('.')[-1] if ft else ''
    m = re.fullmatch(r'(?:this\.)?(\w+)\.(\w+)', expr)
    if m:
        t = infer_type(m.group(1), body, off, params, proj, cls)
        ft = proj['fields'].get(t, {}).get(m.group(2), '')
        return ft.split('<')[0].split('.')[-1] if ft else ''
    m = re.fullmatch(r'new\s+([A-Z][\w.]*)\s*\(.*\)', expr, re.S)
    if m:
        return m.group(1).split('.')[-1]
    m = re.fullmatch(r'\(\s*([\w.]+)\s*\).*', expr, re.S)
    if m:
        return m.group(1).split('.')[-1]
    return ''

def receiver_of(body, off):
    m = re.search(r'([\w.]+)\s*\.\s*$', body[:off])
    return m.group(1) if m else ''

def _bean_match(recv, impl, proj):
    """接收者变量名是否像这个实现类的 bean 名（deptService / deptServiceImpl / DeptServiceImpl）。"""
    base = impl[:-4] if impl.endswith('Impl') else impl
    names = {impl, base, base[:1].lower() + base[1:]}
    b = proj.get('bean_names', {}).get(impl)
    if b:
        names.add(b)
    return recv.split('.')[-1] in names

def resolve_callee(body, off, callee, params, proj, cls):
    """返回 (defs, how)。how: typed / typed-impl / self / framework / external / unresolved"""
    recv = receiver_of(body, off)
    if recv in ('this', 'super'):
        recv = ''
    if recv:
        t = infer_type(recv, body, off, params, proj, cls)
        if not t:
            if recv[:1].isupper():
                return [], 'external'
            if recv.split('.')[-1].lower() in ('log', 'logger'):
                return [], 'external'
            return [], 'unresolved'
        t0 = t
        seen = set()
        for _ in range(4):
            if not t or t in seen:
                break
            seen.add(t)
            dm = proj['methods'].get(t, {}).get(callee)
            if dm:
                return dm[:3], 'typed'
            impls = proj['impls'].get(t, [])
            if len(impls) > 1:
                picked = [i for i in impls if _bean_match(recv, i, proj)]
                if len(picked) == 1:
                    impls = picked
            for impl in impls:
                dm = proj['methods'].get(impl, {}).get(callee)
                if dm:
                    return dm[:3], 'typed-impl'
            t = proj['parents'].get(t, '')
        # 工程内类型：只有"有方法体/有实现"才值得记为未解析；
        # 接口或空类（委托外部/框架）→ external，避免 ambiguous 洪水。
        if recv[:1].isupper():
            return [], 'external'   # 静态工具类：类里没有这个方法就是外部
        if t0.split('.')[-1] in proj['classes']:
            if proj['methods'].get(t0) or proj['impls'].get(t0):
                return [], 'unresolved'
        return [], 'external'
    # 无接收者：本类 + 父类
    t = cls
    seen = set()
    while t and t not in seen:
        seen.add(t)
        dm = proj['methods'].get(t, {}).get(callee)
        if dm:
            return dm[:3], 'self'
        t = proj['parents'].get(t, '')
    if callee in FRAMEWORK_METHODS:
        return [], 'framework'
    return [], 'unresolved'

def arg_types_of(args, body, off, params, proj, cls):
    ts = []
    for a in split_args(args):
        t = infer_type(a, body, off, params, proj, cls)
        if t:
            ts.append(t)
    return ts

def analyze_ep(ep,idx,xml_map,ann_map,perm,proj):
    """返回 {vuln: cell}"""
    out={}
    params=ep['params']
    pnames=[p['name'] for p in params]
    # 可达块（带文件行号）
    stats={'unresolved_service':0,'unresolved_domain':0,'ambiguous':0,
           'typed':0,'typed_impl':0,'self':0,'name_unique':0,'external':0}
    _p0=((ep['handler'],ep['file'],ep.get('bline',ep['line'])),)
    seen=set(); q=deque([(ep['handler'],ep['body'],ep['file'],ep['line'],0,tuple(pnames),ep['params'],string_params(ep['params']),ep.get('bline',ep['line']),ep.get('cls',''),_p0)])
    blocks=[]; flows=defaultdict(list); xml_hits=defaultdict(list); ann_hits=defaultdict(list)
    while q:
        nm,body,file,line,d,seeds,bparams,sseeds,bline,cls,bpath=q.popleft()
        key=(nm,file,d)
        if key in seen: continue
        seen.add(key)
        tainted=taint_names(body,seeds)
        tdet=taint_names(body,sseeds,True)
        blocks.append((nm,file,line,body,tainted,bparams,tdet,bline,cls,bpath))
        if d>=4: continue
        for callee,args,off in collect_calls(body):
            arglist=[a.strip() for a in split_args(args)]
            hot=[i for i,a in enumerate(arglist)
                 if any(re.search(r'\b'+re.escape(v)+r'\b',a) for v in tainted)]
            if callee in xml_map and hot:
                xml_hits[callee].append((xml_map[callee][1],xml_map[callee][2],arglist,hot))
            if callee in ann_map and hot:
                for t,f,l in ann_map[callee]: ann_hits[callee].append((t,f,l,arglist,hot))
            defs,how = resolve_callee(body,off,callee,bparams,proj,cls)
            if how=='unresolved':
                if callee in FRAMEWORK_METHODS:
                    how='framework'
                else:
                    cand=idx.get(callee,[])
                    if len(cand)>1:
                        parts=split_args(args)
                        by=IDX_ARITY.get(callee,{}).get(len(parts),[])
                        if by: cand=by
                        if len(cand)>1 and parts:
                            at0=infer_type(parts[0],body,off,bparams,proj,cls)
                            if at0:
                                narrowed=[d for d in cand
                                          if d['params'] and d['params'][0]['type'].split('<')[0].split('.')[-1]==at0]
                                if narrowed: cand=narrowed
                    if len(cand)==1:
                        defs=cand; how='name_unique'
                    elif len(cand)>1:
                        stats['ambiguous'] += 1
            stats[how] = stats.get(how,0)+1
            if defs:
                for defn in defs:
                    cps=[p['name'] for p in defn['params']]
                    nseeds=tuple(cps[i] for i in hot if i<len(cps))
                    nss=tuple(cps[i] for i in hot if i<len(cps) and defn['params'][i]['type'].split('<')[0] in STR_TYPES)
                    q.append((callee,defn['body'],defn['file'],defn['line'],d+1,nseeds,defn['params'],nss,defn.get('bline',defn['line']),defn.get('cls',''),bpath+((callee,defn['file'],defn.get('bline',defn['line'])),)))
            elif how=='unresolved' and hot and callee not in xml_map and callee not in ann_map:
                # 只有"带着污染实参"的未解析调用才可能成为漏掉的链路；
                # 常量实参的调用与污点无关，不计入（否则未验证会再次泛滥）。
                recv = receiver_of(body,off)
                if re.search(r'(?i)(mapper|dao|repository)$', recv):
                    stats['unresolved_domain'] += 1
                elif re.search(r'(?i)(service|client|util|helper|manager)$', recv):
                    stats['unresolved_service'] += 1

    blob='\n'.join(b[3] for b in blocks)
    has_da=bool(re.search(r'\.(getById|selectOne|selectList|getOne|list|page|updateById|save|insert|removeById|executeQuery|executeUpdate|selectById|deleteById)\s*\(|Mapper\.\w+\s*\(|jdbcTemplate\.|redisService\.|redisUtil\.|StringRedisTemplate|(?<![\w.])(?:list|getOne|getById|save|saveBatch|updateById|removeById|page|count)\s*\(',blob))
    # principal 只认真正的登录上下文；不要用 DTO 里的 getTenantId 冒充 principal
    principal=bool(re.search(r'RequestHeaderUtil\.getRequestHeader|getRequestHeader\s*\(\s*\)|SecurityContext|@AuthenticationPrincipal|UserContext\.require|\bLoginUser\b|\bPrincipal\b|getLoginUser',blob))
    has_ext=bool(re.search(r'HttpRequest\.(?:post|get)|HttpUtil\.|\.(?:postForObject|getForObject|getForEntity|postForEntity|exchange)\s*\(|getHisData|sendPostToApi',blob))
    # XSS：显式设置了非 HTML 的 Content-Type（如 text/csv、application/json）→ 不是 XSS
    _ct=re.search(r'setContentType\s*\(\s*"([^"]+)"', ep['body'])
    xss_html = (not _ct) or ('html' in _ct.group(1).lower())
    for vuln,pat in SINK_PAT.items():
        sinks=[]
        for nm,file,line,body,tainted,bparams,tdet,bline,cls,bpath in blocks:
            for m in re.finditer(pat,body):
                args=tail_args(body,m.start())
                if not args.strip():
                    args=body[m.start():m.start()+400]
                ats=arg_types_of(args,body,m.start(),bparams,proj,cls)
                if not sink_signature_ok(vuln, m.group(0), ats):
                    continue
                if vuln=='path-traversal':
                    # Paths.get(dir, archiveId) 里的 archiveId 是 Long，不是路径；
                    # 只看"带污点实参"的类型，避免把数字拼接误判成路径穿越。
                    hot_types=[]
                    for a in split_args(args):
                        if any(re.search(r'\b'+re.escape(v)+r'\b',a) for v in tainted):
                            t=infer_type(a,body,m.start(),bparams,proj,cls)
                            if t: hot_types.append(t)
                    if hot_types and not (set(hot_types) & {'String','StringBuilder','StringBuffer','Path','File','URI','URL'}):
                        continue
                pool = tdet if vuln=='ssrf' else tainted
                probe = args
                if vuln=='ssrf':
                    probe = ssrf_target(body, m.group(0), m.start()) or args
                if any(re.search(r'\b'+re.escape(v)+r'\b',probe) for v in pool):
                    sinks.append({'api':m.group(0).strip(),'file':rel(file),
                                  'line':(bline or line)+body[:m.start()].count('\n'),
                                  'param':arg_hit(args,tainted),
                                  'arg_types':','.join(ats[:3]),
                                  'receiver':receiver_of(body,m.start()),
                                  'path':[{'method':x[0],'file':rel(x[1]),'line':x[2]} for x in bpath[-5:]]})
        if vuln=='xss' and not xss_html:
            sinks=[]
        if vuln=='sql-injection':
            for callee,hs in xml_hits.items():
                for f,l,arglist,hot in hs:
                    if '${' in xml_map[callee][0]:
                        sinks.append({'api':'MyBatis ${}','file':rel(f),'line':l,'param':arglist[hot[0]] if hot else ''})
            for callee,hs in ann_hits.items():
                for txt,f,l,arglist,hot in hs:
                    if '${' in txt:
                        sinks.append({'api':'MyBatis @Select ${}','file':rel(f),'line':l,
                                      'param':arglist[hot[0]] if hot else ''})
        if sinks:
            guards=detect_guards(vuln,blocks)
            taint='direct' if len(blocks)<=2 else 'indirect'
            out[vuln]={'eligibility':'applicable','sinks':sinks[:5],'guards':guards,
                       'taint':taint,'hops':len(blocks),
                       'chain':[{'method':b[0],'file':rel(b[1]),'line':b[2]} for b in blocks[:6]],
                       'resolution':{'typed':stats['typed'],'typed_impl':stats['typed_impl'],
                                     'self':stats['self'],'name_unique':stats['name_unique'],
                                     'framework':stats.get('framework',0),
                                     'external':stats['external'],'ambiguous':stats['ambiguous'],
                                     'unresolved':stats['unresolved_service']+stats['unresolved_domain']}}
        else:
            out[vuln]={'eligibility':'not_applicable',
                       'reason':na_reason(vuln,blocks),
                       'trace':[f"{rel(b[1])}:{b[2]} {b[0]}" for b in blocks[:5]]}
    # 调用链不完整时不能断言"不适用"，但也不直接派单：单列 unverified（可见、可后补审计）。
    for v, c in list(out.items()):
        if c['eligibility'] != 'not_applicable':
            continue
        relcnt = stats['unresolved_service'] + (stats['unresolved_domain'] if v == 'sql-injection' else 0)
        if v == 'sql-injection' and not has_da:
            continue   # 全程不访问数据层，不可能有 SQL sink
        if (relcnt > 0 or stats['ambiguous'] > 0) and type_plausible(v, ep):
            c['eligibility'] = 'unverified'
            c['reason'] = (f"调用链不完整：{relcnt} 处相关未解析调用、{stats['ambiguous']} 处同名歧义，"
                           f"无法确认该类 sink 不存在")

    # authz 单独：判据 = 是否访问数据层/文件资源 + 是否有 principal 介入
    has_file_da = bool(
        (out.get('file-upload', {}) or {}).get('sinks') or
        (out.get('path-traversal', {}) or {}).get('sinks')
    )
    res_param=[]
    for p in params:
        if re.search(r'(?i)^(id|.*id|.*no|.*code|.*key)$',p['name']):
            res_param.append(p['name'])
        if p.get('location')=='body' and p.get('type') in proj['fields']:
            for fn in proj['fields'][p['type']]:
                if re.search(r'(?i)(id|no|code|key|tenant|org|dept|user)$', fn):
                    res_param.append(p['name']+'.'+fn)
    res_param=list(dict.fromkeys(res_param))[:8]
    ext_unauth = has_ext and not principal
    if has_da or has_file_da or ext_unauth:
        da_sites=[]; principal_sites=[]; owner_pred=[]; owner_ev=None
        for nm,file,line,body,tainted,bparams,tdet,bline,cls,bpath in blocks:
            if owner_ev is None:
                om=OWNER_RE.search(body)
                if om:
                    owner_ev={'file':rel(file),'line':(bline or line)+body[:om.start()].count('\n'),'api':om.group(0)[:60]}
            for m in re.finditer(r'([\w.]+)\s*\.\s*(getById|selectOne|selectList|getOne|list|page|updateById|save|insert|removeById|executeQuery|executeUpdate|selectById|deleteById)\s*\(', body):
                da_sites.append({'file':rel(file),'line':(bline or line)+body[:m.start()].count('\n'),'call':m.group(0).strip(),
                                 'path':[{'method':x[0],'file':rel(x[1]),'line':x[2]} for x in bpath[-5:]]})
            for m in re.finditer(r'(?:RequestHeaderUtil|getRequestHeader|SecurityContext|UserContext|LoginUser)[\w.]*\.?\w*\s*\(|\bgetUserId\s*\(\s*\)|\bprincipal\.getId\s*\(\s*\)', body):
                principal_sites.append({'file':rel(file),'line':(bline or line)+body[:m.start()].count('\n'),'call':m.group(0).strip()})
            for m in re.finditer(r'(?i)(?:where[^;{}]{0,80}|eq\s*\(\s*"[^"]*(?:user|tenant|org|dept|owner)[^"]*"|set\w+\s*\(\s*"[^"]*(?:user|tenant|org|dept|owner)[^"]*")', body):
                owner_pred.append({'file':rel(file),'line':(bline or line)+body[:m.start()].count('\n'),'expr':m.group(0).strip()[:80]})
        g=[]
        if principal: g.append({'name':'principal 已出现（需确认是否介入查询条件）','file':rel(ep['file']),'line':ep['line']})
        if principal_sites: g.append({'name':'显式取当前用户','file':principal_sites[0]['file'],'line':principal_sites[0]['line']})
        if has_file_da and not da_sites:
            _fs = (out.get('path-traversal', {}) or {}).get('sinks') or (out.get('file-upload', {}) or {}).get('sinks') or []
            for _s in _fs[:3]:
                da_sites.append({'file':_s.get('file'),'line':_s.get('line'),
                                 'call':_s.get('api','文件操作'),'path':_s.get('path',[])})
        if owner_ev: g.append({'name':'归属校验','file':owner_ev['file'],'line':owner_ev['line']})
        _az_reason = ('访问数据层' if has_da else
                      ('未登录且调用外部数据服务（未授权访问）' if ext_unauth else
                       '访问文件资源（读/写文件也是资源）'))
        out['authz']={'eligibility':'applicable',
                      'reason':_az_reason,
                      'guards':g,'taint':'direct' if principal else 'none',
                      'hops':len(blocks),'resource_params':res_param,
                      'ownership':bool(owner_ev),
                      'ownership_at':(f"{owner_ev['file']}:{owner_ev['line']}" if owner_ev else ''),
                      'da_sites':da_sites[:6],'principal_sites':principal_sites[:4],
                      'owner_predicates':owner_pred[:5],
                      'chain':[{'method':b[0],'file':rel(b[1]),'line':b[2]} for b in blocks[:6]],
                      'resolution':{'typed':stats['typed'],'typed_impl':stats['typed_impl'],
                                    'self':stats['self'],'name_unique':stats['name_unique'],
                                    'framework':stats.get('framework',0),
                                    'external':stats['external'],'ambiguous':stats['ambiguous'],
                                    'unresolved':stats['unresolved_service']+stats['unresolved_domain']},
                      'sinks':[{'api':'数据访问','file':rel(blocks[0][1]),'line':blocks[0][2],'param':','.join(res_param[:3])}]}
    else:
        out['authz']={'eligibility':'not_applicable','reason':'未访问数据层（无 DB/缓存/文件读写）',
                      'trace':[f"{rel(b[1])}:{b[2]} {b[0]}" for b in blocks[:3]]}
    if perm=='公开' and re.search(r'(?i)login|logout|register|token|health|ping', ep['url']):
        out['authz']={'eligibility':'not_applicable','reason':'公开的登录/健康接口，资源授权无意义',
                      'trace':[f"{rel(ep['file'])}:{ep['line']} {ep['handler']}"]}
    return out

def split_args(s):
    out=[];d=0;b=''
    for ch in s:
        if ch in '(<[': d+=1
        elif ch in ')>]': d-=1
        if ch==',' and d==0: out.append(b);b=''
        else: b+=ch
    if b.strip(): out.append(b)
    return out

def tail_args(body,idx):
    o=body.find('(',idx)
    if o<0: return ''
    d=0
    for i in range(o,len(body)):
        if body[i]=='(': d+=1
        elif body[i]==')':
            d-=1
            if d==0: return body[o+1:i]
    return body[o:o+200]

LOCAL_TYPE=re.compile(r'\b([A-Z][\w\.]*)\s+(\w+)\s*[=;,)]')
def var_types(body, params):
    t={p['name']:p['type'] for p in params}
    for m in LOCAL_TYPE.finditer(body):
        t.setdefault(m.group(2), m.group(1))
    return t

def ssrf_target(body, matched, start):
    """返回本次调用的「URL 实参」表达式"""
    if 'openConnection' in matched:
        head=body[:start]
        m=re.search(r'([\w\.\[\]]+)\s*\.\s*$', head)
        return m.group(1) if m else ''
    args=tail_args(body,start)
    parts=split_args(args)
    return parts[0] if parts else ''

def ssrf_arg_ok(body, params, start):
    """ImageIO.read(File) 不是 SSRF；只有 URL/String/byte[] 来源才算"""
    o=body.find('(',start)
    if o<0: return True
    d=0; close=len(body)
    for i in range(o,len(body)):
        if body[i]=='(': d+=1
        elif body[i]==')':
            d-=1
            if d==0: close=i; break
    args=body[o+1:close]
    if 'ImageIO' not in body[start:start+40]:
        return True
    vt=var_types(body,params)
    for name,ty in vt.items():
        if re.search(r'\b'+re.escape(name)+r'\b',args):
            if ty.split('.')[-1] in ('File','InputStream','ByteArrayInputStream','MultipartFile'):
                return False
    if re.search(r'new\s+File\s*\(',args): return False
    return True

def arg_hit(args,tainted):
    # 固定顺序：set 的迭代顺序受 PYTHONHASHSEED 影响，会让同一份代码产出不同的 param
    for v in sorted(tainted):
        if re.search(r'\b'+re.escape(v)+r'\b',args): return v
    return ''

def detect_guards(vuln,blocks):
    """返回 [{name,file,line}]，精确到行，减少 worker 定位成本。"""
    g=[]
    for nm,file,line,body,tainted,bparams,tdet,bline,cls,bpath in blocks:
        rb=RAW_BODIES.get((file,bline),body)
        for pat,name in GUARD_PAT.get(vuln,[]):
            for m in re.finditer(pat,rb):
                loc=(bline or line)+rb[:m.start()].count('\n')
                item={'name':name,'file':rel(file),'line':loc}
                if item not in g:
                    g.append(item)
                if len(g)>=6:
                    return g
    return g

SIG_TYPES = {
    ('ImageIO','read'): {'ssrf': {'URL','URI','String'},
                         'path-traversal': {'File','InputStream','ByteArrayInputStream'}},
    ('Files','read'): {'path-traversal': {'Path','String'}},
    ('Files','newInputStream'): {'path-traversal': {'Path','String'}},
    ('Files','write'): {'file-upload': {'Path','String'}, 'path-traversal': {'Path','String'}},
    ('Files','copy'): {'file-upload': {'Path','String'}, 'path-traversal': {'Path','String'}},
    ('Files','move'): {'file-upload': {'Path','String'}, 'path-traversal': {'Path','String'}},
    ('HttpUtil','createPost'): {'ssrf': {'String','URL','URI'}},
    ('HttpUtil','createGet'): {'ssrf': {'String','URL','URI'}},
}

def _api_of(txt):
    m=re.match(r'([A-Za-z_$][\w$]*)\s*(?:\.\s*([A-Za-z_$][\w$]*))?', txt.strip())
    if not m: return '', ''
    return m.group(1), (m.group(2) or '')

def sink_signature_ok(vuln, txt, arg_types):
    """按签名收窄：同名方法的不同重载不能混为一谈（ImageIO.read(File) ≠ ImageIO.read(URL)）。"""
    recv,meth=_api_of(txt)
    allow=SIG_TYPES.get((recv,meth),{}).get(vuln)
    if not allow:
        return True
    if not arg_types:
        return True   # 类型推不出时不排除，避免误杀
    return bool(set(arg_types) & allow)

def na_reason(vuln,blocks):
    return f"调用链 {len(blocks)} 个方法内未发现 {VULN_CN[vuln]} 所需 Sink，且请求参数不可达"

def rel(p):
    try: return os.path.relpath(p,ROOT)
    except Exception: return p

def score(vuln,perm,taint,guards):
    base=VULN_BASE[vuln]
    exp={'公开':3,'登录用户':2,'管理员':1}.get(perm,2)
    tw={'direct':2,'indirect':1,'none':0}.get(taint,0)
    gw=0 if not guards else (-6 if len(guards)>=2 else -3)
    return max(1,base*exp+tw*2+gw)

def bucket(p): return 'P0' if p>=26 else ('P1' if p>=16 else 'P2')

# ══════════════════════════════════════════════════════════ 任务描述
OUTPUT_CONTRACT = {
  "verdicts": ["confirmed", "clean", "needs_more"],
  "confirmed_requires": "文件:行号 + 关键代码片段 + 触发条件（谁能调到、参数是否可控）",
  "clean_requires": "正向证据：在哪一行做了什么校验（不给证据不得判 clean）",
  "needs_more_requires": "说明缺什么证据、需要什么人确认",
  "forbidden": "不得使用运行时现象、请求响应、依赖版本推断作为证据；不运行代码、不发请求",
}

def render_task(t, low):
    """把一个格子渲染成 worker 可读的任务书。"""
    L = []
    L.append("【任务】" + t["direction"])
    L.append("")
    L.append("【判定标准】")
    for i, x in enumerate(t["checklist"], 1):
        L.append(f"{i}. {x}")
    L.append("")
    L.append("【已知线索（仅供参考，可能不准确或不完整）】")
    srcs = "、".join(f"{p['name']}({p.get('location','')},{p.get('type','')})" for p in t["hints"]["sources"][:8]) or "（未识别到显式参数）"
    L.append(f"- 入口参数：{srcs}")
    if t["hints"]["sinks"]:
        for sk in t["hints"]["sinks"][:3]:
            extra = f"（实参类型 {sk.get('arg_types')}）" if sk.get('arg_types') else ""
            L.append(f"- 代码中出现：{sk['api']} @ {sk['file']}:{sk['line']}{extra}")
            pth = sk.get('path') or []
            if len(pth) >= 2:
                L.append("  sink 路径：" + " → ".join(f"{x['method']}@{x['file']}:{x['line']}" for x in pth[:5])
                         + f" → {sk['file']}:{sk['line']}")
    else:
        L.append("- 代码中出现：未定位到明确 sink（请自行查找）")
    g = t["hints"]["guards"] or []
    gs = "、".join(f"{x['name']}@{x['file']}:{x['line']}" if isinstance(x, dict) else str(x) for x in g[:5])
    L.append(f"- 已发现守卫：{gs if gs else '未发现'}")
    ch = t["hints"].get("chain") or []
    if ch and not t["hints"]["sinks"]:
        L.append("- 可达方法（BFS 顺序，非单一路径）：" + " → ".join(f"{x['method']}@{x['file']}:{x['line']}" for x in ch[:6]))
    az = t["hints"].get("authz") or {}
    if az.get("resource_params"):
        L.append("- 资源标识参数（重点核对归属绑定）：" + "、".join(az["resource_params"][:6]))
    if az.get("da_sites"):
        L.append("- 数据访问点：" + "、".join(f"{x['call']}@{x['file']}:{x['line']}" for x in az["da_sites"][:4]))
        pth = az["da_sites"][0].get("path") or []
        if len(pth) >= 2:
            L.append("  访问路径：" + " → ".join(f"{x['method']}@{x['file']}:{x['line']}" for x in pth[:5]))
    if az.get("principal_sites"):
        L.append("- 当前用户取值点：" + "、".join(f"{x['call']}@{x['file']}:{x['line']}" for x in az["principal_sites"][:3]))
    if az.get("owner_predicates"):
        L.append("- 疑似归属谓词：" + "、".join(f"{x['expr']}@{x['file']}:{x['line']}" for x in az["owner_predicates"][:3]))
    if low:
        L.append("- 注意：结构层未确认该类风险，本方向来自命名/注释提示")
    if t.get("variant") == "sec":
        L.append("- 本接口命名含 sec/safe/valid，预期已有防护：重点验证既有过滤能否被绕过，不要只确认它存在")
    L.append("")
    L.append("【要求】")
    L.append("- 独立核实以上线索，不要直接采信")
    L.append("- 除上述线索外，检查该接口是否还有其他同类入口/路径")
    L.append("- 结论只能是 confirmed / clean / needs_more 之一")
    L.append("- confirmed：给 文件:行号 + 代码片段 + 触发条件")
    L.append("- clean：给正向证据（哪一行做了什么校验），无证据不得判 clean")
    L.append("- needs_more：说明缺什么证据")
    L.append("- 只做源码静态分析，不运行代码、不发起请求")
    return "\n".join(L)

def expand_sources(params, proj, cap=10):
    """body DTO 展开成字段级来源，worker 可以直接看到 tenantId/branchId 这类归属字段。"""
    out=[]
    for p in params or []:
        out.append(p)
        if p.get('location')=='body' and p.get('type') in proj['fields']:
            for fn,ft in proj['fields'][p['type']].items():
                out.append({'name':p['name']+'.'+fn,'type':ft,'location':'body-field'})
        if len(out)>=cap: break
    return out[:cap]

def guard_names(c):
    return {x['name'] if isinstance(x, dict) else str(x) for x in (c.get('guards') or [])}

def is_hardened(ep):
    """接口命名是否明确是加固版（sec/safe/valid/security）。"""
    return bool(re.search(r'(?i)(?:^|[/_.-])(sec|safe|valid|security)(?:$|[/_.-])',
                          (ep.get('url','') + ' ' + ep.get('handler',''))))

def hold_reason(vuln, ep, c, perm):
    """已有守卫 → 保留在矩阵可见，但不派单（hold）。

    守卫不等于安全，只是"先不烧 token"。因此只对**结构性**守卫放行：
    归属校验、canonical/startsWith、参数化、UUID 重命名；
    名字型白名单（SSRF 域名白名单、上传后缀白名单）可能是可绕过的，
    只有在接口命名明确是 sec/safe 变体时才 hold。
    """
    g = guard_names(c)
    hardened = is_hardened(ep)
    if vuln == 'authz':
        if c.get('ownership'):
            return '已有归属校验（' + (c.get('ownership_at') or '') + '）'
        if perm == '管理员':
            return '全局拦截器已做管理员角色校验'
        return ''
    if vuln == 'path-traversal':
        strong = [x for x in ('路径 startsWith 校验','路径规范化校验') if x in g]
        if strong:
            return '路径限制（' + '、'.join(strong) + '）'
        if 'cleanPath 净化' in g and '.. 过滤' in g:
            return 'cleanPath + .. 过滤'
        if hardened and '路径白名单/过滤' in g:
            return '路径白名单（加固版接口）'
        return ''
    if vuln == 'sql-injection':
        if '排序/字段白名单' in g or 'SQL 白名单过滤' in g:
            return '字段/排序白名单'
        if 'MyBatis 预编译' in g or 'PreparedStatement 占位符' in g:
            return '参数化查询'
        return ''
    if vuln == 'file-upload':
        if 'UUID 重命名' in g and ('cleanPath 净化' in g or '.. 过滤' in g):
            return '文件名净化 + 重命名'
        if hardened and len(g) >= 2:
            return '加固版接口的多重上传校验（' + '、'.join(sorted(g)[:2]) + '）'
        return ''
    if vuln == 'ssrf':
        # 域名/IP 白名单经常可绕过；只在 sec/safe 变体上 hold
        if hardened and ('域名/IP 白名单或 SSRF 钩子' in g or '协议校验' in g):
            return 'SSRF 白名单（加固版接口）'
        return ''
    if vuln in ('command-exec','deserialization','xss'):
        if hardened and g:
            return '加固版接口的' + '、'.join(sorted(g)[:2])
        return ''
    return ''

def build_task(ep, vuln, c, perm, hits, var, flags, csig, aid, p, low):
    seen=set(); uniq=[]
    for sk in c.get("sinks", []):
        k=(sk.get("file"), sk.get("line"), sk.get("api"))
        if k in seen: continue
        seen.add(k); uniq.append(sk)
    c=dict(c); c["sinks"]=uniq
    direction = f"审计 {ep['http']} {ep['url']} 的「{VULN_CN[vuln]}」风险"
    t = {
      "task_id": f"{aid or ep['url']}:{vuln}",
      "asset_ids": [aid] if aid else [],
      "direction": direction,
      "vulnclass": vuln,
      "endpoint": {"asset_id": aid, "method": ep["http"], "url": ep["url"],
                   "permission": perm, "handler": ep["handler"],
                   "file": rel(ep["file"]), "line": ep["line"], "params": ep["params"]},
      "checklist": CHECKLIST[vuln],
      "hints": {
        "sources": ep.get("source_hints") or ep["params"],
        "sinks": c.get("sinks", []),
        "guards": c.get("guards", []),
        "chain": [] if c.get("sinks") else c.get("chain", []),
        "authz": {"da_sites": c.get("da_sites", []),
                  "principal_sites": c.get("principal_sites", []),
                  "owner_predicates": c.get("owner_predicates", []),
                  "resource_params": c.get("resource_params", [])} if vuln == "authz" else {},
        "resolution": c.get("resolution", {}),
        "hint_confidence": "low" if low else ("high" if c.get("taint")=="direct" else "medium"),
      },
      "hints_note": "以上线索由静态分析自动生成，可能不准确或不完整；请独立核实，并检查该接口是否还有其他同类入口。",
      "output_contract": OUTPUT_CONTRACT,
      "variant": var, "signals": hits, "flags": flags, "comment_signals": csig,
      "priority": p, "bucket": ("P3" if low else bucket(p)), "taint": c.get("taint", "none"),
      "evidence": {"sources": ep.get("source_hints") or ep["params"], "sinks": c.get("sinks", []),
                   "guards": c.get("guards", [])},
      "prompt_fragment": f"{vuln}-v1",
    }
    t["prompt"] = render_task(t, low)
    return t

# ══════════════════════════════════════════════════════════ Tier 2 信号
def _file_comments(raw):
    """返回 [(line_no, text)]，支持 // 与 /* */ 跨行。"""
    if not raw: return []
    out=[]; i=0; n=len(raw); line=1
    while i<n:
        if raw.startswith('//',i):
            j=raw.find('\n',i)
            if j<0: j=n
            out.append((line, raw[i+2:j].strip())); i=j; continue
        if raw.startswith('/*',i):
            j=raw.find('*/',i+2)
            if j<0: j=n
            body=raw[i+2:j]
            out.append((line, ' '.join(x.strip().lstrip('*').strip() for x in body.split('\n') if x.strip())))
            line+=body.count('\n'); i=j+2; continue
        if raw[i]=='\n': line+=1
        i+=1
    return out

SWAGGER=re.compile(r'@Api(?:Operation|ModelProperty)?\s*\(\s*(?:value\s*=\s*)?"([^"]{2,200})"',re.S)
def collect_comments(raw, start_line, end_line):
    if not raw: return ''
    cs=_file_comments(raw)
    seg=[t for (ln,t) in cs if start_line-25<=ln<=end_line+2 and t]
    sw=SWAGGER.findall(raw[start_line*0-0:])  # 占位
    return ' | '.join(seg)[:600]

def collect_doc(raw, lo_line, hi_line):
    """注释 + Swagger 描述；窗口 = [上一个方法结束, 本方法结束]"""
    if not raw: return ''
    cs=_file_comments(raw)
    seg=[t for (ln,t) in cs if lo_line<=ln<=hi_line+2 and t]
    lines=raw.split('\n')
    win='\n'.join(lines[max(0,lo_line-1):min(len(lines),hi_line+2)])
    seg += SWAGGER.findall(win)
    return ' | '.join(x for x in seg if x)[:800]

SIGNALS = {
 'file-upload':    {'param':r'(?i)^(file|files|uploadfile|attachment|multipart)$|upload',
                    'method':r'(?i)upload|import',
                    'path':r'(?i)upload|import|attach',
                    'comment':r'上传|附件|导入'},
 'path-traversal': {'param':r'(?i)path|filename|file|dir|name',
                    'method':r'(?i)download|read|export|image|file',
                    'path':r'(?i)download|file|export|read|image',
                    'comment':r'路径|下载|读取|文件'},
 'sql-injection':  {'param':r'(?i)sql|order|sort|query|keyword|name|search|where',
                    'method':r'(?i)query|search|list|page|find|select|count',
                    'path':r'(?i)query|search|list|page|find',
                    'comment':r'查询|搜索|排序|分页'},
 'command-exec':   {'param':r'(?i)cmd|command|exec|script|expression|template|content',
                    'method':r'(?i)exec|run|cmd|eval|shell|script|template',
                    'path':r'(?i)exec|cmd|shell|rce|eval',
                    'comment':r'命令|执行|表达式|脚本|模板'},
 'ssrf':           {'param':r'(?i)url|uri|host|domain|callback|redirect|target|webhook|image',
                    'method':r'(?i)proxy|fetch|request|callback|webhook|redirect|open',
                    'path':r'(?i)proxy|fetch|callback|webhook|redirect|ssrf|url',
                    'comment':r'远程|请求|回调|代理|地址'},
 'deserialization':{'param':r'(?i)data|content|payload|rememberme|cookie|stream',
                    'method':r'(?i)deserialize|read|parse|load|decode',
                    'path':r'(?i)deserialize|parse|load|read',
                    'comment':r'反序列化|解析|加载'},
 'xss':            {'param':r'(?i)content|name|msg|text|title|comment',
                    'method':r'(?i)echo|reflect|show|render|output|view|print',
                    'path':r'(?i)xss|echo|render|show|view',
                    'comment':r'输出|渲染|回显'},
 'authz':          {'param':r'(?i)(^|_)id$|.*Id$|userId|tenantId|orgId|deptId',
                    'method':r'(?i)delete|update|edit|save|add|grant|reset|export',
                    'path':r'(?i)admin|manage|internal|debug|delete|update|export|import|upload',
                    'comment':r'权限|管理员|越权'},
}

ASSERT_PAT = re.compile(r'(?i)白名单|黑名单|过滤|转义|参数化|预编译|已校验|做了校验|安全处理|防护|修复|safe|secure|whitelist|black\s*list|filter|sanitiz|validat|escape|parameteriz|\bfix\b')
NEG_PAT    = re.compile(r'(?i)未校验|未过滤|不校验|未做|没有校验|存在.{0,6}风险|漏洞|不安全|可绕过|绕过|临时|待修复|未修复|todo|fixme|vuln|vulnerab|unsafe|bypass|not\s+check')
IMPACT_PAT = re.compile(r'(?i)任意文件|命令执行|代码执行|注入|越权|敏感信息|getshell|rce|ssrf|反序列化')

def _hits(pat, text, limit=3):
    if not text: return []
    return sorted(set(m.group(0) for m in pat.finditer(text)))[:limit]

def doc_relevant(ep, vuln):
    txt=ep.get('comments','') or ''
    rule=SIGNALS.get(vuln,{})
    if not txt: return False
    return bool('comment' in rule and re.search(rule['comment'], txt))

def comment_signals(text):
    return {'assert':_hits(ASSERT_PAT,text),'neg':_hits(NEG_PAT,text),'impact':_hits(IMPACT_PAT,text)}

def signal_hits(ep, vuln):
    rule=SIGNALS.get(vuln,{})
    hits=[]
    url=(ep['url'] or '').lower(); mth=(ep['handler'] or '').lower()
    pnames=' '.join(p['name'] for p in ep['params'])
    com=ep.get('comments','')
    if 'path' in rule and re.search(rule['path'],url): hits.append('路径')
    if 'method' in rule and re.search(rule['method'],mth): hits.append('方法名')
    if 'param' in rule and pnames and re.search(rule['param'],pnames): hits.append('参数名')
    if 'comment' in rule and com and re.search(rule['comment'],com): hits.append('注释')
    return hits

def variant_of(ep):
    u=(ep['url'] or '').lower(); m=(ep['handler'] or '').lower()
    if re.search(r'(sec|safe|valid|check|filter|black)',u+m): return 'sec'
    if re.search(r'(vuln|unsafe|test|bad|danger)',u+m): return 'vuln'
    return 'unknown'

# ══════════════════════════════════════════════════════════ 主流程
def main():
    import time as _time
    _t0=_time.time()
    clean,masked,raws,xml_map,ann_map,idx,proj=parse_project(ROOT)
    pub=load_permission(ROOT)
    policy=load_auth_policy(clean)
    eps=endpoints(clean,masked,idx,raws)
    # 端点所属类（用于接收者类型推断：controller 的 @Autowired 字段）
    _owner={}
    for cls,mms in proj['methods'].items():
        for nm,defs in mms.items():
            for d in defs:
                _owner[(d['file'],nm,d.get('bline',d['line']))]=cls
                _owner.setdefault((d['file'],nm),cls)
    for ep in eps:
        ep['cls']=_owner.get((ep['file'],ep['handler'],ep.get('bline',-1))) or _owner.get((ep['file'],ep['handler']),'')
    cells=[];tasks=[];review=[]
    cnt=defaultdict(int)
    for ep in eps:
        perm=permission_of(ep['url'],pub,policy['admin'])
        aid=ASSET_MAP.get(f"{ep['http']} {ep['url']}") or ASSET_MAP.get(f"ANY {ep['url']}")
        ep['source_hints']=expand_sources(ep['params'],proj)
        res=analyze_ep(ep,idx,xml_map,ann_map,perm,proj)
        for vuln,c in res.items():
            hits=signal_hits(ep,vuln); var=variant_of(ep)
            csig=comment_signals(ep.get('comments',''))
            docrel=doc_relevant(ep,vuln)
            row={'endpoint':{'asset_id':aid,'method':ep['http'],'url':ep['url'],
                             'permission':perm,'handler':ep['handler'],
                             'file':rel(ep['file']),'line':ep['line'],
                             'params':ep['params']},
                 'vulnclass':vuln,'eligibility':c['eligibility'],
                 'signals':hits,'variant':var}
            if c['eligibility']=='applicable' and hold_reason(vuln,ep,c,perm):
                hr=hold_reason(vuln,ep,c,perm)
                row.update({'eligibility':'hold','sinks':c.get('sinks',[]),
                            'guards':c.get('guards',[]),'taint':c.get('taint'),
                            'hops':c.get('hops',0),'reason':'已有守卫：'+hr,
                            'priority':0,'bucket':'HOLD'})
                cnt['held']+=1
            elif c['eligibility']=='applicable':
                p=score(vuln,perm,c['taint'],c.get('guards'))
                p += min(6, 2*len(hits))
                if vuln=='authz' and re.search(r'(?i)admin|manage|internal|debug', ep['url']): p += 6
                flags=[]
                if docrel and csig['neg']: p += 4; flags.append('注释自述风险')
                if docrel and csig['assert'] and not csig['neg']:
                    p -= 2; flags.append('注释声明已有防护')
                    if var=='unknown': var='sec'
                if docrel and csig['assert'] and csig['neg']: p += 6; flags.append('注释自相矛盾')
                if var=='sec': p -= 3
                p=max(1,p)
                if docrel and csig['assert']:
                    c['guards']=list(c.get('guards') or [])+[{'name':'注释声明：'+'/'.join(csig['assert']),
                                                              'file':rel(ep['file']),'line':ep['line']}]
                row.update({'sinks':c['sinks'],'guards':c.get('guards',[]),
                            'taint':c['taint'],'hops':c.get('hops',0),'priority':p,'bucket':bucket(p)})
                cnt['applicable']+=1; cnt[bucket(p)]+=1
                tasks.append(build_task(ep,vuln,c,perm,hits,var,flags,csig,aid,p,False))
            else:
                # 方向式派发：结构未确认但命名/注释可疑 → 低优先级派出
                strong = ('参数名' in hits) or ('注释' in hits and '路径' in hits) or (docrel and bool(csig['neg']))
                if strong:
                    row.update({'eligibility':'needs_review','signals':hits,
                                'reason':'结构层未确认，命名/注释提示可能相关',
                                'trace':c.get('trace',[])})
                    cnt['needs_review']+=1
                    # 默认只派"多信号/注释自述风险"的格子；单信号格子保留在矩阵里可见，
                    # 不派单（省 token，也避免 worker 对着空气找 sink）。
                    ship = DISPATCH_LOW or len(hits)>=2 or (docrel and bool(csig['neg']))
                    if ship:
                        tasks.append(build_task(ep,vuln,c,perm,hits,var,['结构未确认'],csig,aid,8,True))
                    else:
                        cnt['low_unshipped']+=1
                    review.append({'endpoint':row['endpoint'],'vulnclass':vuln,
                                   'signals':hits,'trace':c.get('trace',[]),
                                   'comment_signals':csig,
                                   'dispatched':bool(ship),
                                   'question':f"是否真的不存在{VULN_CN[vuln]}风险？结构层未找到 Sink，但{('、'.join(hits) or '注释')}提示可能相关。"})
                else:
                    row.update({'reason':c.get('reason'),'trace':c.get('trace',[])})
                    cnt['not_applicable']+=1
            cells.append(row)

    cells.sort(key=lambda c:(c['endpoint']['url'], c['vulnclass']))
    tasks.sort(key=lambda x:(-x['priority'],x['endpoint']['url'],x['vulnclass']))
    _by=defaultdict(list)
    for t in tasks: _by[t['endpoint']['url']].append(t)
    for _u,_ts in _by.items():
        _ts.sort(key=lambda x:-x['priority'])
        for _i,_t in enumerate(_ts):
            _t['role']='primary' if _i==0 else 'secondary'
            _t['related_tasks']=[x['task_id'] for x in _ts if x is not _t]

    json.dump(cells,open(f'{PREFIX}/cells.json','w'),ensure_ascii=False,indent=1)
    json.dump(tasks,open(f'{PREFIX}/tasks.json','w'),ensure_ascii=False,indent=1)
    json.dump(review,open(f'{PREFIX}/review.json','w'),ensure_ascii=False,indent=1)

    N=len(eps); M=len(VULN_CN)
    print(f"接口: {N}   矩阵: {N}×{M} = {N*M} 格")
    print(f"结构确认(applicable) : {cnt['applicable']}")
    print(f"低置信(needs_review) : {cnt['needs_review']}")
    print(f"不派(not_applicable) : {cnt['not_applicable']}")
    print(f"派发任务合计         : {len(tasks)}   (P0/P1/P2/P3 = {cnt['P0']}/{cnt['P1']}/{cnt['P2']}/{cnt['needs_review']})")
    print(f"有守卫未派(hold)     : {cnt['held']}")
    print(f"低置信未派(矩阵可见) : {cnt['low_unshipped']}\n")
    print("按漏洞类型（结构确认数）：")
    for v in VULN_CN:
        a=sum(1 for c in cells if c['vulnclass']==v and c['eligibility']=='applicable')
        print(f"  {VULN_CN[v]:14s} {a:4d} / {N}")
    print("\n" + "="*110)
    print("Top 15 任务")
    print("="*110)
    for t in tasks[:15]:
        s0 = t['hints']['sinks'][0] if t['hints']['sinks'] else {'api':'—','file':'—','line':'-'}
        print(f"[{t['bucket']} {t['priority']:2d}] {t['endpoint']['method']:5s} {t['endpoint']['url'][:36]:38s} "
              f"{VULN_CN[t['vulnclass']]:10s} {str(s0['api'])[:20]:22s} {str(s0['file']).split('/')[-1]}:{s0['line']}")
    print("\n=== 一条完整任务（渲染后的 prompt）===")
    print(tasks[0]['prompt'])
    print("\n=== 一条低置信任务 ===")
    low=[t for t in tasks if t['hints']['hint_confidence']=='low']
    if low: print(low[0]['prompt'])
    rep = {
      "files": len(clean),
      "lines": sum(v.count(chr(10))+1 for v in clean.values()),
      "endpoints": N,
      "cells": len(cells),
      "applicable": sum(1 for c in cells if c['eligibility']=='applicable'),
      "needs_review": sum(1 for c in cells if c['eligibility']=='needs_review'),
      "not_applicable": sum(1 for c in cells if c['eligibility']=='not_applicable'),
      "unverified": sum(1 for c in cells if c['eligibility']=='unverified'),
      "hold": cnt['held'],
      "low_unshipped": cnt['low_unshipped'],
      "avg_prompt_chars": round(sum(len(t['prompt']) for t in tasks)/max(1,len(tasks))),
      "tasks": len(tasks),
      "duration_sec": round(_time.time()-_t0, 2),
      "lines_per_sec": round(sum(v.count(chr(10))+1 for v in clean.values())/max(0.01,_time.time()-_t0)),
    }
    json.dump(rep, open(f'{PREFIX}/report.json','w'), ensure_ascii=False, indent=1)
    print("\n=== 生成报告 ===")
    for k in ("files","lines","endpoints","cells","applicable","needs_review","not_applicable","unverified","hold","low_unshipped","tasks","duration_sec","lines_per_sec","avg_prompt_chars"):
        print(f"  {k:16s} {rep[k]}")
    print(f"\n输出: {PREFIX}/tasks.json ({len(tasks)} 条)  cells.json ({len(cells)} 格)  report.json")

if __name__=='__main__':
    main()
