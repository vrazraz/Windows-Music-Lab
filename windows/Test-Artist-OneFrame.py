"""Retired SDXL validation command: user removed this feature. No model/runtime imports."""
import argparse, json
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--plan',action='store_true')
p.add_argument('--run',action='store_true')
p.add_argument('--run-standalone',action='store_true')
args=p.parse_args()
print(json.dumps({'status':'removed_by_user','feature':'sdxl','testCancelled':True,'memoryReadyRequired':False,'weightsRetained':True,'inferenceAllowed':False}))
if args.run or args.run_standalone:
    raise SystemExit('SDXL validation was cancelled by the user; no execution is permitted')
