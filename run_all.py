import os
import re
import subprocess
import sys
import time

import plivo
from dotenv import load_dotenv

# Load environment variables dynamically
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, ".env")
load_dotenv(dotenv_path=env_path)

auth_id = os.getenv("PLIVO_AUTH_ID")
auth_token = os.getenv("PLIVO_AUTH_TOKEN")
app_id = "17610917888861742"
port = 7860
subdomain = "goodwind-plivo-agent"

def kill_port_owner(port):
    """Find and kill the process holding the given local port on Windows."""
    print(f"Checking for any process running on port {port}...", flush=True)
    try:
        # Get TCP connections on port using PowerShell
        cmd = f"powershell -Command \"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess\""
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        pids = [line.strip() for line in result.stdout.split('\n') if line.strip()]
        
        # Filter PIDs to kill (must be digits)
        pids_to_kill = set(pid for pid in pids if pid and pid.isdigit() and pid != '0')
        if pids_to_kill:
            for pid in pids_to_kill:
                print(f"Killing process with PID {pid} occupying port {port}...", flush=True)
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
            time.sleep(2)
        else:
            print(f"Port {port} is clear.", flush=True)
    except Exception as e:
        print(f"Error freeing port {port}: {e}", flush=True)

def update_plivo_url(url):
    if not auth_id or not auth_token:
        print("Plivo credentials not found in env, skipping webhook update.", flush=True)
        return
    try:
        client = plivo.RestClient(auth_id, auth_token)
        print(f"\n[PLIVO UPDATE] Updating Plivo App {app_id} to Answer URL: {url}", flush=True)
        response = client.applications.update(
            app_id=app_id,
            answer_url=url,
            answer_method="POST"
        )
        print(f"[PLIVO UPDATE] Update response: {response}\n", flush=True)
    except Exception as e:
        print(f"[PLIVO UPDATE ERROR] Error updating Plivo App: {e}", flush=True)

def main():
    # 1. Kill any existing process on port 7860
    kill_port_owner(port)
    
    # 2. Start the FastAPI server
    print("Starting FastAPI server...", flush=True)
    server_process = subprocess.Popen(
        ["uv", "run", "server.py"],
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True
    )
    
    # Wait briefly for server startup
    time.sleep(2)
    
    # 3. Start localtunnel loop
    print("Starting localtunnel...", flush=True)
    try:
        while True:
            print(f"Launching localtunnel on port {port} with subdomain {subdomain}...", flush=True)
            cmd = f"npx -y localtunnel --port {port} --subdomain {subdomain}"
            tunnel_process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Read stdout line by line and print immediately
            if tunnel_process.stdout:
                for line in iter(tunnel_process.stdout.readline, ""):
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    if "your url is:" in line:
                        match = re.search(r"https://[^\s]+", line)
                        if match:
                            url = match.group(0)
                            if not url.endswith("/"):
                                url += "/"
                            update_plivo_url(url)
            
            tunnel_process.wait()
            print(f"localtunnel process exited with code {tunnel_process.returncode}", flush=True)
            print("Re-trying localtunnel in 3 seconds...", flush=True)
            time.sleep(3)
    except KeyboardInterrupt:
        print("\nShutting down service...", flush=True)
    finally:
        # Clean up server and localtunnel processes on exit
        if 'tunnel_process' in locals() and tunnel_process and tunnel_process.poll() is None:
            print("Terminating localtunnel process...", flush=True)
            tunnel_process.terminate()
            try:
                tunnel_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tunnel_process.kill()
        if 'server_process' in locals() and server_process and server_process.poll() is None:
            print("Terminating server process...", flush=True)
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExit requested by user.", flush=True)
