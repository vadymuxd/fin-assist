#!/bin/bash
cd "/Users/vadymshcherbakov/Documents/Claude/Fin Assist"
python3 - <<'EOF'
import os, requests
from dotenv import load_dotenv

load_dotenv()

url   = os.environ['SUPABASE_URL']          # e.g. https://abcdef.supabase.co
token = os.environ['SUPABASE_ACCESS_TOKEN'] # personal access token

# Extract project ref from URL
ref = url.replace('https://', '').split('.')[0]
print(f"Project ref: {ref}")

sql = open('supabase/migrations/0022_monzo_transactions.sql').read()

resp = requests.post(
    f'https://api.supabase.com/v1/projects/{ref}/database/query',
    headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
    json={'query': sql},
)

print(f"Status: {resp.status_code}")
if resp.ok:
    print("✓ Migration 0022 applied successfully.")
    print(resp.json())
else:
    print("✗ Error:")
    print(resp.text)
EOF
