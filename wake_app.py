import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# Pull your live Streamlit URL from your environment variables
url = os.environ.get("STREAMLIT_APP_URL", "https://masonsmartflow-tysg2tcwknuemmwxxcasu3.streamlit.app/")

options = Options()
options.add_argument("--headless=new") # Required for running on GitHub Actions
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

print(f"Launching automated browser to visit: {url}")
driver = webdriver.Chrome(options=options)

try:
    driver.get(url)
    print("Waiting 15 seconds for page elements to load...")
    time.sleep(15) 

    # Search for Streamlit's official wake-up button text
    buttons = driver.find_elements(By.XPATH, "//button[contains(., 'Yes, get this app back up!')]")
    
    if buttons:
        print("App is currently sleeping. Clicking the wake-up button...")
        buttons[0].click() # Corrected to click the first element found in the list
        print("Waiting 30 seconds for the app container to rebuild...")
        time.sleep(30) 
        print("App successfully kicked awake!")
    else:
        print("Success! App is already awake and responsive. No action needed.")

except Exception as e:
    print(f"An error occurred during execution: {e}")

finally:
    driver.quit()
