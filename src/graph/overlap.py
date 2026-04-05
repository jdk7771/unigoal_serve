import json
import networkx as nx
from networkx.algorithms import isomorphism
import numpy as np
from scipy.spatial.distance import cosine
from heapq import heappush, heappop
from grakel import Graph, kernels
import re


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

    def calculate_relative_positions(self, graph):
        """ Calculate relative positions of nodes within a graph (G2) using LLM for unknown positions """
        relative_positions = {}
        nodes = list(graph.nodes)
        if not nodes:
            return {}

        ref_node = nodes[0]

        for node in nodes:
            if node == ref_node:
                continue
            prompt = f"Given the following information: {ref_node} and {node}. Please provide the relative position of {node} with respect to {ref_node} in the format [x, y]."
            response = self.llm(prompt)
            try:
                # Using regex for more robust coordinate parsing
                match = re.search(r'\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]', response)
                if match:
                    rel_pos = [float(match.group(1)), float(match.group(2))]
                    key = tuple((node, ref_node))
                    relative_positions[key] = rel_pos
            except (IndexError, ValueError, AttributeError):
                pass

        positions = {}
        if not relative_positions:
            for node in nodes:
                positions[node] = [0.0, 0.0]
            return positions

        # Reconstruct positions relative to ref_node (index 1 of the tuple)
        first_key = next(iter(relative_positions))
        actual_ref = first_key[1]
        positions[actual_ref] = [0.0, 0.0]
        for (node, ref), pos in relative_positions.items():
            if ref == actual_ref:
                positions[node] = pos

        return positions

    def predict_remaining_node_positions(self, mapping, positions, scene_graph):
        """
        Predict positions of unmatched nodes in G2 by anchoring them to matched nodes in G1 space.
        mapping: {G1_ID: G2_ID}
        positions: {G2_ID: [x, y]}
        scene_graph: G1 DiGraph
        """
        if len(mapping) < 2:
            return None

        # Find two G1 nodes that map to distinct G2 nodes for establishing reference frame
        distinct_matches = []
        seen_g2 = set()
        for g1_id, g2_id in mapping.items():
            if g2_id in positions and g2_id not in seen_g2:
                distinct_matches.append((g1_id, g2_id))
                seen_g2.add(g2_id)
            if len(distinct_matches) >= 2:
                break
        
        if len(distinct_matches) < 2:
            return None

        (g1_1, g2_1), (g1_2, g2_2) = distinct_matches

        try:
            ref_pos_1_g1 = np.array(scene_graph.nodes[g1_1]['position'])
            ref_pos_2_g1 = np.array(scene_graph.nodes[g1_2]['position'])
        except KeyError:
            return None

        ref_vec_scene = ref_pos_2_g1 - ref_pos_1_g1
        try:
            ref_vec_subgraph = np.array(positions[g2_2]) - np.array(positions[g2_1])
        except KeyError:
            return None

        if np.allclose(ref_vec_subgraph, 0):
            # If reference nodes in G2 are collapsed, fallback to average of G1 points
            return list((ref_pos_1_g1 + ref_pos_2_g1) / 2.0)

        # Calculate rotation and scale to transform G2 relative space into G1 physical space
        angle = np.arctan2(ref_vec_scene[1], ref_vec_scene[0]) - np.arctan2(ref_vec_subgraph[1], ref_vec_subgraph[0])
        rotation_matrix = np.array([[np.cos(angle), -np.sin(angle)],
                                    [np.sin(angle), np.cos(angle)]])

        norm_sub = np.linalg.norm(ref_vec_subgraph)
        scale_factor = np.linalg.norm(ref_vec_scene) / norm_sub if norm_sub > 1e-6 else 1.0

        all_matched_g2 = set(mapping.values())
        predicted_positions = []
        for g2_id, rel_pos in positions.items():
            if g2_id not in all_matched_g2:
                # Relative vector from anchor g2_1 to the unmatched node in G2 space
                relative_pos_in_g2 = np.array(rel_pos) - np.array(positions[g2_1])
                # Transform to G1 space: rotate -> scale -> translate
                transformed_pos = np.dot(rotation_matrix, relative_pos_in_g2 * scale_factor) + ref_pos_1_g1
                predicted_positions.append(transformed_pos)

        if not predicted_positions:
            # Fallback if no unmatched nodes found
            return list((ref_pos_1_g1 + ref_pos_2_g1) / 2.0)

        # Return the centroid of all predicted unmatched node positions
        position = sum(predicted_positions) / len(predicted_positions)
        return list(position)
