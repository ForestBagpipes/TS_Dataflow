# -*- coding: utf-8 -*-
"""把附录表格里的旧 baseline 行换成 v4.4-r2 的五个正式 baseline，
并把 RMSSE 统一为 RMSE（任务书 §20 固定四个指标：MASE / MAE / RMSE / MSE）。"""
import io
import re

P = r'F:\work\Time-research\work2\latex\introact_ts_iclr27_v44.tex'
s = io.open(P, encoding='utf-8').read()
orig = s

# ---------------------------------------------------------------- 1) RMSSE -> RMSE
s = s.replace('RMSSE', 'RMSE')

# ---------------------------------------------------------------- 2) 逐来源表列名
s = s.replace('Source & $H$ & MASE $\\downarrow$ & MSE $\\downarrow$ & MAE $\\downarrow$ & RMSE $\\downarrow$ \\\\',
              'Source & $H$ & MASE $\\downarrow$ & MAE $\\downarrow$ & RMSE $\\downarrow$ & MSE $\\downarrow$ \\\\')

# ---------------------------------------------------------------- 3) 重建-效用配对表
old_rec = '''    BRITS       & \\ph{BRITS-MSE}  & \\ph{BRITS-MAE}  & \\ph{BRITS-MASE}  & \\ph{BRITS-GAIN}  & \\multirow{6}{*}{\\ph{DISCORDANT}} \\\\
    CSDI        & \\ph{CSDI-MSE}   & \\ph{CSDI-MAE}   & \\ph{CSDI-MASE}   & \\ph{CSDI-GAIN}   & \\\\
    TOI         & \\ph{TOI-MSE}    & \\ph{TOI-MAE}    & \\ph{TOI-MASE}    & \\ph{TOI-GAIN}    & \\\\
    T1          & \\ph{T1-MSE}     & \\ph{T1-MAE}     & \\ph{T1-MASE}     & \\ph{T1-GAIN}     & \\\\
    TATO        & \\ph{TATO-MSE}   & \\ph{TATO-MAE}   & \\ph{TATO-MASE}   & \\ph{TATO-GAIN}   & \\\\
    \\rowcolor{bestgray}\\introact{} & \\ph{OURS-MSE}   & \\ph{OURS-MAE}   & \\ph{OURS-MASE}   & \\ph{OURS-GAIN}   & \\\\'''
new_rec = '''    TOI                & \\ph{REC_TOI_MSE}    & \\ph{REC_TOI_MAE}    & \\ph{REC_TOI_MASE}    & \\ph{REC_TOI_GAIN}    & \\multirow{6}{*}{\\ph{DISCORDANT_RATE}} \\\\
    TOI-VSF            & \\ph{REC_TOIVSF_MSE} & \\ph{REC_TOIVSF_MAE} & \\ph{REC_TOIVSF_MASE} & \\ph{REC_TOIVSF_GAIN} & \\\\
    GIMCC              & \\ph{REC_GIMCC_MSE}  & \\ph{REC_GIMCC_MAE}  & \\ph{REC_GIMCC_MASE}  & \\ph{REC_GIMCC_GAIN}  & \\\\
    SRDI               & \\ph{REC_SRDI_MSE}   & \\ph{REC_SRDI_MAE}   & \\ph{REC_SRDI_MASE}   & \\ph{REC_SRDI_GAIN}   & \\\\
    ChannelTokenFormer & \\ph{REC_CTF_MSE}    & \\ph{REC_CTF_MAE}    & \\ph{REC_CTF_MASE}    & \\ph{REC_CTF_GAIN}    & \\\\
    \\rowcolor{bestgray}\\introact{} & \\ph{REC_OURS_MSE} & \\ph{REC_OURS_MAE} & \\ph{REC_OURS_MASE} & \\ph{REC_OURS_GAIN} & \\\\'''
assert old_rec in s, 'recutils rows not found'
s = s.replace(old_rec, new_rec)
s = s.replace('Spearman $\\rho$ between reconstruction rank and\n    forecasting rank: Bolt \\ph{RHO-BOLT}, TimesFM \\ph{RHO-TF}, Chronos-2 \\ph{RHO-CH2}',
              'Spearman $\\rho$ between reconstruction rank and\n    forecasting rank: Bolt \\ph{RHO_BOLT}, TimesFM \\ph{RHO_TF}, Chronos-2 \\ph{RHO_CH2}')

# ---------------------------------------------------------------- 4) severity 三张表
SLOTS = [('BRITS', 'TOI'), ('CSDI', 'TOIVSF'), ('TOI', 'GIMCC'),
         ('T1', 'SRDI'), ('TATO', 'CTF')]
NAMES = {'TOI': 'TOI', 'TOIVSF': 'TOI-VSF', 'GIMCC': 'GIMCC',
         'SRDI': 'SRDI', 'CTF': 'ChannelTokenFormer'}

sev_lines = []
for sev in ('10', '30', '50'):
    for oldk, newk in SLOTS:
        # 行标签可能带不同数量的尾随空格，用正则容错
        pat = re.compile(r'^(\s*)(?:BRITS|CSDI|TOI|T1|TATO)(\s*)&(.*?)\\ph\{SEV%s-%s-(MASE|MSE|MAE|RMSE)\}(.*)$'
                         % (sev, re.escape(oldk)), re.M)
        def rep(m, sev=sev, newk=newk):
            return '%s%s%s&%s\\ph{SEV%s_%s_%s}%s' % (
                m.group(1), NAMES[newk], ' ' * max(1, 22 - len(NAMES[newk])),
                m.group(3), sev, newk, m.group(4), m.group(5))
        s, n = pat.subn(rep, s)
        sev_lines.append((sev, oldk, n))

# rank 列
for sev in ('10', '30', '50'):
    for oldk, newk in SLOTS:
        s = s.replace('\\ph{SEV%s-%s-RANK}' % (sev, oldk), '\\ph{SEV%s_%s_RANK}' % (sev, newk))

# ---------------------------------------------------------------- 5) per-pattern 表
pat_lines = 0
for oldk, newk in SLOTS:
    pat = re.compile(r'^(\s*)(?:BRITS|CSDI|TOI|T1|TATO)(\s*)&(.*?)\\ph\{P([1-4])-%s\}(.*?)\\ph\{PR-%s\}(.*)$'
                     % (re.escape(oldk), re.escape(oldk)), re.M)
    def rep2(m, newk=newk):
        return '%s%s%s&%s\\ph{P%s_%s}%s\\ph{PR_%s}%s' % (
            m.group(1), NAMES[newk], ' ' * max(1, 22 - len(NAMES[newk])),
            m.group(3), m.group(4), newk, m.group(5), newk, m.group(6))
    s, n = pat.subn(rep2, s)
    pat_lines += n

io.open(P, 'w', encoding='utf-8', newline='\n').write(s)
print('changed:', s != orig)
print('severity row hits:', sev_lines)
print('pattern row hits:', pat_lines)
print('remaining BRITS/CSDI/TATO:', len(re.findall(r'BRITS|CSDI|TATO', s)))
print('remaining RMSSE:', s.count('RMSSE'))
print('remaining T1 as method row:', len(re.findall(r'(?m)^\s*T1\s*&', s)))
