"""Inspect the frozen official input preprocessing, without generating forecasts.

AST extraction executes the installed pure preprocessing routines verbatim. It
avoids importing or loading a second model while the single GPU queue is active.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
TF_SOURCE = ROOT / '.cache/v431-timesfm-source/src/timesfm/timesfm_2p5/timesfm_2p5_base.py'
BOLT_SOURCE = Path('/home/vipuser/work2-envs/w2-chronos/lib/python3.11/site-packages/chronos/chronos_bolt.py')


def source_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _extract(path, names, namespace, method=None):
    tree = ast.parse(Path(path).read_text())
    nodes = [n for n in tree.body if getattr(n, 'name', None) in names]
    if method:
        owner, member = method
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner)
        nodes.append(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == member))
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)] + nodes, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), 'exec'), namespace)
    return namespace


def timesfm_inputs(x):
    """Capture actual official values/masks immediately before compiled_decode."""
    ns = _extract(TF_SOURCE, ['strip_leading_nans', 'linear_interpolation'], {'np': np}, ('TimesFM_2p5', 'forecast'))
    class Captured(Exception):
        pass
    result = {}
    def capture(horizon, values, masks):
        result.update(values=np.asarray(values), masks=np.asarray(masks))
        raise Captured()
    obj = SimpleNamespace(compiled_decode=capture, global_batch_size=1,
                          forecast_config=SimpleNamespace(max_context=512))
    try:
        ns['forecast'](obj, 96, [np.asarray(x).copy()])
    except Captured:
        pass
    if not result:
        raise RuntimeError('Official TimesFM preprocessing did not reach decoder')
    result['source_sha256'] = source_sha(TF_SOURCE)
    return result


def bolt_inputs(x):
    """Actual Patch and InstanceNorm classes, before learned patch embedding."""
    import torch
    ns = _extract(BOLT_SOURCE, ['Patch', 'InstanceNorm'], {'torch': torch, 'nn': torch.nn})
    values = torch.as_tensor(np.asarray(x).copy(), dtype=torch.float32)[None, -2048:]
    masks = ~torch.isnan(values)
    normalized, _ = ns['InstanceNorm']()(values)
    patch = ns['Patch'](16, 16)
    patched_mask = torch.nan_to_num(patch(masks.to(torch.bfloat16)), nan=0.)
    patched = torch.where(patched_mask > 0, patch(normalized.to(torch.bfloat16)), 0.)
    return dict(values=torch.cat([patched, patched_mask], dim=-1).float().numpy(),
                masks=(patched_mask.sum(dim=-1) > 0).numpy(), source_sha256=source_sha(BOLT_SOURCE))


def compare_inputs(long, short, family):
    from introact_ts.v43.schemas import array_hash
    transform = {'bolt': bolt_inputs, 'timesfm': timesfm_inputs}[family]
    a, b = transform(long), transform(short)
    same = all(np.array_equal(a[k], b[k], equal_nan=True) for k in ('values', 'masks'))
    return dict(family=family, long_length=len(long), short_length=len(short),
                long_model_shape=list(a['values'].shape), short_model_shape=list(b['values'].shape),
                long_model_input_hash=array_hash(a['values']), short_model_input_hash=array_hash(b['values']),
                long_model_mask_hash=array_hash(a['masks']), short_model_mask_hash=array_hash(b['masks']),
                actual_preprocessing_identical=same, source_sha256=a['source_sha256'],
                scope='official preprocessing only; no artificial forecast or model accuracy result')
