import requests
import json
from datetime import date, timedelta

def analyze_historical_weather(lat, lon, month, day,
                               start_year=2015,
                               end_year=2024,
                               conditions=None,
                               heatwave_threshold_c=40.0,
                               heatwave_duration_days=3,
                               muggy_temp_c=32.0,
                               muggy_humidity_pct=70.0):
    """
    Analyzes historical weather data from the NASA POWER API to calculate the
    probability of user-defined weather conditions for a specific location and day.

    This function checks for three types of events:
    1. Simple, single-day conditions (e.g., precipitation > 10mm).
    2. Complex, multi-day events (e.g., a heatwave over 3 days).
    3. Complex, combination events (e.g., a "muggy day" with high heat AND humidity).

    Args:
        lat (float): Latitude of the location.
        lon (float): Longitude of the location.
        month (int): The target month (1-12).
        day (int): The target day (1-31).
        start_year (int): The beginning of the analysis period.
        end_year (int): The end of the analysis period.
        conditions (list): A list of simple user-defined conditions (e.g., ["precipitation_gt_10"]).
        heatwave_threshold_c (float): The minimum temperature to define a heatwave.
        heatwave_duration_days (int): The number of consecutive days for a heatwave.
        muggy_temp_c (float): The minimum temperature to define a muggy day.
        muggy_humidity_pct (float): The minimum humidity to define a muggy day.

    Returns:
        dict: A dictionary containing the analysis summary and calculated probabilities.
    """
    if conditions is None:
        conditions = []

    # Maps user-friendly names to NASA POWER API parameter codes.
    PARAMETER_MAP = {
        "temperature": "T2M_MAX",
        "precipitation": "PRECTOTCORR",
        "wind_speed": "WS10M",
        "humidity": "RH2M"
    }

    # 1. Parse all conditions and determine which API parameters are needed.
    parsed_conditions = []
    needed_params = set()
    for cond_str in conditions:
        try:
            var, op, val = cond_str.split('_')
            param_code = PARAMETER_MAP[var]
            needed_params.add(param_code)
            parsed_conditions.append({'condition_str': cond_str, 'param_code': param_code, 'op': op, 'value': float(val), 'count': 0})
        except (ValueError, KeyError):
            pass # Silently skip invalid conditions in a production environment.

    # Ensure parameters for complex events are always included in the API call.
    needed_params.add(PARAMETER_MAP["temperature"])
    needed_params.add(PARAMETER_MAP["humidity"])

    # 2. Initialize counters for the analysis.
    total_years_checked = 0
    heatwave_count = 0
    muggy_day_count = 0

    # 3. Loop through each year in the historical period.
    for year in range(start_year, end_year + 1):
        # Fetch a chunk of days to check for consecutive patterns like heatwaves.
        daily_data_chunk = get_weather_data_range(lat, lon, year, month, day, heatwave_duration_days, list(needed_params))

        if daily_data_chunk and len(daily_data_chunk) == heatwave_duration_days:
            total_years_checked += 1
            first_day_data = daily_data_chunk[0]
            
            # Check for "muggy day" (hot AND humid on the same day).
            temp = first_day_data.get(PARAMETER_MAP["temperature"])
            humidity = first_day_data.get(PARAMETER_MAP["humidity"])
            if temp is not None and humidity is not None:
                if temp > muggy_temp_c and humidity > muggy_humidity_pct:
                    muggy_day_count += 1

            # Check for "heatwave" (consecutive hot days).
            is_heatwave = True
            for day_data in daily_data_chunk:
                temp_of_day = day_data.get(PARAMETER_MAP["temperature"])
                if temp_of_day is None or temp_of_day < heatwave_threshold_c:
                    is_heatwave = False
                    break
            if is_heatwave:
                heatwave_count += 1

            # Check for all simple, single-day conditions from the user.
            for cond in parsed_conditions:
                value_from_api = first_day_data.get(cond['param_code'])
                if value_from_api is not None:
                    if cond['op'] == 'gt' and value_from_api > cond['value']: cond['count'] += 1
                    elif cond['op'] == 'lt' and value_from_api < cond['value']: cond['count'] += 1
    
    # 4. Format the final JSON object with all calculated probabilities.
    final_results = {"analysis": {
        "location": {"lat": lat, "lon": lon}, "date": f"{month:02d}-{day:02d}",
        "period": f"{start_year}-{end_year}", "years_with_data": total_years_checked
    }, "probabilities": []}

    if total_years_checked > 0:
        for cond in parsed_conditions:
            final_results["probabilities"].append({
                "condition": cond['condition_str'], "event_count": cond['count'],
                "probability": round((cond['count'] / total_years_checked) * 100, 2)
            })
        final_results["probabilities"].append({
            "condition": f"heatwave ({heatwave_duration_days} consecutive days > {heatwave_threshold_c}°C)",
            "event_count": heatwave_count, "probability": round((heatwave_count / total_years_checked) * 100, 2)
        })
        final_results["probabilities"].append({
            "condition": f"muggy_day (temp > {muggy_temp_c}°C AND humidity > {muggy_humidity_pct}%)",
            "event_count": muggy_day_count, "probability": round((muggy_day_count / total_years_checked) * 100, 2)
        })

    return final_results

def get_weather_data_range(lat, lon, year, month, day, num_days, parameters):
    """
    Fetches a range of daily weather data from the NASA POWER API.
    """
    start_date = date(year, month, day)
    end_date = start_date + timedelta(days=num_days - 1)
    
    base_url = "https://power.larc.nasa.gov/api/temporal/daily/point"
    api_params = sorted(list(set(parameters)))

    params = {
        "parameters": ",".join(api_params),
        "community": "RE",
        "longitude": lon,
        "latitude": lat,
        "start": start_date.strftime("%Y%m%d"),
        "end": end_date.strftime("%Y%m%d"),
        "format": "JSON"
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status() # Raises an error for bad status codes (4xx or 5xx)
        data = response.json()
        
        # Robustly find the date keys from the first available parameter.
        date_keys_source = None
        for p in api_params:
            if p in data['properties']['parameter'] and data['properties']['parameter'][p]:
                date_keys_source = data['properties']['parameter'][p]
                break
        
        if not date_keys_source: return None
        
        dates = date_keys_source.keys()

        # Re-formats the API response into a more usable list of daily data.
        daily_data = []
        for d in sorted(dates):
            day_dict = {}
            for p in api_params:
                if p in data['properties']['parameter']:
                    day_dict[p] = data['properties']['parameter'][p].get(d, None)
                else:
                    day_dict[p] = None
            daily_data.append(day_dict)
        return daily_data
    except Exception:
        # In case of any API or parsing error, return None to be handled by the main function.
        return None