import subprocess
import time
import sys
import os
import re
from dotenv import load_dotenv
import plivo

env_path = r"c:\Users\Equipp\plivo-agent\.env"
load_dotenv(dotenv_path=env_path)

auth_id = os.getenv("PLIVO_AUTH_ID")
auth_token = os.getenv("PLIVO_AUTH_TOKEN")
app_id = "17610917888861742"

print("Starting persistent localtunnel script...")
subdomain = "goodwind-plivo-agent"
port = "7860"

def update_plivo_url(url):
    if not auth_id or not auth_token:
        print("Plivo credentials not found in env, skipping webhook update.")
        return
    try:
        client = plivo.RestClient(auth_id, auth_token)
        print(f"\n[PLIVO UPDATE] Updating Plivo App {app_id} to Answer URL: {url}")
        response = client.applications.update(
            app_id=app_id,
            answer_url=url,
            answer_method="POST"
        )
        print(f"[PLIVO UPDATE] Update response: {response}\n")
    except Exception as e:
        print(f"[PLIVO UPDATE ERROR] Error updating Plivo App: {e}")

while True:
    try:
        print(f"Launching localtunnel on port {port} with subdomain {subdomain}...")
        cmd = ["npx", "-y", "localtunnel", "--port", port, "--subdomain", subdomain]
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        for line in iter(process.stdout.readline, ""):
            sys.stdout.write(line)
            sys.stdout.flush()
            if "your url is:" in line:
                match = re.search(r"https://[^\s]+", line)
                if match:
                    url = match.group(0)
                    # Add trailing slash if not present
                    if not url.endswith("/"):
                        url += "/"
                    update_plivo_url(url)
            
        process.wait()
        print(f"localtunnel process exited with code {process.returncode}")
    except Exception as e:
        print(f"Error running localtunnel: {e}")
        
    print("Re-trying in 3 seconds...")
    time.sleep(3)
