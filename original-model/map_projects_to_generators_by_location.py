#!/usr/bin/env python3
"""
Map planned projects to generators based on location and assign location-specific weather profiles.

This module:
1. Reads REPD planning database with location information
2. Maps projects to nearest representative generator based on location
3. For offshore: creates location-specific weather profiles for each project
4. For onshore/solar: maps to correct representative generator based on location
"""

import pandas as pd
import numpy as np
from math import radians, cos, sin, asin, sqrt
import config
try:
    from netCDF4 import Dataset
except ModuleNotFoundError:
    Dataset = None
import xarray as xr

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points on Earth (in km).
    
    Parameters:
    - lat1, lon1: Latitude and longitude of first point (in degrees)
    - lat2, lon2: Latitude and longitude of second point (in degrees)
    
    Returns:
    - Distance in kilometers
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in kilometers
    return c * r


def find_nearest_generator(project_lat, project_lon, tech_type, generator_objects):
    """
    Find the nearest representative generator for a project based on location.
    
    Parameters:
    - project_lat, project_lon: Project location coordinates
    - tech_type: Technology type ('solar', 'onshore', 'offshore')
    - generator_objects: Dictionary of generator objects
    
    Returns:
    - Name of nearest generator
    """
    from run_investment_analysis import get_asset_type
    
    min_distance = float('inf')
    nearest_generator = None
    
    # Get all generators of the matching technology type
    for name, asset in generator_objects.items():
        asset_type = get_asset_type(name)
        if asset_type != tech_type:
            continue
        # Resolve location: config has city names (Nottingham) and offshore1..21
        loc_key = None
        if name in config.locations:
            loc_key = name
        elif tech_type in ('solar', 'onshore') and '_' in name:
            city = name.split('_', 1)[1]
            if city in config.locations:
                loc_key = city
        if loc_key is None:
            continue
        gen_lat = config.locations[loc_key]["lat"]
        gen_lon = config.locations[loc_key]["lon"]
        distance = haversine_distance(project_lat, project_lon, gen_lat, gen_lon)
        if distance < min_distance:
            min_distance = distance
            nearest_generator = name

    return nearest_generator, min_distance


# get_asset_type is imported from run_investment_analysis


def extract_location_from_repd(repd_row):
    """
    Extract latitude and longitude from REPD row.
    
    REPD files typically have columns like:
    - 'Latitude' or 'Lat'
    - 'Longitude' or 'Lon' or 'Long'
    - Or 'Location' with coordinates in text
    
    Returns:
    - (lat, lon) tuple or (None, None) if not found
    """
    # Try common column names
    lat_cols = ['Latitude', 'Lat', 'latitude', 'lat']
    lon_cols = ['Longitude', 'Lon', 'Long', 'longitude', 'lon', 'long']
    
    lat = None
    lon = None
    
    for col in lat_cols:
        if col in repd_row.index and pd.notna(repd_row[col]):
            try:
                lat = float(repd_row[col])
                break
            except (ValueError, TypeError):
                continue
    
    for col in lon_cols:
        if col in repd_row.index and pd.notna(repd_row[col]):
            try:
                lon = float(repd_row[col])
                break
            except (ValueError, TypeError):
                continue
    
    # If not found, try to parse from location text
    if lat is None or lon is None:
        location_cols = ['Location', 'Site Location', 'Coordinates', 'location']
        for col in location_cols:
            if col in repd_row.index and pd.notna(repd_row[col]):
                location_str = str(repd_row[col])
                # Try to extract coordinates from text (e.g., "51.5, -0.1" or "51.5°N, 0.1°W")
                import re
                coords = re.findall(r'-?\d+\.?\d*', location_str)
                if len(coords) >= 2:
                    try:
                        lat = float(coords[0])
                        lon = float(coords[1])
                        break
                    except (ValueError, TypeError):
                        continue
    
    return lat, lon


def load_repd_with_locations(repd_file='repd-q2-jul-2025.csv'):
    """
    Load REPD projects with location information.
    
    Returns:
    - DataFrame with projects including lat/lon columns
    """
    try:
        df = pd.read_csv(repd_file, encoding='utf-8')
    except UnicodeDecodeError:
        df = pd.read_csv(repd_file, encoding='latin1')
    
    # Extract locations
    locations = []
    for _, row in df.iterrows():
        lat, lon = extract_location_from_repd(row)
        locations.append({'lat': lat, 'lon': lon})
    
    df_locations = pd.DataFrame(locations)
    df = pd.concat([df, df_locations], axis=1)
    
    return df


def map_projects_to_generators(project_pipeline, generator_objects, repd_file='repd-q2-jul-2025.csv'):
    """
    Map projects from pipeline to generators based on location.
    
    For offshore projects: Creates location-specific weather profiles
    For onshore/solar: Maps to nearest representative generator
    
    Parameters:
    - project_pipeline: List of project dictionaries
    - generator_objects: Dictionary of generator objects
    - repd_file: Path to REPD CSV file with location data
    
    Returns:
    - Updated project_pipeline with 'assigned_generator' and 'location' fields
    - Dictionary mapping generator names to their weather profile locations
    """
    from run_investment_analysis import get_asset_type

    # Load REPD data with locations
    try:
        repd_df = load_repd_with_locations(repd_file)
        # Create a mapping from project name to location
        repd_location_map = {}
        for _, row in repd_df.iterrows():
            project_name = row.get('Site Name', '')
            lat = row.get('lat')
            lon = row.get('lon')
            if pd.notna(lat) and pd.notna(lon):
                repd_location_map[project_name] = (lat, lon)
    except Exception as e:
        print(f"Warning: Could not load REPD locations: {e}")
        repd_location_map = {}
    
    # Track generator locations for weather profile assignment
    generator_weather_locations = {}
    offshore_locations = {}  # generator name -> list of {lat, lon, project_name} for weather profiles

    # Process each project
    for project in project_pipeline:
        tech_type = project.get('technology_type')
        project_name = project.get('name', '')
        
        # Try to get location from project data first (from load_external_projects)
        project_lat = project.get('latitude')
        project_lon = project.get('longitude')
        
        # If not in project, try REPD map
        if (project_lat is None or project_lon is None) and project_name in repd_location_map:
            project_lat, project_lon = repd_location_map[project_name]
        
        # If still None, mark as no location data
        if project_lat is None or project_lon is None:
            project_lat = None
            project_lon = None
        
        if tech_type == 'offshore':
            # For offshore, we need location-specific weather profiles
            if project_lat is not None and project_lon is not None:
                # Find nearest existing offshore generator
                nearest_gen, distance = find_nearest_generator(
                    project_lat, project_lon, 'offshore', generator_objects
                )
                
                if nearest_gen:
                    project['assigned_generator'] = nearest_gen
                    project['location'] = {'lat': project_lat, 'lon': project_lon}
                    project['distance_to_generator_km'] = distance
                    
                    # Store location for weather profile creation
                    if nearest_gen not in offshore_locations:
                        offshore_locations[nearest_gen] = []
                    offshore_locations[nearest_gen].append({
                        'lat': project_lat,
                        'lon': project_lon,
                        'project_name': project_name
                    })
                else:
                    # No matching generator found, use first offshore generator
                    offshore_gens = [name for name in generator_objects.keys() 
                                   if get_asset_type(name) == 'offshore']
                    if offshore_gens:
                        project['assigned_generator'] = offshore_gens[0]
                        project['location'] = {'lat': project_lat, 'lon': project_lon}
            else:
                # No location data, use proportional allocation (existing logic)
                project['assigned_generator'] = None  # Will use proportional allocation
                
        elif tech_type in ['onshore', 'solar']:
            # For onshore/solar, map to nearest representative generator by lat/lon, or by region
            if project_lat is not None and project_lon is not None:
                nearest_gen, distance = find_nearest_generator(
                    project_lat, project_lon, tech_type, generator_objects
                )
                
                if nearest_gen:
                    project['assigned_generator'] = nearest_gen
                    project['location'] = {'lat': project_lat, 'lon': project_lon}
                    project['distance_to_generator_km'] = distance
                else:
                    project['assigned_generator'] = None
            else:
                # No lat/lon: assign by REPD region so each planned project goes to correct region
                from run_investment_analysis import region_to_generator_name
                region = project.get('region', '')
                gen_name = region_to_generator_name(region, tech_type)
                if gen_name and gen_name in generator_objects:
                    project['assigned_generator'] = gen_name
                    project['location'] = {}
                    project['distance_to_generator_km'] = 'N/A'
                else:
                    project['assigned_generator'] = None
    
    # Store generator weather locations
    generator_weather_locations['offshore'] = offshore_locations
    
    return project_pipeline, generator_weather_locations


def create_weather_profile_for_location(lat, lon, weather_file, profile_type='wind'):
    """
    Create a weather profile for a specific location.
    
    Parameters:
    - lat, lon: Location coordinates
    - weather_file: Path to weather data file (netCDF)
    - profile_type: 'wind' or 'solar'
    
    Returns:
    - Weather profile array
    """
    try:
        if profile_type == 'wind':
            # Use acm_energy function from simulation_model
            from simulation_model import acm_energy
            ds = xr.open_dataset(weather_file)
            profile = acm_energy(ds, lat, lon)
            ds.close()
            return profile
        elif profile_type == 'solar':
            # Use acm_solar function from simulation_model
            from simulation_model import acm_solar
            dataset = Dataset(weather_file, 'r') if Dataset is not None else xr.open_dataset(weather_file)
            profile = acm_solar(dataset, lat, lon)
            dataset.close()
            return profile
    except Exception as e:
        print(f"Error creating weather profile for ({lat}, {lon}): {e}")
        return None


def update_generator_weather_profiles(generator_weather_locations, weather_data_paths):
    """
    Update weather profiles for generators based on their assigned project locations.
    
    For offshore generators with multiple projects, use weighted average of locations.
    
    Parameters:
    - generator_weather_locations: Dictionary from map_projects_to_generators
    - weather_data_paths: Dict with 'wind' and 'solar' file paths
    
    Returns:
    - Dictionary mapping generator names to weather profiles
    """
    generator_profiles = {}
    
    # Process offshore generators
    if 'offshore' in generator_weather_locations:
        wind_file = weather_data_paths.get('wind', 
            r'F:\newfinalweather\average_annual_wind_profile.nc')
        
        for gen_name, locations in generator_weather_locations['offshore'].items():
            if locations:
                # For multiple projects, create weighted average profile
                # Weight by project capacity (if available) or equal weight
                profiles = []
                weights = []
                
                for loc_info in locations:
                    lat = loc_info['lat']
                    lon = loc_info['lon']
                    capacity = loc_info.get('capacity', 1.0)  # Default weight
                    
                    profile = create_weather_profile_for_location(lat, lon, wind_file, 'wind')
                    if profile is not None:
                        profiles.append(profile)
                        weights.append(capacity)
                
                if profiles:
                    # Weighted average
                    weights = np.array(weights)
                    weights = weights / weights.sum()  # Normalize
                    
                    # Calculate weighted average
                    weighted_profile = np.zeros_like(profiles[0])
                    for profile, weight in zip(profiles, weights):
                        weighted_profile += profile * weight
                    
                    generator_profiles[gen_name] = weighted_profile
                    print(f"Created weighted weather profile for {gen_name} from {len(locations)} locations")
    
    return generator_profiles


if __name__ == '__main__':
    # Example usage
    print("Project-to-Generator Location Mapping Module")
    print("This module should be imported and used in the investment analysis pipeline")

