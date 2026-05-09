import json

class GoalGraphDecomposer:
    def __init__(self, llm=None):
        self.llm = llm
        self.goalgraph_decomposed = {}

    def build_graph(self, objects, relations):
        graph = {
            'nodes': [{'id': str(obj)} for obj in objects],
            'edges': [{'source': str(r['source']), 'target': str(r['target']), 'type': r['type']} for r in relations]
        }
        return graph

    def clean_edges(self, subgraphs):
        if not isinstance(subgraphs, dict):
            return
        for subgraph in subgraphs.values():
            if not isinstance(subgraph, dict):
                continue
            # Ensure nodes and edges keys exist and are lists
            if 'nodes' not in subgraph or not isinstance(subgraph['nodes'], list):
                subgraph['nodes'] = []
            if 'edges' not in subgraph or not isinstance(subgraph['edges'], list):
                subgraph['edges'] = []
            
            # Filter and keep only valid nodes (normalize id to str)
            valid_nodes = []
            node_ids = set()
            for node in subgraph['nodes']:
                if isinstance(node, dict) and 'id' in node:
                    node['id'] = str(node['id'])
                    valid_nodes.append(node)
                    node_ids.add(node['id'])
            subgraph['nodes'] = valid_nodes

            # Filter and keep only valid edges that link existing nodes (normalize source/target to str)
            valid_edges = []
            for edge in subgraph['edges']:
                if isinstance(edge, dict) and 'source' in edge and 'target' in edge:
                    edge['source'] = str(edge['source'])
                    edge['target'] = str(edge['target'])
                    if edge['source'] in node_ids and edge['target'] in node_ids:
                        valid_edges.append(edge)
            subgraph['edges'] = valid_edges

    def graph_to_text(self, graph):
        if not isinstance(graph, dict):
            return ""
        nodes_list = graph.get('nodes', [])
        edges_list = graph.get('edges', [])
        
        nodes = ', '.join([str(node['id']) for node in nodes_list if isinstance(node, dict) and 'id' in node])
        edges = ', '.join([f"{edge['source']} {edge['type']} {edge['target']}"
                          for edge in edges_list 
                          if isinstance(edge, dict) and 'source' in edge and 'target' in edge and 'type' in edge])
        return f"Nodes: {nodes}. Edges: {edges}."

    def goal_decomposition(self, goalgraph=None):
        prompt = (f"Task: Decompose the following graph into subgraphs where each subgraph contains strongly related nodes.\n"
                  f"Output Format: Return ONLY a valid JSON object. No preamble, no explanation.\n"
                  f"JSON Schema:\n"
                  f"{{\n"
                  f"  \"subgraph_1\": {{\n"
                  f"    \"nodes\": [{{ \"id\": \"node_id\" }}],\n"
                  f"    \"edges\": [{{ \"source\": \"id1\", \"target\": \"id2\", \"type\": \"relation\" }}]\n"
                  f"  }},\n"
                  f"  ...\n"
                  f"}}\n"
                  f"Constraints:\n"
                  f"1. Every node MUST be a dictionary with an 'id' key.\n"
                  f"2. Every edge MUST be a dictionary with 'source', 'target', and 'type' keys.\n"
                  f"3. DO NOT use strings as subgraph values. Use the specified JSON structure.\n\n"
                  f"Input Graph: {self.graph_to_text(goalgraph)}")

        max_attempts = 10
        attempts = 0
        while attempts < max_attempts:
            response = self.llm(prompt)
            
            # Pre-processing: Extract JSON if LLM wraps it in markdown
            clean_response = response
            if "```json" in response:
                clean_response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                clean_response = response.split("```")[1].split("```")[0].strip()

            try:
                self.goalgraph_decomposed = json.loads(clean_response)
                # Defensive cleaning
                self.clean_edges(self.goalgraph_decomposed)
                break
            except Exception:
                attempts += 1

        if attempts == max_attempts:
            # Fallback: if all attempts fail, use the whole graph as one subgraph
            self.goalgraph_decomposed = {'subgraph_1': goalgraph}

        return self.goalgraph_decomposed
