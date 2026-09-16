import copy
import io
import json
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from app.config import settings
from app.ingest import chunks
from app.graph import build_graph
from app.providers import Providers
from app.tools import evaluate, get_loan_application, search_bank_policies, create_review_case

APP = {"application_id":"L002","name":"Mary Jones (Demo)","amount":45000,"term_months":60,"credit_score":630,"annual_income":72000,"dti_percent":42,"employment_months":8,"income_verified":False}

class FakeStore:
    def __init__(self):
        self.events=[]; self.cases={}; self.approved=False
    def application(self,id):
        if id != "L002": raise LookupError("Application not found")
        return copy.deepcopy(APP)
    def search(self,*args,**kwargs): return list(chunks(settings.documents_dir))
    def event(self,run,step,detail): self.events.append((step,detail))
    def create_case(self,run,app,assessment):
        if not self.approved: raise PermissionError("No recorded approval")
        self.cases.setdefault(run,"CASE-1")
        return self.cases[run]


def test_l002_pauses_then_creates_once_with_citations():
    store=FakeStore(); saver=InMemorySaver()
    graph=build_graph(store,Providers("demo"),saver)
    config={"configurable":{"thread_id":"run-1"}}
    graph.invoke({"run_id":"run-1","application_id":"L002"},config)
    state=graph.get_state(config)
    assert state.next == ("approve",)
    assert not store.cases
    a=state.values["assessment"]
    assert a["recommendation"] == "Enhanced Manual Review"
    assert {c["citation_id"] for c in a["risks"]} == {"CR-01","CR-02","IV-01","IV-02"}
    assert all(c["page"] > 0 and c["source"] and c["content_hash"] for c in a["checks"])
    # Rebuild the graph to prove resume uses the checkpoint.
    store.approved=True
    graph=build_graph(store,Providers("demo"),saver)
    graph.invoke(Command(resume=True),config)
    assert graph.get_state(config).values["case_id"] == "CASE-1"
    assert len(store.cases)==1
    assert [e[0] for e in store.events] == ["get_loan_application","plan_policy_search","search_bank_policies","evaluate_application","human_approval","create_review_case"]


def test_rejection_never_creates_case():
    store=FakeStore(); graph=build_graph(store,Providers("demo"),InMemorySaver())
    config={"configurable":{"thread_id":"reject"}}
    graph.invoke({"run_id":"reject","application_id":"L002"},config)
    graph.invoke(Command(resume=False),config)
    assert not store.cases
    assert not graph.get_state(config).next


def test_write_tool_cannot_bypass_saved_approval():
    with pytest.raises(PermissionError): create_review_case(FakeStore(),"x","L002",{})


@pytest.mark.parametrize("id",["L002' OR 1=1--","L002;DROP TABLE customers","../L002","l002"])
def test_ids_are_constrained(id):
    with pytest.raises(ValueError): get_loan_application(FakeStore(),id)


def test_incomplete_policy_coverage_fails_closed():
    store=FakeStore(); store.search=lambda *a,**kw: []
    with pytest.raises(ValueError,match="coverage"):
        search_bank_policies(store,Providers("demo"),"loan policy")


def test_policy_boundaries_and_pass_case():
    app={**APP,"amount":50000,"term_months":60,"credit_score":660,"dti_percent":40,"employment_months":12,"income_verified":True}
    result=evaluate(app,list(chunks(settings.documents_dir)))
    assert not result["risks"]
    assert result["recommendation"] == "Standard Manual Review"


def test_embedding_deterministic_normalized():
    p=Providers("demo"); v=p.embed("credit score policy")
    assert len(v)==1024 and v==p.embed("credit score policy")
    assert sum(x*x for x in v)==pytest.approx(1)


def test_bedrock_request_contracts():
    class Client:
        def invoke_model(self,**kwargs):
            self.embedding=kwargs
            return {"body":io.BytesIO(json.dumps({"embedding":[0.1]*1024}).encode())}
        def converse(self,**kwargs):
            self.conversation=kwargs
            name=kwargs["toolConfig"]["tools"][0]["toolSpec"]["name"]
            return {"output":{"message":{"content":[{"toolUse":{"name":name,"input":{"query":"credit policy"}}}]}}}
    client=Client(); p=Providers("bedrock",client)
    assert len(p.embed("policy"))==1024
    assert json.loads(client.embedding["body"])["dimensions"]==1024
    assert p.search_query(APP)=="credit policy"
    assert client.conversation["toolConfig"]["toolChoice"] == {"tool":{"name":"plan_policy_search"}}


def test_bad_embedding_dimension_rejected():
    class Client:
        def invoke_model(self,**kw): return {"body":io.BytesIO(b'{"embedding":[1]}')}
    with pytest.raises(ValueError,match="1024"): Providers("bedrock",Client()).embed("x")
