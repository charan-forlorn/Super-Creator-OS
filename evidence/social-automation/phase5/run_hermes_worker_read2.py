import subprocess, pathlib, sys
p=pathlib.Path(r'C:\Workspace\super-creator-os\evidence\social-automation\phase5\cf-worker-read2.txt')
r=subprocess.run(['hermes','-z',p.read_text(encoding='utf-8'),'--in',r'C:\Workspace\super-creator-os','--yolo'],capture_output=True,text=True,encoding='utf-8',errors='replace')
print(r.stdout)
print(r.stderr,file=sys.stderr)
raise SystemExit(r.returncode)