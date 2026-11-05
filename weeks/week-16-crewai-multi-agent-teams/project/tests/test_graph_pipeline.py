import os

os.environ.setdefault("OPENAI_API_KEY", "sk-placeholder-never-sent")

from langchain_openai import ChatOpenAI

from app.graph_pipeline import GraphPipeline


def test_graph_has_the_expected_nodes_and_conditional_abstain_edge():
    graph = GraphPipeline(ChatOpenAI(model="gpt-4o-mini", temperature=0)).graph.get_graph()
    assert {"retrieve", "grade", "synthesise", "abstain"} <= set(graph.nodes)
    edges = {(e.source, e.target, e.conditional) for e in graph.edges}
    assert ("grade", "synthesise", True) in edges
    assert ("grade", "abstain", True) in edges
