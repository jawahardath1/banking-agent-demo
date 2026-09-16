"""Repeatable acceptance demo: creates a fresh synthetic review run on each invocation."""
import argparse
import json
import time
import urllib.request

parser=argparse.ArgumentParser()
parser.add_argument("--base-url",default="http://127.0.0.1:8000")
parser.add_argument("--approve",action="store_true",help="Explicitly authorize the demo script to create a review case")
args=parser.parse_args()


def request(path,body=None):
    req=urllib.request.Request(args.base_url+"/api"+path,data=None if body is None else json.dumps(body).encode(),headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=180) as response: return json.load(response)


def wait(id):
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        run=request("/reviews/"+id)
        if run["status"] != "RUNNING": return run
        time.sleep(.5)
    raise TimeoutError("Review did not complete within four minutes")


id=request("/reviews",{"message":"Review application L002 against our lending policies. Identify risks and recommend the next action."})["run_id"]
run=wait(id)
assert run["status"]=="AWAITING_APPROVAL",run
assert run["case"] is None
assessment=next(e["detail"] for e in run["events"] if e["step"]=="evaluate_application")
assert assessment["recommendation"]=="Enhanced Manual Review"
assert {x["citation_id"] for x in assessment["risks"]}=={"CR-01","CR-02","IV-01","IV-02"}
print(json.dumps({"run_id":id,"assessment":assessment},indent=2))
if not args.approve:
    args.approve=input("Type APPROVE to create the review case: ").strip()=="APPROVE"
request(f"/reviews/{id}/decision",{"approved":args.approve,"reviewer":"Demo Script Reviewer"})
run=wait(id)
assert run["status"]==("COMPLETED" if args.approve else "DECLINED"),run
assert bool(run["case"])==args.approve
if args.approve:
    original=run["case"]["case_id"]
    request(f"/reviews/{id}/decision",{"approved":True,"reviewer":"Demo Script Reviewer"})
    assert wait(id)["case"]["case_id"]==original
print(json.dumps({"result":"PASS","status":run["status"],"case":run["case"]},indent=2))
