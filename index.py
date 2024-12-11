import os
import json

import google.generativeai as genai

from textblob import TextBlob

from flask import Flask, jsonify, send_file, request
from flask_cors import CORS

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

from datetime import datetime

# config.py
CHROME_BINARY = "/usr/bin/chromium"
CHROME_DRIVER = "/usr/bin/chromedriver"
CHROME_OPTIONS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--window-size=1280,1024",
    "--headless"
]

CHROME_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.110 Safari/537.36"
# CHROME_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
CHROME_EXTENSION = "ad-blocker"

BASE_URL = "https://www.google.com"

genai.configure(api_key="AIzaSyCMkLUDUU6lL-uEIMXosFzA5zDfcny3SQQ")
model = genai.GenerativeModel("gemini-1.5-flash")

stock_urls = None

def load_stock_config():
    """Load stock configuration from JSON file during server startup"""
    global stock_urls
    try:
        with open('stock_config.json', 'r') as file:
            stock_urls = json.load(file)
        return "Stock configuration loaded successfully."
    except Exception as e:
        return f"Error loading stock configuration: {str(e)}"
    
# driver_manager.py
class DriverManager:
    def __init__(self):
        self.driver = None
    
    def init_driver(self, user_data_dir):
        if self.driver is None:
            chrome_options = Options()
            for option in CHROME_OPTIONS:
                chrome_options.add_argument(option)
            chrome_options.binary_location = CHROME_BINARY
            chrome_options.add_argument(f"user-data-dir={user_data_dir}")
            chrome_options.add_argument(f"user-agent={CHROME_USER_AGENT}")
            
            chrome_options.add_extension(f"./{CHROME_EXTENSION}.crx")

            service = Service(CHROME_DRIVER)
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.get(BASE_URL)
            return "WebDriver initialized successfully."
        return "WebDriver already initialized."

    def take_screenshot(self):
        """Take a screenshot of the current WhatsApp session."""
        try:
            if self.driver is not None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = f"./screenshots/whatsapp_screenshot_{timestamp}.png"
                os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                self.driver.save_screenshot(screenshot_path)
                return screenshot_path, "Screenshot saved successfully."
            else:
                return None, "Driver is not initialized."
        except Exception as e:
            return None, f"Error taking screenshot: {str(e)}"

    def quit_driver(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
            return "WebDriver quit successfully."
        return "WebDriver is not running."

# scraper.py
class NewsScraper:
    def __init__(self, driver):
        self.driver = driver
    
    def extract_urls(self):
        try:
            news_list = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "news_list"))
            )
            news_urls = [li.find_element(By.CSS_SELECTOR, "p > a").get_attribute("href")
                        for li in news_list.find_elements(By.TAG_NAME, "li")]
            
            newsblock = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "newsblock1"))
            )
            newsblock_urls = [a.get_attribute("href") 
                            for a in newsblock.find_elements(By.TAG_NAME, "a")]
            
            return list(set(news_urls + newsblock_urls))
        except Exception as e:
            raise Exception(f"Error extracting URLs: {str(e)}")
    
    def extract_article_text(self, url):
        try:
            self.driver.get(url)
            content_div = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "content_wrapper"))
            )   

            # Extract text content
            article_text = " ".join(
                p.get_attribute("textContent").strip()
                for p in content_div.find_elements(By.TAG_NAME, "p")
                if p.get_attribute("textContent").strip()
                and 'display: none;' not in p.get_attribute("style")
            )   

            # Extract date from article schedule div
            try:
                schedule_div = self.driver.find_element(By.CLASS_NAME, "article_schedule")
                date_text = schedule_div.text.strip()

                date_text = date_text.replace(" IST", "")
                date_part = date_text.split(" / ")[0]
                time_part = date_text.split(" / ")[1]

                full_datetime = f"{date_part} {time_part}"
                date_obj = datetime.strptime(full_datetime, '%B %d, %Y %H:%M')

                formatted_date = date_obj.strftime('%B %d, %Y %I:%M %p')
                date_obj = datetime.strptime(formatted_date, '%B %d, %Y %I:%M %p')
            except Exception as e:
                print(f"Date extraction error: {str(e)}")
                date_obj = None 

            return {
                "text": article_text,
                "date": date_obj
            }   

        except Exception as e:
            raise Exception(f"Failed to extract article content: {str(e)}")

# sentiment_analyzer.py
class SentimentAnalyzer:
    @staticmethod
    def analyze(text):
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        return {
            "positive": max(0, polarity),
            "negative": abs(min(0, polarity)),
            "polarity": polarity
        }
    
    @staticmethod
    def genAIAnalysis(news, stock):
        response = model.generate_content(
            f"This is the news: {news}. Provide brief sentiment analysis from the news for the stock:{stock}."
        )

        return response.text


# app.py
app = Flask(__name__)
CORS(app)
driver_manager = DriverManager()

@app.route('/api/init', methods=['POST'])
def api_init():
    try:
        user_data_dir = os.path.join(os.getcwd(), "session")

        os.makedirs(user_data_dir, exist_ok=True)
        result = driver_manager.init_driver(user_data_dir)
        
        return jsonify({"message": result})
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/quit', methods=['POST'])
def api_quit():
    message = driver_manager.quit_driver()
    return jsonify({"message": message}), 200 if "successfully" in message else 400

@app.route('/api/screenshot', methods=['GET'])
def get_screenshot():
    """API endpoint to get the latest screenshot."""
    screenshot_path, message = driver_manager.take_screenshot()

    if screenshot_path and os.path.exists(screenshot_path):
        return send_file(screenshot_path, mimetype='image/png'), 200
    elif "Driver is not initialized" in message:
        return jsonify({"error": message}), 400
    else:
        return jsonify({"error": message}), 500

@app.route('/api/analyse', methods=['GET'])
def get_news_analysis():
    try:
        data = request.get_json()
        symbol = data.get('symbol')
        
        if not symbol:
            return jsonify({
                'status': 'error',
                'message': 'Stock symbol is required'
            }), 400
            
        if symbol not in stock_urls:
            return jsonify({
                'status': 'error',
                'message': f'Invalid stock symbol: {symbol}'
            }), 400
            
        # Update the current URL
        driver_manager.driver.get(stock_urls[symbol])
        
        scraper = NewsScraper(driver_manager.driver)
        analyzer = SentimentAnalyzer()
        
        data = []
        for url in scraper.extract_urls():
            article_data = scraper.extract_article_text(url)
            text = article_data["text"]
            date = article_data["date"]
            sentiment = analyzer.analyze(text)
            genai_analysis = analyzer.genAIAnalysis(text, symbol)
            data.append({
                "news-url": url,
                "news-date": date,
                "sentiment": sentiment,
                "genai_analysis": genai_analysis
            })
        
        sorted_data = sorted(
            data, 
            key=lambda x: x["news-date"] if x["news-date"] else datetime.min,
            reverse=True
        )
        return jsonify({
            'status': 'success',
            'data': sorted_data
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == '__main__':
    load_stock_config()
    app.run(host='0.0.0.0', port=5173)