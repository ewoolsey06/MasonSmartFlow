import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# Pull your app URL from Github Secrets or use a fallback string
url = os.environ.get("STREAMLIT_APP_URL", "https://masonsmartflow-tysg2tcwknuemmwxxcasu3.streamlit.app/")

options = Options()
options.add_argument("--headless") # Runs completely in the background
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

print(f"Launching browser to visit: {url}")
driver = webdriver.Chrome(options=options)

try:
    driver.get(url)
    time.sleep(10) # Give the page plenty of time to render the layout

    # Search for Streamlit's official 'Yes, get this app back up!' button text
    buttons = driver.find_elements(By.XPATH, "//button[contains(text(), 'Yes, get this app back up!')]")
    
    if buttons:
        print("App was asleep! Clicking the wake-up button now...")
        buttons[0].click()
        time.sleep(15) # Wait for the app container to rebuild completely
        print("App successfully kicked awake.")
    else:
        print("App is already awake and responsive.")

except Exception as e:
    print(f"An error occurred during execution: {e}")

finally:
    driver.quit()
