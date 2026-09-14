"""Read an audited historical producer as a frozen input, never relabel its hash."""
import json
from pathlib import Path
import numpy as np
from .data_io import file_hash
from .schemas import Episode, array_hash, require
from .worker_protocol import verify_response


class FrozenP2Archive:
    def __init__(self, root, evidence_path):
        self.root = Path(root)
        evidence = json.loads(Path(evidence_path).read_text())
        require(Path(evidence['run']).resolve() == self.root.resolve(), 'archive/evidence run mismatch')
        self.provenance = dict(run=str(self.root.resolve()), producer_code_hash=evidence['code_hash'],
                               producer_commit=evidence['code_commit'], evidence_sha256=file_hash(evidence_path))
        for name, digest in evidence['artifact_sha256'].items():
            require(file_hash(self.root/name) == digest, f'frozen archive changed: {name}')
        require(self.read('status')['status'] == self.read('independent_verification')['status'] == 'completed', 'archive not audited')
        self.meta = self.read('episode_manifest')
        self.candidates = self.arrays('candidates.npz')
        self.forecasts = self.arrays('forecasts.npz')
        self.aliases = self.read('forecast_aliases')
        self.contexts = {}
        self.base_predictions = {uid: {} for uid in self.meta}
        self.base_costs = {}
        self.cov_costs = {}
        for horizon in (96, 192):
            for suffix in ('nested', 'cov', 'bolt'):
                shard = f'h{horizon}-{suffix}'
                request, response = self.read(shard+'.request'), self.read(shard+'.response')
                output = self.arrays(shard+'.predictions.npz')
                verify_response(request, response, [output[f'row_{i}'] for i in range(len(request['rows']))])
                for i, (row, result) in enumerate(zip(request['rows'],response['rows'])):
                    uid = row['episode_uid']
                    if suffix == 'nested':
                        self.base_predictions[uid][row['input_hash']] = output[f'row_{i}']
                        self.base_costs[uid,row['input_hash']] = result['runtime_seconds']
                    elif suffix == 'cov':
                        self.cov_costs[uid] = result['runtime_seconds']
                    elif row['candidate_id'] == 'A0_NATIVE':
                        payload = self.arrays_path(row['array_path'])
                        for name,key in [('target','input_hash'),('raw_mask','raw_mask_hash'),('covariates','covariate_hash'),('timestamps','timestamps_hash'),('availability','availability_hash')]:
                            require(array_hash(payload[name]) == row[key], 'archive payload changed')
                        m = self.meta[uid]
                        self.contexts[uid] = Episode(uid,m['source'],m['source'],m['parent_group'],m['split'],0,
                            m['raw_start'],m['context_end'],horizon,payload['timestamps'],payload['target'],payload['covariates'],payload['availability'])
        require(set(self.contexts) == set(self.meta), 'archive context registry incomplete')

    def read(self, name):
        return json.loads((self.root/(name+'.json')).read_text())

    @staticmethod
    def arrays_path(path):
        with np.load(path,allow_pickle=False) as f:
            return {key:f[key] for key in f.files}

    def arrays(self,name):
        return self.arrays_path(self.root/name)

    def forecast(self,uid,arm):
        return self.forecasts[self.aliases[uid+'_'+arm]]
