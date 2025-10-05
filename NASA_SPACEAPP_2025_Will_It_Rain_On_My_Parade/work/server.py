from flask import Flask, request, jsonify, render_template, url_for
from predict_weather import analyze_historical_weather

app = Flask(__name__)

@app.route('/')
def index():
    """Serves the main landing page (index.html)."""
    return render_template('index.html')

@app.route('/app')
def app_page():
    """Serves the main web application page (nasa_2d.html)."""
    return render_template('nasa_2d.html')

@app.route('/analyze', methods=['GET'])
def analyze_weather():
    """
    API endpoint that receives location and date data from the frontend,
    calls the analysis function, and returns the results as JSON.
    """
    try:
        # Extract query parameters from the request URL.
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        month = int(request.args.get('month'))
        day = int(request.args.get('day'))
        conditions_str = request.args.get('conditions', '')
        conditions = [c.strip() for c in conditions_str.split(',') if c.strip()]
        
        # Call the core analysis function from the predict_weather library.
        results = analyze_historical_weather(lat, lon, month, day, conditions=conditions)
        
        # Return the analysis results in JSON format.
        return jsonify(results)
    except Exception as e:
        # Handle potential errors, such as invalid input.
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)