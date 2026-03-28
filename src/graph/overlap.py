import json
import networkx as nx
from networkx.algorithms import isomorphism
import numpy as np
from scipy.spatial.distance import cosine
from heapq import heappush, heappop
from grakel import Graph, kernels


class GraphMatcher:
    def __init__(self, graph1, graph2, llm=None):
        self.graph1 = graph1
        self.graph2 = graph2
        self.llm = llm

        G1 = nx.DiGraph()
        for node in graph1['nodes']:
            G1.add_node(node['id'], position=node['position'])
        for edge in graph1['edges']:
            G1.add_edge(edge['source'], edge['target'], type=edge['type'])

        G2 = nx.DiGraph()
        for node in graph2['nodes']:
            G2.add_node(node['id'])  # No position assigned initially
        for edge in graph2['edges']:
            G2.add_edge(edge['source'], edge['target'], type=edge['type'])
        self.G1 = G1
        self.G2 = G2

    def node_similarity(self, G1, G2):
        nodes_G1 = list(G1.nodes)
        nodes_G2 = list(G2.nodes)
        
        # Use semantic mapping instead of exact ID intersection
        common_mapping = self.find_common_nodes(G1, G2)
        common_nodes_G1 = list(common_mapping.keys())

        if len(nodes_G2) == 0:
            node_overlap_ratio = 0.0
        else:
            # Ratio of unique labels in G2 that have been found in G1
            matched_labels_G2 = set(common_mapping.values())
            node_overlap_ratio = len(matched_labels_G2) / len(nodes_G2)

        degree_sim = 0.0
        if common_nodes_G1:
            for node_G1 in common_nodes_G1:
                node_G2 = common_mapping[node_G1]
                degree_G1 = G1.degree(node_G1)
                degree_G2 = G2.degree(node_G2)
                degree_diff = abs(degree_G1 - degree_G2)
                max_degree = max(degree_G1, degree_G2)
                if max_degree > 0:
                    degree_sim += 1.0 - (degree_diff / max_degree)
            degree_sim /= len(common_nodes_G1)

        node_sim = (node_overlap_ratio + degree_sim) / 2.0
        return node_sim

    def edge_similarity(self, G1, G2):
        # Map G1 edges to label-based edges to compare with G2
        common_mapping = self.find_common_nodes(G1, G2)
        
        mapped_edges_G1 = set()
        for u, v, data in G1.edges(data=True):
            if u in common_mapping and v in common_mapping:
                # Convert G1 instance IDs to their matched labels in G2
                u_label = common_mapping[u]
                v_label = common_mapping[v]
                # Store as frozenset for unordered comparison if needed, 
                # but G2 uses DiGraph, so order (source, target) matters.
                edge_type = data.get('type', '')
                mapped_edges_G1.add((u_label, v_label, edge_type))

        edges_G2 = set()
        for u, v, data in G2.edges(data=True):
            edges_G2.add((u, v, data.get('type', '')))
        
        common_edges = mapped_edges_G1.intersection(edges_G2)

        if len(edges_G2) == 0:
            return 1.0
        else:
            return len(common_edges) / len(edges_G2)

    def graph_edit_distance_heuristic(self, G1, G2):
        node_diff = abs(len(G1) - len(G2))
        edge_diff = abs(G1.number_of_edges() - G2.number_of_edges())
        return node_diff + edge_diff

    def apply_operation(self, operation, G, **kwargs):
        if operation == 'add_node':
            G.add_node(kwargs['node'])
        elif operation == 'remove_node':
            G.remove_node(kwargs['node'])
        elif operation == 'add_edge':
            G.add_edge(*kwargs['edge'])
        elif operation == 'remove_edge':
            G.remove_edge(*kwargs['edge'])

    def overlap(self):
        G1 = self.G1
        G2 = self.G2

        self.common_nodes_mapping = self.find_common_nodes(G1, G2)
        # Store G1 IDs for backward compatibility with explore_remaining etc.
        self.common_nodes = set(self.common_nodes_mapping.keys())
        
        node_sim = self.node_similarity(G1, G2)
        edge_sim = self.edge_similarity(G1, G2)

        combined_sim = (node_sim + edge_sim) / 2
        return combined_sim

    def find_common_nodes(self, G1, G2):
        """ Find semantic matches between G1 (scenegraph with suffixes) and G2 (goalgraph labels) """
        mapping = {}
        for n1 in G1.nodes:
            # Strip instance suffix (e.g., 'chair_0' -> 'chair')
            label1 = n1.rsplit('_', 1)[0] if '_' in n1 else n1
            for n2 in G2.nodes:
                # Goal graph nodes are typically raw labels, but may also have suffixes
                label2 = n2.rsplit('_', 1)[0] if '_' in n2 else n2
                if label1.lower() == label2.lower():
                    mapping[n1] = n2
                    break
        return mapping

    def calculate_relative_positions(self, graph, common_nodes):
        """ Calculate relative positions of nodes within a graph using LLM for unknown positions """
        positions = {}
        if not common_nodes:
            return positions

        # Ensure we only deal with unique G2 labels
        unique_labels = []
        for n in common_nodes:
            if n not in unique_labels:
                unique_labels.append(n)
        
        if not unique_labels:
            return {}
            
        ref_label = unique_labels[0]
        # Always put the first reference label at the local origin
        positions[ref_label] = [0.0, 0.0]

        if len(unique_labels) == 1:
            return positions

        for label in unique_labels[1:]:
            prompt = f"Given the following information: {ref_label} and {label}. Please provide the relative position of {label} with respect to {ref_label} in the format [x, y]."
            response = self.llm(prompt)
            try:
                rel_pos_str = response.split("[")[1].split("]")[0]
                rel_pos = [float(coord.strip()) for coord in rel_pos_str.split(",")]
                positions[label] = rel_pos
            except (IndexError, ValueError) as e:
                # If LLM fails, we skip this label's relative position
                pass

        return positions

    def predict_remaining_node_positions(self, common_nodes, positions, scene_graph):
        """
        common_nodes: List of G1 instance IDs (e.g., ['chair_0', 'table_1'])
        positions: Dict of G2 label positions (e.g., {'chair': [0,0], 'table': [1,1]})
        """
        mapping = self.common_nodes_mapping
        
        # We need at least two G1 nodes that map to DIFFERENT G2 labels to calculate rotation/scale
        valid_ref_g1 = []
        for n1 in common_nodes:
            if n1 in mapping and mapping[n1] in positions:
                # Check if this G2 label is unique in our ref list to avoid [0,0] vectors
                if not any(mapping[n1] == mapping[prev] for prev in valid_ref_g1):
                    valid_ref_g1.append(n1)
        
        if len(valid_ref_g1) < 2:
            # Fallback: If we only have one anchor, we can't determine orientation/scale
            # Just return the position of the first anchor or a center if available
            if len(valid_ref_g1) == 1:
                return list(scene_graph.nodes[valid_ref_g1[0]]['position'])
            return [0, 0]

        ref_point_1, ref_point_2 = valid_ref_g1[:2]
        label_1, label_2 = mapping[ref_point_1], mapping[ref_point_2]

        ref_pos_1 = np.array(scene_graph.nodes[ref_point_1]['position'])
        ref_pos_2 = np.array(scene_graph.nodes[ref_point_2]['position'])

        ref_vec_scene = ref_pos_2 - ref_pos_1
        ref_vec_subgraph = np.array(positions[label_2]) - np.array(positions[label_1])

        if np.allclose(ref_vec_subgraph, 0):
            # This shouldn't happen with our 'different labels' check above, but for safety:
            if len(valid_ref_g1) == 1:
                return list(ref_pos_1)
            return [0, 0]

        angle = np.arctan2(ref_vec_scene[1], ref_vec_scene[0]) - np.arctan2(ref_vec_subgraph[1], ref_vec_subgraph[0])
        rotation_matrix = np.array([[np.cos(angle), -np.sin(angle)],
                                    [np.sin(angle), np.cos(angle)]])

        scale_factor = np.linalg.norm(ref_vec_scene) / np.linalg.norm(ref_vec_subgraph)

        predicted_positions = []
        # Predict positions for all nodes in the goal graph that we haven't found yet
        for label, rel_pos in positions.items():
            if label not in [label_1, label_2]:
                relative_position = np.array(rel_pos) - np.array(positions[label_1])
                transformed_pos = np.dot(rotation_matrix, np.array(relative_position) * scale_factor) + ref_pos_1
                predicted_positions.append(transformed_pos)

        if len(predicted_positions) > 0:
            position = np.mean(predicted_positions, axis=0)
        else:
            # If no 'remaining' nodes, the best we can do is the midpoint or first point
            position = (ref_pos_1 + ref_pos_2) / 2
            
        return list(position)
