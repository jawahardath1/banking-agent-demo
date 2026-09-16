from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from .tools import get_loan_application, search_bank_policies, evaluate, create_review_case


class State(TypedDict, total=False):
    run_id: str
    application_id: str
    request: str
    application: dict
    query: str
    policies: list
    assessment: dict
    approved: bool
    case_id: str


def build_graph(store, provider, checkpointer):
    def load(state):
        application = get_loan_application(store, state["application_id"])
        store.event(state["run_id"], "get_loan_application", application)
        return {"application": application}

    def plan(state):
        query = provider.search_query(state["application"])
        store.event(state["run_id"], "plan_policy_search", {"query": query, "mode": provider.mode})
        return {"query": query}

    def retrieve(state):
        policies = search_bank_policies(store, provider, state["query"])
        store.event(state["run_id"], "search_bank_policies", {"query": state["query"], "sources": policies})
        return {"policies": policies}

    def assess(state):
        assessment = evaluate(state["application"], state["policies"])
        assessment["summary"] = provider.explain(state["application"], assessment)
        store.event(state["run_id"], "evaluate_application", assessment)
        return {"assessment": assessment}

    def approve(state):
        decision = interrupt({"question": "Create a review case for this assessment?", "recommendation": state["assessment"]["recommendation"]})
        if type(decision) is not bool:
            raise ValueError("Approval must be a boolean")
        store.event(state["run_id"], "human_approval", {"approved": decision})
        return {"approved": decision}

    def create(state):
        case_id = create_review_case(store, state["run_id"], state["application_id"], state["assessment"])
        store.event(state["run_id"], "create_review_case", {"case_id": case_id})
        return {"case_id": case_id}

    graph = StateGraph(State)
    for name, fn in [("load",load),("plan",plan),("retrieve",retrieve),("assess",assess),("approve",approve),("create",create)]:
        graph.add_node(name,fn)
    graph.add_edge(START,"load")
    for left,right in [("load","plan"),("plan","retrieve"),("retrieve","assess"),("assess","approve")]:
        graph.add_edge(left,right)
    graph.add_conditional_edges("approve",lambda s: "create" if s["approved"] else END)
    graph.add_edge("create",END)
    return graph.compile(checkpointer=checkpointer)
