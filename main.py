# main.py

import streamlit as st
import folium
from streamlit_folium import st_folium
import osmnx as ox
from src.helper_functions import *
from src.map_utils import plot_paths_on_map
from config.config import DEFAULT_DRIVER_LOCATIONS  as default_driver_locations

def main():
    st.set_page_config(page_title="Car Pooling App", layout="wide")

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
        st.session_state.office_location = (12.934, 77.62)  # Updated office location
    if 'best_driver_info' not in st.session_state:
        st.session_state.best_driver_info = None
    if 'bangalore_graph' not in st.session_state:
        st.session_state.bangalore_graph = load_bangalore_map_with_times()

    if st.session_state.page == 'login':
        display_login_page()
    elif st.session_state.page == 'map':
        display_map_page()
    elif st.session_state.page == 'results':
        display_results_page()

def display_login_page():
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
folium_map = folium.Map(location=[12.9716, 77.5946], zoom_start=12)


def display_map_page():
    st.title("Map Dashboard")
    st.write("Explore driver and companion locations")

    # Create the map
    # folium_map = folium.Map(location=[12.9716, 77.5946], zoom_start=12)
    folium.Marker(location=[12.931, 77.62], popup="Office", icon=folium.Icon(color="red")).add_to(folium_map)

    handle_companion_input()
    handle_driver_options(folium_map)

    if st.button("Process", key="process"):
        process_routes()

    # Display the map
    st_folium(folium_map, width=900, height=600)

    # Logout Button
    if st.button("Logout", key="logout_map"):
        st.session_state.page = 'login'

def handle_companion_input():
    st.sidebar.title("Companion Location")
    companion_input = st.sidebar.text_input("Companion Location (lat,lon)", "12.937,77.63")
    if st.sidebar.button("Add Companion"):
        try:
            lat, lon = map(float, companion_input.split(','))
            st.session_state.markers.append((lat, lon))
            st.success(f"Companion location added at ({lat}, {lon})")
        except ValueError:
            st.error("Invalid coordinates. Please enter in 'lat,lon' format.")

    for lat, lon in st.session_state.markers:
        folium.Marker(location=[lat, lon], popup="Companion", icon=folium.Icon(color="green")).add_to(folium_map)

def handle_driver_options(folium_map):
    st.sidebar.title("Driver Options")
    num_drivers = st.sidebar.slider("Number of Drivers (1-10)", 1, 10)

    driver_coords = []
    capacity_list = []
    for i in range(num_drivers):
        st.sidebar.subheader(f"Driver {i + 1}")
        default_lat, default_lon = default_driver_locations[i]
        coord_input = st.sidebar.text_input(f"Driver {i + 1} Location (lat,lon)", f"{default_lat},{default_lon}", key=f"driver_coord_{i}")

        try:
            lat, lon = map(float, coord_input.split(','))
            capacity = st.sidebar.slider(f"Driver {i + 1} Capacity", 1, 4, value=2, key=f"capacity_{i}")
            driver_coords.append((lat, lon))
            capacity_list.append(capacity)
        except ValueError:
            st.error(f"Invalid format for Driver {i + 1}. Please enter coordinates as 'lat,lon'.")

    if st.sidebar.button("Update Drivers", key="update_drivers"):
        update_drivers(driver_coords, capacity_list)

    for lat, lon in st.session_state.driver_coords:
        folium.Marker(location=[lat, lon], popup="Drivers", icon=folium.Icon(color="gray")).add_to(folium_map)

    if st.sidebar.button("Clear Drivers", key="clear_drivers"):
        st.session_state.driver_coords.clear()
        st.session_state.driver_capacity.clear()
        st.success("Driver locations cleared.")

def update_drivers(driver_coords, capacity_list):
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

def process_routes():
    if st.session_state.driver_coords and st.session_state.markers:
        with st.spinner("Processing..."):
            locations = {f'driver{i + 1}': coords for i, coords in enumerate(st.session_state.driver_coords)}
            locations['office'] = st.session_state.office_location
            locations['companion'] = st.session_state.markers[0] if st.session_state.markers else (12.905, 77.605)

            paths = find_best_paths(st.session_state.bangalore_graph, locations)
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

def display_results_page():
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

def reset_app():
    st.session_state.markers.clear()
    st.session_state.driver_coords.clear()
    st.session_state.driver_capacity.clear()
    st.session_state.best_driver_info = None
    st.session_state.page = 'map'  # Go back to map

if __name__ == "__main__":
    main()
