import subprocess, pathlib, sys
prompt = pathlib.Path(r"C:\Workspace\super-creator-os\evidence\social-automation\phase5\cf-worker-deploy.txt").read_text(encoding="utf-8")
args = ["hermes", "-z", prompt, "--in", r"C:\Workspace\super-creator-os", "--yolo"]
p = subprocess.run(args, text=True, capture_output=True)
print(p.stdout)
print(p.stderr, file=sys.stderr)
raise SystemExit(p.returncode)
