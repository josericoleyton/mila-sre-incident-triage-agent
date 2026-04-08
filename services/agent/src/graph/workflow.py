from pydantic_graph import Graph

from src.domain.models import TriageDeps, TriageResult, TriageState
from src.graph.nodes.analyze_input import AnalyzeInputNode
from src.graph.nodes.classify import ClassifyNode
from src.graph.nodes.generate_output import GenerateOutputNode
from src.graph.nodes.search_code import SearchCodeNode

triage_graph = Graph(
    nodes=[AnalyzeInputNode, SearchCodeNode, ClassifyNode, GenerateOutputNode],
)
