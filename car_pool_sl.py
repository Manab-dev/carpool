import streamlit as st
import folium
from streamlit_folium import st_folium
import time as tm
import osmnx as ox
import networkx as nx
import math
from collections import defaultdict
from typing import Dict, List, Tuple
EARTH_RADIUS_KM = 6371  # Radius of the Earth in kilometers

def load_bangalore_map_with_times() -> nx.Graph:
    """
    Load the road network for Bangalore from OSM and add travel times.
    """
    place_name = "Bangalore, India"
    graph = ox.graph_from_place(place_name, network_type='drive')
    ox.add_edge_speeds(graph)
    ox.add_edge_travel_times(graph)
    return graph

def calculate_aerial_distance(graph: nx.Graph, node1: int, node2: int) -> float:
    """
    Calculate the aerial distance between two nodes.
    """
    lat1, lon1 = graph.nodes[node1].get('y'), graph.nodes[node1].get('x')
    lat2, lon2 = graph.nodes[node2].get('y'), graph.nodes[node2].get('x')
    
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return float('inf')
    
    return get_distance_from_lat_lon_in_km(lat1, lon1, lat2, lon2)

def get_distance_from_lat_lon_in_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Compute the distance between two latitude-longitude points in kilometers.
    """
    R = 6371  # Radius of the Earth in kilometers
    dLat = deg2rad(lat2 - lat1)
    dLon = deg2rad(lon2 - lon1)
    a = math.sin(dLat / 2) ** 2 + math.cos(deg2rad(lat1)) * math.cos(deg2rad(lat2)) * math.sin(dLon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def deg2rad(deg: float) -> float:
    """
    Convert degrees to radians.
    """
    return deg * (math.pi / 180)

def find_best_paths(graph: nx.Graph, locations: Dict[str, Tuple[float, float]]) -> Dict[str, List[int]]:
    """
    Compute the shortest paths from drivers to the office based on travel time.
    """
    # print(locations)
    office_location = locations['office']
    office_node = ox.distance.nearest_nodes(graph, office_location[1], office_location[0])
    
    paths = {}
    
    for label, (lat, lon) in locations.items():
        if label.startswith('driver'):
            driver_node = ox.distance.nearest_nodes(graph, lon, lat)
            try:
                path = nx.shortest_path(graph, source=driver_node, target=office_node, weight='travel_time')
                paths[label] = path
            except nx.NetworkXNoPath:
                paths[label] = []  # No path found
    
    return paths

def calculate_driver_companion_distances(
    graph: nx.Graph,
    driver_paths: Dict[str, List[int]],
    companion_nodes: List[int]
) -> Dict[Tuple[str, int], List[Tuple[int, float]]]:
    """
    Calculate the top 5 closest nodes for each driver-companion pair based on aerial distance.
    """
    aerial_distances = {}
    
    for driver_label, path in driver_paths.items():
        if not path:
            continue
        for companion_node in companion_nodes:
            distances = []
            for node in path:
                if node in graph.nodes and companion_node in graph.nodes:
                    distance = calculate_aerial_distance(graph, node, companion_node)
                    distances.append((node, distance))
            
            top_5_nodes = sorted(distances, key=lambda x: x[1])[:5]
            aerial_distances[(driver_label, companion_node)] = top_5_nodes
    
    return aerial_distances

def find_best_intersection_node(
    graph: nx.Graph,
    driver_paths: Dict[str, List[int]],
    companion_nodes: List[int],
    aerial_distances: Dict[Tuple[str, int], List[Tuple[int, float]]]
) -> Dict[Tuple[str, int], Tuple[float, float, int]]:
    """
    Find the best intersection node among the top 5 nodes for each driver-companion pair.
    """
    road_distances = {}
    
    buffer_time = 5  # Buffer time in minutes
    
    for (driver_label, companion_node), top_5_nodes in aerial_distances.items():
        shortest_road_distance = float('inf')
        shortest_road_time = float('inf')
        best_intersection_node = None
        
        for node, _ in top_5_nodes:
            try:
                # Calculate road distance and travel time from the driver to the intersection node
                path_to_intersection = nx.shortest_path(graph, source=driver_paths[driver_label][0], target=node, weight='travel_time')
                road_distance_to_intersection = nx.shortest_path_length(graph, source=driver_paths[driver_label][0], target=node, weight='length')
                travel_time_to_intersection = sum(graph[u][v][0].get('travel_time', 0) for u, v in zip(path_to_intersection[:-1], path_to_intersection[1:]))
                
                # Calculate road distance and travel time from the intersection node to the companion
                path_from_intersection = nx.shortest_path(graph, source=node, target=companion_node, weight='length')
                road_distance_from_intersection = nx.shortest_path_length(graph, source=node, target=companion_node, weight='length')
                travel_time_from_intersection = sum(graph[u][v][0].get('travel_time', 0) for u, v in zip(path_from_intersection[:-1], path_from_intersection[1:]))
                
                if road_distance_from_intersection < shortest_road_distance and travel_time_from_intersection <= (travel_time_to_intersection + buffer_time):
                    shortest_road_distance = road_distance_from_intersection
                    shortest_road_time = travel_time_from_intersection
                    best_intersection_node = node
            
            except nx.NetworkXNoPath:
                continue
        
        road_distances[(driver_label, companion_node)] = (shortest_road_distance, shortest_road_time, best_intersection_node)
    
    return road_distances

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



def main():
    st.set_page_config(page_title="Car Pooling App", layout="wide")

    # New default driver locations
    default_driver_locations = [
        (13.064165569984327, 77.69139096635745),
        (12.9417027837777, 77.6047024498736),
        (12.954032807906207, 77.65954983678637),
        (13.058517489154386, 77.60478468841292),
        (12.880261914881979, 77.53660170901598),
        (12.940454648155722, 77.53464148361742),
        (12.853139039629268, 77.53113161431367),
        (13.019213642830296, 77.64707293682815),
        (12.924086544235553, 77.6240676997266),
        (12.890032282392307, 77.63744525906849),
    ]

    # Initialize session state
    if 'page' not in st.session_state:
        st.session_state.page = 'login'
    if 'markers' not in st.session_state:
        st.session_state.markers = []
    if 'driver_coords' not in st.session_state:
        st.session_state.driver_coords = []
    if 'driver_capacity' not in st.session_state:
        st.session_state.driver_capacity = []
    if 'office_location' not in st.session_state:
        st.session_state.office_location = (12.934, 77.62) # Updated office location
    if 'best_driver_info' not in st.session_state:
        st.session_state.best_driver_info = None
    if 'bangalore_graph' not in st.session_state:
        st.session_state.bangalore_graph = load_bangalore_map_with_times()

    if st.session_state.page == 'login':
        st.title("Welcome to the Car Pooling App")
        st.subheader("Please log in to continue")

        with st.form(key='login_form', clear_on_submit=True):
            name = st.text_input("Name")
            csid = st.text_input("CSID")
            submit_button = st.form_submit_button("Login")

            if submit_button and name and csid:
                st.session_state.logged_in = True
                st.session_state.user_name = name
                st.session_state.user_csid = csid
                st.session_state.page = 'map'
            elif submit_button:
                st.warning("Both fields are required!")

    elif st.session_state.page == 'map':
        st.title("Map Dashboard")
        st.write("Explore driver and companion locations")

        # Create the map
        folium_map = folium.Map(location=[12.9716, 77.5946], zoom_start=12)

        
        folium.Marker(location=[12.934, 77.62], popup="Office", icon=folium.Icon(color="red")).add_to(folium_map)

        # Companion Input
        st.sidebar.title("Companion Location")
        # lat = st.sidebar.text_input("Latitude", "12.937")
        # lon = st.sidebar.text_input("Longitude", "77.628")

        # if st.sidebar.button("Add Companion"):
        #     try:
        #         lat = float(lat)
        #         lon = float(lon)
        #         st.session_state.markers.append((lat, lon))
        #         st.success(f"Companion location added at ({lat}, {lon})")
        #     except ValueError:
        #         st.error("Invalid coordinates.")
                
                
        st.sidebar.title("Companion Location")
        companion_input = st.sidebar.text_input("Companion Location (lat,lon)", "12.937,77.628")        
        if st.sidebar.button("Add Companion"):
            try:
                lat, lon = map(float, companion_input.split(','))
                st.session_state.markers.append((lat, lon))
                st.success(f"Companion location added at ({lat}, {lon})")
            except ValueError:
                st.error("Invalid coordinates. Please enter in 'lat,lon' format.")
        for lat, lon in st.session_state.markers:
            folium.Marker(location=[lat, lon], popup="Companion", icon=folium.Icon(color="green")).add_to(folium_map)
        # Driver Options
        
        st.sidebar.title("Driver Options")
        num_drivers = st.sidebar.slider("Number of Drivers (1-10)", 1, 10)

        # driver_coords = []
        # capacity_list = []
        # for i in range(num_drivers):
        #     st.sidebar.subheader(f"Driver {i + 1}")
        #     lat = st.sidebar.text_input(f"Driver {i + 1} Latitude", default_driver_locations[i][0], key=f"driver_lat_{i}")
        #     lon = st.sidebar.text_input(f"Driver {i + 1} Longitude", default_driver_locations[i][1], key=f"driver_lon_{i}")
        #     capacity = st.sidebar.slider(f"Driver {i + 1} Capacity", 1, 4, value=2, key=f"capacity_{i}")
        #     driver_coords.append((lat, lon))
        #     capacity_list.append(capacity)
        driver_coords = []
        capacity_list = []
        for i in range(num_drivers):
            st.sidebar.subheader(f"Driver {i + 1}")
            
            # Extract default coordinates from the tuple
            default_lat, default_lon = default_driver_locations[i]

            # Use single input for lat, lon
            coord_input = st.sidebar.text_input(f"Driver {i + 1} Location (lat,lon)", f"{default_lat},{default_lon}", key=f"driver_coord_{i}")

            try:
                lat, lon = map(float, coord_input.split(','))
                capacity = st.sidebar.slider(f"Driver {i + 1} Capacity", 1, 4, value=2, key=f"capacity_{i}")
                driver_coords.append((lat, lon))
                capacity_list.append(capacity)
            except ValueError:
                st.error(f"Invalid format for Driver {i + 1}. Please enter coordinates as 'lat,lon'.")

        if st.sidebar.button("Update Drivers", key="update_drivers"):
            st.session_state.driver_coords.clear()
            st.session_state.driver_capacity.clear()
            for (lat, lon), capacity in zip(driver_coords, capacity_list):
                try:
                    lat = float(lat)
                    lon = float(lon)
                    st.session_state.driver_coords.append((lat, lon))
                    st.session_state.driver_capacity.append(capacity)
                    st.success(f"Driver updated at ({lat}, {lon}) with capacity {capacity}")
                except ValueError:
                    st.error("Invalid driver coordinates.")
                    
        for lat, lon in st.session_state.driver_coords:
            folium.Marker(location=[lat, lon], popup="Drivers", icon=folium.Icon(color="gray")).add_to(folium_map)

        if st.sidebar.button("Clear Drivers", key="clear_drivers"):
            st.session_state.driver_coords.clear()
            st.session_state.driver_capacity.clear()
            st.success("Driver locations cleared.")

        if st.button("Process", key="process"):
            if st.session_state.driver_coords and st.session_state.markers:
                with st.spinner("Processing..."):
                    # Find best paths for all drivers
                    locations = {f'driver{i + 1}': coords for i, coords in enumerate(st.session_state.driver_coords)}
                    locations['office'] = st.session_state.office_location
                    locations['companion'] = st.session_state.markers[0] if st.session_state.markers else (12.905, 77.605)
                    
                    # print(locations)

                    paths = find_best_paths(st.session_state.bangalore_graph, locations)

                    # print(paths)
                    # Calculate aerial distances for each driver's path to the companion
                    companion_coords = st.session_state.markers[0]  # Take the first companion
                    lat,lon=companion_coords
                    comp_node = [ox.distance.nearest_nodes(st.session_state.bangalore_graph, lon, lat)]
                    aerial_distances = calculate_driver_companion_distances(st.session_state.bangalore_graph, paths, comp_node)
                
                    driver_companion_distances = find_best_intersection_node(st.session_state.bangalore_graph, paths, comp_node, aerial_distances)
                    # Get top intersections based on aerial distances
                    
                    best_drivers = sorted(driver_companion_distances.items(), key=lambda x: x[1][0])  # Sort by distance
                    for (driver_label, companion_node), (distance, time, intersection) in best_drivers:
                        print(f"Driver {driver_label} is {distance:.2f} km away from the companion with a total travel time of {time:.2f} minutes.")
                        if intersection:
                            intersection_coords = (st.session_state.bangalore_graph.nodes[intersection]['y'], st.session_state.bangalore_graph.nodes[intersection]['x'])
                            print(f"Best intersection point is at coordinates: {intersection_coords}")
                    
                    best_driver = None
                    best_distance = float('inf')
                    best_intersection_node=-1
                    best_time=0

                    # Iterate over the dictionary to find the minimum distance
                    for (driver_label, companion_node), (distance, time, intersection) in driver_companion_distances.items():
                        if distance < best_distance:
                            best_distance = distance
                            best_driver = driver_label 
                            best_intersection_node = intersection 
                            best_time = time 
                    
                    best_driver_info={best_driver:(best_distance,best_time,best_intersection_node)}

                    if best_driver_info:
                        st.session_state.best_driver_info = best_driver_info
                        st.session_state.page = 'results'
                    else:
                        st.error("No available drivers meet the criteria.")

            else:
                st.warning("Please add both driver and companion locations before processing.")


        # Display the map
        st_folium(folium_map, width=900, height=600)

        # Logout Button
        if st.button("Logout", key="logout"):
            st.session_state.page = 'login'

    elif st.session_state.page == 'results':
        folium_map = folium.Map(location=[12.9716, 77.5946], zoom_start=12)
        st.title("Best Driver and Companion Match")
        best_driver_info = st.session_state.best_driver_info
        for lat, lon in st.session_state.driver_coords:
            folium.Marker(location=[lat, lon], popup="Driver", icon=folium.Icon(color="gray")).add_to(folium_map)
        if best_driver_info:
            for driver_label, (actual_distance, driver_time, intersection_node) in best_driver_info.items():
                st.success(f"The best match is {driver_label} with an actual distance of {actual_distance:.2f} m and driver time of {driver_time:.2f} minutes.")

                # Use pre-loaded graph
                graph = st.session_state.bangalore_graph
                
                paths = find_best_paths(graph, {
                    driver_label: st.session_state.driver_coords[int(driver_label[-1]) - 1],
                    'office': st.session_state.office_location,
                    'companion': st.session_state.markers[0]
                })
                # print(f"paths is {paths}")

                # Plot the paths on a new map
                path_map = plot_paths_on_map(paths, graph, {
                    driver_label: st.session_state.driver_coords[int(driver_label[-1]) - 1],
                    'office': st.session_state.office_location,
                    'companion': st.session_state.markers[0]
                }, best_driver_info)
                st_folium(path_map, width=900, height=600)
        else :
            st.write("Sorry No mathcing for You right Now")
            

        if st.button("Reset Everything", key="reset"):
            st.session_state.markers.clear()
            st.session_state.driver_coords.clear()
            st.session_state.driver_capacity.clear()
            st.session_state.best_driver_info = None
            st.session_state.page = 'map'  # Go back to map

        if st.button("Logout", key="logout_results"):
            st.session_state.page = 'login'

if __name__ == "__main__":
    main()
