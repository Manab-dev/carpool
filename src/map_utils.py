# src/map_utils.py

import folium
from streamlit_folium import st_folium
import networkx as nx
import osmnx as ox

def plot_paths_on_map(paths, graph, locations, best_driver_info):
    """Plot paths and intersections on a Folium map."""
    
    folium_map = folium.Map(location=[12.9716, 77.5946], zoom_start=12)

    # Add markers for the office and companion
    for label, (lat, lon) in locations.items():
        color = 'blue' if label.startswith('driver') else 'red' if label == 'office' else 'green'
        folium.Marker(
            location=[lat, lon],
            popup=label,
            icon=folium.Icon(color=color)
        ).add_to(folium_map)

    # Plot each driver's path to the office
    for driver_label, path in paths.items():
        if not path:
            continue
        path_coords = [(graph.nodes[node]['y'], graph.nodes[node]['x']) for node in path]
        folium.PolyLine(
            locations=path_coords,
            color='red',
            weight=2.5,
            opacity=0.8,
            popup=f"{driver_label} to Office"
        ).add_to(folium_map)

    # Highlight the best driver path and intersection
    for driver_label, (aerial_distance, driver_time, intersection_node) in best_driver_info.items():
        if driver_label in paths and paths[driver_label]:
            best_path = paths[driver_label]
            best_path_coords = [(graph.nodes[node]['y'], graph.nodes[node]['x']) for node in best_path]
            folium.PolyLine(
                locations=best_path_coords,
                color='green',
                weight=3,
                opacity=0.8,
                popup=f"Best Driver: {driver_label}, Distance: {aerial_distance:.2f} km"
            ).add_to(folium_map)

            # Add the best intersection point
            intersection_coords = (graph.nodes[intersection_node]['y'], graph.nodes[intersection_node]['x'])
            folium.Marker(
                location=intersection_coords,
                popup=f"Best Intersection: {driver_label}",
                icon=folium.Icon(color='orange')
            ).add_to(folium_map)
    # Add the companion's path to the intersection node
    for driver_label, (aerial_distance, driver_time, intersection_node) in best_driver_info.items():
        companion_node = ox.distance.nearest_nodes(graph, locations['companion'][1], locations['companion'][0]) 
        if intersection_node:
            path_to_intersection = nx.shortest_path(graph,source=companion_node, target=intersection_node, weight="distance")

            if path_to_intersection:
                companion_path_coords = [(graph.nodes[node]['y'], graph.nodes[node]['x']) for node in path_to_intersection]
                folium.PolyLine(
                    locations=companion_path_coords,
                    color='blue',
                    weight=3,
                    opacity=0.8,
                    popup="Companion Path to Intersection"
                ).add_to(folium_map)

    return folium_map