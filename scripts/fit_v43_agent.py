#!/usr/bin/env python3
import argparse
import json
from introact_ts.v43.agent_fit import fit_and_evaluate

parser=argparse.ArgumentParser()
parser.add_argument('run')
args=parser.parse_args()
print(json.dumps(fit_and_evaluate(args.run)),flush=True)
